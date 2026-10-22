"""Seven specialist uAgents plus one identity per configured provider.

Eight role types including providers. Bureau shares SQLite on one machine.
Only Concierge exposes ACP. Concierge proxies the human-facing seller protocol
to Payment so ASI:One needs to route the customer to a single address.
"""
from __future__ import annotations
import asyncio
import json
import os
import secrets
import copy
from datetime import datetime,timezone
from pathlib import Path
from uuid import UUID

from uagents import Agent,Bureau,Context,Model,Protocol
from uagents_core.contrib.protocols.chat import ChatMessage,ChatAcknowledgement,chat_protocol_spec
from uagents_core.contrib.protocols.payment import (RequestPayment,CommitPayment,RejectPayment,CompletePayment,CancelPayment,Funds,payment_protocol_spec)
from uagents_core.registration import AgentRegistrationPolicy,BatchRegistrationPolicy
from uagents.registration import BatchAlmanacApiRegistrationPolicy

from .cards import chat_message,booking_status,envelope
from .evidence import evidence_path
from .core import Store,Rejected
from .service import Services
from .conversation import Conversation,strip_recipient


class Work(Model):
    action: str
    owner: str
    data: dict


class Result(Model):
    ok: bool
    data: dict = {}
    error: str = ""


class ProviderCancelled(Model):
    booking: str
    owner: str
    provider: str


class CancelControl(Model):
    booking: str
    token: str


class ControlResult(Model):
    ok: bool
    message: str


class NoRegistration(AgentRegistrationPolicy):
    async def register(self,*args,**kwargs): pass


class NoBatchRegistration(BatchRegistrationPolicy):
    async def register(self,*args,**kwargs): pass
    def add_agent(self,*args,**kwargs): pass


class OfflineAgent(Agent):
    # uAgents 0.25.5 updates Almanac status even with a no-op registration
    # policy. Override that lifecycle hook only in explicit offline mode.
    async def _update_agent_status(self,active): pass


class MeshBus:
    def __init__(self,ctx,addresses): self.ctx,self.addresses=ctx,addresses

    async def call(self,role,action,owner,**data):
        reply,status=await self.ctx.send_and_receive(self.addresses[role],Work(action=action,owner=owner,data=data),response_type=Result,timeout=25)
        if not isinstance(reply,Result): raise TimeoutError(f"{role} timed out; no outcome assumed")
        if not reply.ok: raise Rejected(reply.error)
        return reply.data


def seed_phrase():
    seed=os.getenv("SERVICESETU_SEED")
    if seed: return seed
    path=Path("data/agent-seed")
    path.parent.mkdir(exist_ok=True)
    if not path.exists():
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"w") as f: f.write(secrets.token_hex(32))
    return path.read_text().strip()


def profile(role):
    customer=role=="concierge"
    return (f"# ServiceSetu {role}\n\n"
        "![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)\n"
        "![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)\n\n"
        +("Request fictional home-service packages at Indian locations. Provide city and locality (PIN optional); booking depends on each provider's declared coverage. Ask show services for the available packages, including cleaning, appliance inspections, repairs and furniture assembly. Provider availability depends on the active demo database. Compare provider agents, see honest trust labels, approve one quote, receive a test booking, and recover from provider cancellation. Try: AC service in Indiranagar Bengaluru tomorrow 10am under INR 1000. Ask show what happened for an audit timeline. " if customer else
          f"Internal ServiceSetu {role} specialist. Not a customer chat entry point. Accepts typed Work messages only from the Concierge. ")
        +"Providers, credentials and registry are seeded test data. Payment is simulated or Stripe test mode; no real service or money. Discretionary refunds, payouts and verification overrides require human review.\n")


