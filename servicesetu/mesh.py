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
from .transport import send_customer,delivered
from .fet_payments import request_message as fet_request_message


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
    header=(f"# ServiceSetu {role}\n\n"
        "![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)\n"
        "![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)\n\n")
    if customer:
        return header+("Book a fictional AC or plumbing visit in Indiranagar, Bengaluru. Compare seeded providers and trust labels, review and approve the exact quote, and approve a fresh replacement if a provider cancels. You can message the provider, confirm completion, or report a problem. Try: AC service in Indiranagar Bengaluru tomorrow 10am under INR 1000. Send show what happened for the full history. TomTom MCP discovers local businesses and may show a public listing phone for you to contact them directly; these listings are not onboarded or verified ServiceSetu providers, and their availability is unknown. Taskrabbit assistance supports US locations through an external handoff and is unavailable in India. The demo booking uses simulated payment. FET is implemented for Dorado testnet only; live wallet checkout is unverified. Stripe and Razorpay test integrations are not used in the demo. Providers and trust data are fictional. No real service or live payment is claimed.\n")
    return (header+f"Internal ServiceSetu {role} specialist. Not a customer chat entry point. Accepts typed Work messages only from the Concierge. "
        +"Providers, credentials and registry are seeded test data. Payment is simulated, Stripe/Razorpay test mode, or Dorado native FET testnet only; no mainnet payments. Discretionary refunds, payouts and verification overrides require human review.\n")


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
    conversation=Conversation(store,reasoner,payment_mode=services.payments.mode)

    async def send_reply(ctx,customer,reply):
        # Only acknowledge notices covered by this actual customer response.
        bid=reply.get('notice_booking');last=0
        if bid:
            with store.connect() as db:last=db.execute('SELECT COALESCE(MAX(event),0) FROM booking_notices WHERE booking=?',(bid,)).fetchone()[0]
        result=await send_customer(ctx,customer,chat_message(reply))
        if not delivered(result):ctx.logger.warning('Customer reply delivery failed; booking/payment state retained. Customer can send status to retry.')
        if bid and delivered(result):
            with store.tx() as db:
                for kind in reply.get('notice_kinds',[]):
                    db.execute('UPDATE booking_notices SET sent=1 WHERE booking=? AND event<=? AND event IN (SELECT seq FROM events WHERE kind=?)',(bid,last,kind))

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
                if payment.get('fet_invoice'):
                    invoice=payment['fet_invoice']
                    await send_customer(ctx,sender,fet_request_message(invoice,store.clock()))
                else:
                    q=store.get_quote(b["quote"],owner)
                    await send_customer(ctx,sender,RequestPayment(accepted_funds=[Funds(currency="INR",amount=f"{q['amount']/100:.2f}",payment_method="stripe")],
                        recipient=concierge.address,deadline_seconds=max(1,int(b["hold_until"]-store.clock())),reference=b["id"],
                        description="ServiceSetu fictional service · Stripe TEST payment",metadata={"stripe":payment["stripe"],"service":"servicesetu_test"}))
            await send_reply(ctx,sender,reply)
        except Exception:
            ctx.logger.error("Concierge failed; no outcome assumed")
            await ctx.send(sender,chat_message(envelope("I could not finish this request. Ask for status before retrying; persisted booking/payment intents are retained.")))
    concierge.include(chat,publish_manifest=not offline)

    @concierge.on_interval(period=10)
    async def reply_notices(ctx:Context):
        from .notifications import notify_customers,notify_bookings
        try:
            await notify_bookings(store,ctx)
            await notify_customers(store,ctx)
        except Exception:ctx.logger.warning('Provider reply notice unavailable; stored messages remain available')


    seller=Protocol(spec=payment_protocol_spec,role="seller")
    @seller.on_message(model=CommitPayment)
    async def commit(ctx:Context,sender:str,msg:CommitPayment):
        bid=msg.reference or ""
        try:
            with store.connect() as db:
                row=db.execute("SELECT owner FROM bookings WHERE id=?",(bid,)).fetchone()
            if not row or row["owner"].rsplit(":",1)[0]!=sender: raise Rejected("Payment belongs to another customer")
            owner=row["owner"]
            if owner!=sender+':'+str(ctx.session):raise Rejected('Payment belongs to another conversation')
            if msg.funds.payment_method=='fet_direct':
                if services.payments.mode!='fet_testnet':raise Rejected('Dorado testnet payment is disabled')
                b=await MeshBus(ctx,addresses).call('payment','commit_fet',owner,booking=bid,transaction=msg.transaction_id,
                    funds=msg.funds,recipient=msg.recipient,metadata=msg.metadata,reference=msg.reference)
            else:
                if msg.funds.payment_method!="stripe": raise Rejected("Expected Stripe test payment")
                b=await MeshBus(ctx,addresses).call("payment","commit",owner,booking=bid,transaction=msg.transaction_id,
                    currency=msg.funds.currency,amount=msg.funds.amount,recipient=msg.recipient,expected_recipient=concierge.address)
            if b["state"]=="confirmed": await ctx.send(sender,CompletePayment(transaction_id=msg.transaction_id))
            else: await ctx.send(sender,CancelPayment(transaction_id=msg.transaction_id,reason="Expired reservation; test payment reversed or queued for review"))
            await send_reply(ctx,sender,booking_status(b,store.get_quote(b["quote"],owner)))
        except (Rejected,TimeoutError) as exc:
            await ctx.send(sender,CancelPayment(transaction_id=msg.transaction_id,reason=str(exc)))

    @seller.on_message(model=RejectPayment)
    async def reject_payment(ctx:Context,sender:str,msg:RejectPayment):
        # RejectPayment carries no booking/session reference. A delayed rejection
        # must never cancel a newer or confirmed booking in this conversation.
        await ctx.send(sender,chat_message(envelope("Test checkout was rejected. Send status to review your booking, then cancel booking if you want to release it. A checkout rejection alone does not cancel a booking.")))
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
        reply['text']='Your provider cancelled the booking. '+('Refund required; not yet confirmed.' if b['payment_state']=='refund_required' else 'Review the original booking history for its test-payment reversal status.')+'\n\n'+reply['text']
        customer=msg.owner.rsplit(":",1)[0]
        reply['notice_booking']=msg.booking
        reply['notice_kinds']=['provider_cancelled']
        await send_reply(customer_ctx,customer,reply)

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

    if services.payments.mode=='fet_testnet':
        # Agent identity is agent1...; the agent's native ledger wallet is fetch1...
        services.payments.fet_recipient=str(concierge.wallet.address())

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
        if services.payments.mode in ("stripe_test","razorpay_test"):
            await asyncio.to_thread(reconcile,services)

    port=int(os.getenv("SERVICESETU_PORT","8000"))
    bureau=Bureau(port=port,registration_policy=NoBatchRegistration() if offline else BatchAlmanacApiRegistrationPolicy())
    for agent in agents.values(): bureau.add(agent)
    return bureau,agents,store


def reconcile(services):
    """Compatibility entry point for the monitor and existing proof tools."""
    services.payments.reconcile()


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
