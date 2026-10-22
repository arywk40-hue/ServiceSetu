"""No API keys/server required: real uAgent envelopes through local dispatcher."""
import asyncio
import json
import logging
import tempfile
import os
import secrets
from pathlib import Path
from datetime import datetime,timedelta

from uagents import Agent,Context
from uagents_core.contrib.protocols.chat import ChatMessage,ChatAcknowledgement

from .cards import chat_message,envelope
from .evidence import evidence_path
from .core import Store
from .mesh import create_mesh,NoRegistration,OfflineAgent,CancelControl
from .reasoning import Reasoner
from .service import Services
from .catalogue import SERVICES,provider_services


async def smoke(service="ac"):
    with tempfile.TemporaryDirectory() as tmp:
        reasoner=Reasoner();reasoner.key=None
        store=Store(Path(tmp)/"mesh.db")
        store.seed(expanded=service in ("cleaning","electrical"),full_catalogue=service in ("kitchen_cleaning","sofa_cleaning","washing_machine","furniture"),extended_catalogue=service in ("mattress_cleaning","carpet_cleaning","refrigerator","water_purifier"))
        bureau,agents,store=create_mesh(store,offline=True,reasoner=reasoner,payment_mode="mock")
        probe=OfflineAgent(name="ServiceSetu-Smoke-Customer",seed="servicesetu-public-smoke-customer",registration_policy=NoRegistration(),enable_agent_inspector=False,publish_agent_details=False)
        finished=asyncio.get_running_loop().create_future()
        steps=[]
        transcript=[]
        state={"replacement":False,"booking":None}
        target=agents["concierge"].address

        @probe.on_message(model=ChatAcknowledgement)
        async def ack(ctx:Context,sender:str,msg:ChatAcknowledgement): pass

        @probe.on_message(model=ChatMessage)
        async def receive(ctx:Context,sender:str,msg:ChatMessage):
            try:
                text="\n".join(c.text for c in msg.content if c.type=="text")
                meta=next((c.metadata for c in msg.content if c.type=="metadata"),{})
                transcript.append({"text":text,"metadata":meta})
                payload=json.loads(meta.get("card_payload","{}"))
                kind=meta.get("card_kind")
                if kind=="carousel":
                    if payload.get("title")=="Choose another appointment":
                        steps.append("availability_choices")
                    else:
                        steps.append("recovery_shortlist" if state["replacement"] else "shortlist")
                    await ctx.send(target,chat_message(envelope(json.dumps(payload["items"][0]["primary_cta"]["selection"]))))
                elif kind=="review":
                    steps.append("replacement_approval" if state["replacement"] else "approval")
                    await ctx.send(target,chat_message(envelope(json.dumps(payload["approve_cta"]["selection"]))))
                elif kind=="detail" and "confirmed" in payload["title"]:
                    steps.append("replacement_confirmed" if state["replacement"] else "confirmed")
                    owner=probe.address+":"+str(ctx.session)
                    saved=store.session(owner)
                    if not state["replacement"]:
                        state["booking"]=saved["booking"]
                        state["replacement"]=True
                        pid=store.booking(saved["booking"],owner)["provider"]
                        provider=agents["provider:"+pid]
                        handler=provider._rest_handlers[("POST","/demo/cancel/"+pid)]
                        token=secrets.token_hex(32)
                        prior=os.environ.get("DEMO_CONTROL_TOKEN")
                        os.environ["DEMO_CONTROL_TOKEN"]=token
                        try:
                            rejected=await handler(provider._build_context(),CancelControl(booking=saved["booking"],token="wrong"))
                            assert not rejected.ok
                            cancelled=await handler(provider._build_context(),CancelControl(booking=saved["booking"],token=token))
                            assert cancelled.ok
                            steps.append("authenticated_provider_notice")
                        finally:
                            if prior is None: os.environ.pop("DEMO_CONTROL_TOKEN",None)
                            else: os.environ["DEMO_CONTROL_TOKEN"]=prior
                    else:
                        await ctx.send(target,chat_message(envelope("show what happened")))
                elif text.startswith("Booking history"):
                    assert "You approved the exact quote" in text and "Replacement booking confirmed" in text
                    assert "Provider cancelled" in text and text.count("confirmed with") == 2
                    steps.append("audit")
                    if not finished.done(): finished.set_result({"status":"passed","transport":"actual uAgent local dispatcher", "steps":steps,"transcript":transcript})
                else:
                    raise AssertionError("Unexpected response: "+text)
            except Exception as exc:
                if not finished.done(): finished.set_exception(exc)

        @probe.on_event("startup")
        async def start(ctx:Context):
            slot=next(p for p in store.providers() if service in provider_services(p))["slots"][0]
            slot=(datetime.fromisoformat(slot)+timedelta(days=1)).isoformat()
            package=SERVICES[service].get("package",SERVICES[service]["label"])
            details={"sofa_cleaning":" 3 seats fabric", "washing_machine":" front-loading not spinning", "furniture":" two flat-pack chairs instructions available", "mattress_cleaning":" two queen mattresses", "carpet_cleaning":" synthetic 8 by 6 feet", "refrigerator":" double-door not cooling", "water_purifier":" RO+UV routine maintenance"}.get(service,"")
            await ctx.send(target,chat_message(envelope(package+details+" in Indiranagar Bengaluru "+slot+" under INR 5000")))

        bureau.add(probe)
        # Agent.setup runs actual handlers and queues; no HTTP listener needed.
        for agent in agents.values(): agent.setup()
        probe.setup()
        try:
            result=await asyncio.wait_for(finished,timeout=45)
            Path("artifacts").mkdir(exist_ok=True)
            evidence_path("mesh-proof.json" if service=="ac" else "mesh-proof-"+service+".json").write_text(json.dumps(result,indent=2))
            print(f"PASS real uAgent message flow ({service}):"," -> ".join(result["steps"]))
            return result
        finally:
            pending=[t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in pending: task.cancel()
            await asyncio.gather(*pending,return_exceptions=True)


if __name__=="__main__":
    logging.getLogger("network").setLevel(logging.ERROR)
    asyncio.run(smoke())