def create_mesh(store=None,offline=None,reasoner=None,payment_mode=None):
    mailbox=os.getenv("SERVICESETU_MAILBOX","false").lower()=="true"
    offline=not mailbox if offline is None else offline
    if mailbox and offline: raise Rejected("Mailbox mode requires online registration")
    store=store or Store(os.getenv("SERVICESETU_DB","data/servicesetu.db"))
    store.seed()
    services=Services(store,payment_mode)
    roles=["concierge","matching","verification","booking","payment","recovery","trust_monitor"]+["provider:"+p["id"] for p in store.providers()]
    seed=seed_phrase()
    agents={}
    for role in roles:
        path=Path("docs/agents")/(role.replace(":","-")+".md")
        path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists(): path.write_text(profile(role))
        kwargs={"registration_policy":NoRegistration()} if offline else {}
        agent_class=OfflineAgent if offline else Agent
        agents[role]=agent_class(name="ServiceSetu-"+role.replace(":","-"),seed=seed+":"+role,
            mailbox=mailbox,readme_path=str(path),publish_agent_details=not offline,
            handle="servicesetu" if role=="concierge" else None,
            metadata={"is_public":True,"categories":["innovationlab","hackathon"]},
            enable_agent_inspector=not offline,handle_messages_concurrently=False,**kwargs)
    addresses={role:agent.address for role,agent in agents.items()}
    concierge=agents["concierge"]
    conversation=Conversation(store,reasoner)

    def register_worker(role,agent):
        proto=Protocol(name="ServiceSetuMesh",version="0.1.0")
        @proto.on_message(model=Work,replies={Result})
        async def work(ctx:Context,sender:str,msg:Work):
            if sender!=addresses["concierge"]:
                await ctx.send(sender,Result(ok=False,error="Only the Concierge may invoke this internal agent"))
                return
            try:
                result=await asyncio.to_thread(services.execute,role,msg.action,msg.owner,msg.data)
                await ctx.send(sender,Result(ok=True,data=result))
            except (Rejected,KeyError,TypeError,ValueError) as exc:
                store.denied(msg.data.get("booking",msg.owner),str(exc),role)
                await ctx.send(sender,Result(ok=False,error=str(exc)))
            except Exception:
                ctx.logger.error("Worker failed; persisted intent can be retried")
                await ctx.send(sender,Result(ok=False,error="Worker unavailable; retry or request human review"))
        agent.include(proto,publish_manifest=not offline)

    for role,agent in agents.items():
        if role not in ("concierge","trust_monitor"): register_worker(role,agent)

    chat=Protocol(spec=chat_protocol_spec)
    @chat.on_message(model=ChatAcknowledgement)
    async def ack(ctx:Context,sender:str,msg:ChatAcknowledgement): pass

    @chat.on_message(model=ChatMessage)
    async def on_chat(ctx:Context,sender:str,msg:ChatMessage):
        await ctx.send(sender,ChatAcknowledgement(timestamp=datetime.now(timezone.utc),acknowledged_msg_id=msg.msg_id))
        owner=sender+":"+str(ctx.session)
        text=strip_recipient("\n".join(c.text for c in msg.content if c.type=="text"),concierge.address)
        bus=MeshBus(ctx,addresses)
        try:
            reply=await conversation.handle(owner,text,bus,request_id=str(msg.msg_id))
            if reply.get("payment"):
                payment=reply["payment"]
                b=payment["booking"]
                q=store.get_quote(b["quote"],owner)
                await ctx.send(sender,RequestPayment(accepted_funds=[Funds(currency="INR",amount=f"{q['amount']/100:.2f}",payment_method="stripe")],
                    recipient=concierge.address,deadline_seconds=max(1,int(b["hold_until"]-store.clock())),reference=b["id"],
                    description="ServiceSetu fictional service · Stripe TEST payment",metadata={"stripe":payment["stripe"],"service":"servicesetu_test"}))
            await ctx.send(sender,chat_message(reply))
        except Exception:
            ctx.logger.error("Concierge failed; no outcome assumed")
            await ctx.send(sender,chat_message(envelope("I could not finish this request. Ask for status before retrying; persisted booking/payment intents are retained.")))
    concierge.include(chat,publish_manifest=not offline)

    @concierge.on_interval(period=10)
    async def reply_notices(ctx:Context):
        from .notifications import notify_customers
        try:await notify_customers(store,ctx)
        except Exception:ctx.logger.warning('Provider reply notice unavailable; stored messages remain available')


    seller=Protocol(spec=payment_protocol_spec,role="seller")
    @seller.on_message(model=CommitPayment)
    async def commit(ctx:Context,sender:str,msg:CommitPayment):
        bid=msg.reference or ""
        try:
            with store.connect() as db:
                row=db.execute("SELECT owner FROM bookings WHERE id=?",(bid,)).fetchone()
            if not row or row["owner"].rsplit(":",1)[0]!=sender: raise Rejected("Payment belongs to another customer")
            if msg.funds.payment_method!="stripe": raise Rejected("Expected Stripe test payment")
            owner=row["owner"]
            b=await MeshBus(ctx,addresses).call("payment","commit",owner,booking=bid,transaction=msg.transaction_id,
                currency=msg.funds.currency,amount=msg.funds.amount,recipient=msg.recipient,expected_recipient=concierge.address)
            if b["state"]=="confirmed": await ctx.send(sender,CompletePayment(transaction_id=msg.transaction_id))
            else: await ctx.send(sender,CancelPayment(transaction_id=msg.transaction_id,reason="Expired reservation; test payment reversed or queued for review"))
            await ctx.send(sender,chat_message(booking_status(b,store.get_quote(b["quote"],owner))))
        except (Rejected,TimeoutError) as exc:
            await ctx.send(sender,CancelPayment(transaction_id=msg.transaction_id,reason=str(exc)))

    @seller.on_message(model=RejectPayment)
    async def reject_payment(ctx:Context,sender:str,msg:RejectPayment):
        owner=sender+":"+str(ctx.session)
        state=store.session(owner)
        if state.get("booking"):
            await MeshBus(ctx,addresses).call("payment","cancel",owner,booking=state["booking"])
        await ctx.send(sender,chat_message(envelope("Test checkout rejected. Ask for a fresh quote.")))
    concierge.include(seller,publish_manifest=not offline)

    @concierge.on_message(model=ProviderCancelled)
    async def cancellation(ctx:Context,sender:str,msg:ProviderCancelled):
        if sender!=addresses.get("provider:"+msg.provider): return
        b=store.booking(msg.booking,msg.owner)
        if b["provider"]!=msg.provider or b["state"]!="cancelled": return
        state=store.session(msg.owner)
        if state.get("booking")!=msg.booking: return
        # Provider REST notices have their own session. Copy the SDK context to
        # preserve the original customer's session on the outgoing card and RPCs.
        # This isolated adapter is covered by the real-message cancellation proof.
        customer_ctx=copy.copy(ctx)
        customer_ctx._session=UUID(msg.owner.rsplit(":",1)[1])
        reply=await conversation.quotes(MeshBus(customer_ctx,addresses),msg.owner,state["job"],msg.booking)
        customer=msg.owner.rsplit(":",1)[0]
        await customer_ctx.send(customer,chat_message(reply))

    def register_cancel(role,agent):
        provider=role.split(":",1)[1]
        @agent.on_rest_post("/demo/cancel/"+provider,CancelControl,ControlResult)
        async def cancel(ctx:Context,msg:CancelControl):
            token=os.getenv("DEMO_CONTROL_TOKEN","")
            if not token or not secrets.compare_digest(token,msg.token): return ControlResult(ok=False,message="Demo control authentication failed")
            with store.connect() as db:
                b=db.execute("SELECT * FROM bookings WHERE id=? AND provider=?",(msg.booking,provider)).fetchone()
            if not b: return ControlResult(ok=False,message="Booking not assigned to this provider")
            try:
                await asyncio.to_thread(services.payments.cancel,b["owner"],b["id"],"provider:"+provider)
                await ctx.send(addresses["concierge"],ProviderCancelled(booking=b["id"],owner=b["owner"],provider=provider))
                return ControlResult(ok=True,message="Provider cancelled; recovery notice sent")
            except Exception:
                return ControlResult(ok=False,message="Cancellation needs reconciliation; ask for booking status")
    for role,agent in agents.items():
        if role.startswith("provider:"): register_cancel(role,agent)

    @agents["trust_monitor"].on_interval(period=30)
    async def monitor(ctx:Context):
        with store.tx() as db: store.expire(db)
        paused=[]
        for p in store.providers():
            if not store.trust(p,datetime.now(timezone.utc).isoformat())["eligible"]: paused.append(p["id"])
        old=store.session("system:trust_monitor")
        if old.get("paused")!=paused:
            with store.tx() as db: store.event(db,"trust_monitor","eligibility_refresh","trust_monitor",paused=paused)
            store.save_session("system:trust_monitor",{"paused":paused})
        if services.payments.mode=="stripe_test":
            await asyncio.to_thread(reconcile,services)

    port=int(os.getenv("SERVICESETU_PORT","8000"))
    bureau=Bureau(port=port,registration_policy=NoBatchRegistration() if offline else BatchAlmanacApiRegistrationPolicy())
    for agent in agents.values(): bureau.add(agent)
    return bureau,agents,store


def reconcile(services):
    """Poll persisted test checkout references; recover a lost CommitPayment."""
    s=services.store
    with s.connect() as db:
        rows=db.execute("SELECT b.owner,b.id,p.external,p.amount,p.state FROM bookings b JOIN payments p ON p.booking=b.id WHERE p.external IS NOT NULL AND p.state IN ('pending','refund_required')").fetchall()
    for r in rows:
        try:
            if r["state"]=="refund_required": services.payments.refund(r["owner"],r["id"]);continue
            stripe=services.payments.stripe()
            session=stripe.checkout.Session.retrieve(r["external"])
            b=s.booking(r["id"],r["owner"])
            if session.payment_status=="paid":
                if session.livemode or session.amount_total!=r["amount"] or session.currency!="inr" or session.metadata.get("owner")!=r["owner"] or session.metadata.get("booking_id")!=r["id"] or session.client_reference_id!=r["id"]:
                    s.denied(r["id"],"Checkout reconciliation binding mismatch","payment");continue
                b=s.settle(r["owner"],r["id"],external=r["external"])
                if b["payment_state"]=="refund_required": services.payments.refund(r["owner"],r["id"])
            elif b["hold_until"]<=s.clock() or b["state"]=="cancelled":
                if session.status=="open": stripe.checkout.Session.expire(r["external"])
                s.settle(r["owner"],r["id"],success=False)
        except Exception:
            s.denied(r["id"],"Gateway reconciliation retry required","payment")


def main():
    from dotenv import load_dotenv
    load_dotenv()
    bureau,agents,_=create_mesh()
    Path("artifacts").mkdir(exist_ok=True)
    evidence_path("agent-addresses.json").write_text(json.dumps({role:agent.address for role,agent in agents.items()},indent=2))
    print(f"ServiceSetu: {len(agents)} agents / 8 role types · seeded test data ·",os.getenv("PAYMENT_MODE","mock"))
    print("Concierge:",agents["concierge"].address)
    bureau.run()


if __name__=="__main__": main()
