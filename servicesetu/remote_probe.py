"""Actual Agentverse-hosted client → mailbox → local provider mesh proof.

This proves transport, not ASI:One UI discovery/rendering. Uses a temporary
hosted client and only synthetic bookings with the configured mock rail.
API shapes were checked against Fetch.ai's official agentverse relay example.
"""
import argparse
import json
import os
import re
import time
from datetime import datetime,timezone
from pathlib import Path
import requests
from dotenv import load_dotenv
from .core import Store
from .payments import Payments

HOSTING="https://agentverse.ai/v1/hosting/agents"
PRIVATE_STATE=Path("data/remote-probe-state.json")


def client_code(target,request):
    constants="TARGET="+repr(target)+"\nREQUEST="+repr(request)+"\n"
    return constants+'''
import json
from datetime import datetime, timezone
from uuid import uuid4
from uagents import Context, Protocol
from uagents_core.contrib.protocols.chat import ChatMessage, ChatAcknowledgement, TextContent, chat_protocol_spec

proto=Protocol(spec=chat_protocol_spec)

def record(ctx, kind, **data):
    ctx.logger.info("SERVICESETU_PROBE:"+json.dumps(dict(kind=kind,**data)))

async def say(ctx, text):
    await ctx.send(TARGET,ChatMessage(timestamp=datetime.now(timezone.utc),msg_id=uuid4(),content=[TextContent(type="text",text=text)]))

@agent.on_event("startup")
async def start(ctx:Context):
    if ctx.storage.get("started"):
        phase=ctx.storage.get("phase")
        if phase=="complete":record(ctx,"complete",replacement=ctx.storage.get("replacement"))
        elif phase=="failed":record(ctx,"failed",phase=phase,reason="Persisted failed phase")
        else:record(ctx,"waiting",phase=phase)
        return
    ctx.storage.set("started",True)
    ctx.storage.set("phase","shortlist")
    record(ctx,"started")
    await say(ctx,REQUEST)

@proto.on_message(ChatAcknowledgement)
async def acknowledged(ctx:Context,sender:str,msg:ChatAcknowledgement):
    if sender==TARGET:record(ctx,"ack")

@proto.on_message(ChatMessage)
async def response(ctx:Context,sender:str,msg:ChatMessage):
    if sender!=TARGET:return
    await ctx.send(sender,ChatAcknowledgement(timestamp=datetime.now(timezone.utc),acknowledged_msg_id=msg.msg_id))
    phase=ctx.storage.get("phase")
    text="\\n".join(c.text for c in msg.content if c.type=="text")
    metadata=next((c.metadata for c in msg.content if c.type=="metadata"),{})
    record(ctx,"response",phase=phase,text=text,metadata=metadata)
    try:
        payload=json.loads(metadata.get("card_payload","{}"))
        kind=metadata.get("card_kind")
        if phase in ("shortlist","wait_cancellation") and kind=="carousel":
            ctx.storage.set("phase","review" if phase=="shortlist" else "replacement_review")
            await say(ctx,json.dumps(payload["items"][0]["primary_cta"]["selection"]))
        elif phase in ("review","replacement_review") and kind=="review":
            ctx.storage.set("phase","confirmation" if phase=="review" else "replacement_confirmation")
            await say(ctx,json.dumps(payload["approve_cta"]["selection"]))
        elif phase in ("confirmation","replacement_confirmation") and kind=="detail" and "confirmed" in payload["title"]:
            booking=next(row["value"] for row in payload["summary_rows"] if row["label"]=="Booking")
            if phase=="confirmation":
                ctx.storage.set("phase","wait_cancellation")
                record(ctx,"cancel_ready",booking=booking)
            else:
                ctx.storage.set("replacement",booking)
                ctx.storage.set("phase","audit")
                await say(ctx,"show what happened")
        elif phase=="audit" and text.startswith(("Booking history","Immutable timeline")):
            if text.startswith("Booking history"):
                assert "You approved the exact quote" in text and "Replacement booking confirmed" in text and "Provider cancelled" in text
            else:
                assert "customer_approved" in text and "booking_confirmed" in text and "recovery_of" in text
            ctx.storage.set("phase","complete")
            record(ctx,"complete",replacement=ctx.storage.get("replacement"))
        else:
            ctx.storage.set("phase","failed")
            record(ctx,"failed",phase=phase,reason="Unexpected conversation response")
    except Exception as error:
        ctx.storage.set("phase","failed")
        record(ctx,"failed",phase=phase,reason=type(error).__name__)

agent.include(proto,publish_manifest=True)
'''


def events_from_logs(logs):
    events=[]
    for row in logs:
        line=str(row.get("log_entry",""))
        if "SERVICESETU_PROBE:" not in line: continue
        try:events.append(json.loads(line.split("SERVICESETU_PROBE:",1)[1]))
        except ValueError:continue
    return events


def main():
    load_dotenv()
    parser=argparse.ArgumentParser()
    parser.add_argument("--resume",action="store_true")
    parser.add_argument("--refresh-client",action="store_true",help="Apply updated probe code to the same hosted identity, preserving its stored phase")
    parser.add_argument("--wait",type=int,default=120)
    args=parser.parse_args()
    if os.getenv("PAYMENT_MODE","mock")!="mock":raise SystemExit("Remote synthetic probe requires PAYMENT_MODE=mock")
    key=os.getenv("AGENTVERSE_API_KEY")
    if not key:raise SystemExit("Configure AGENTVERSE_API_KEY")
    headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"}
    store=Store(os.getenv("SERVICESETU_DB","data/servicesetu.db"));store.seed()
    addresses=json.loads(Path("artifacts/agent-addresses.json").read_text())
    PRIVATE_STATE.parent.mkdir(exist_ok=True)
    def call(method,path="",**kwargs):
        response=requests.request(method,HOSTING+path,headers=headers,timeout=30,**kwargs)
        response.raise_for_status()
        return response
    if args.resume:
        state=json.loads(PRIVATE_STATE.read_text())
        if state.get("terminal"):raise SystemExit("Recorded probe is terminal; inspect its evidence before creating another")
        address=state["address"]
        print("Resuming existing hosted probe:",address,flush=True)
        if args.refresh_client:
            call("POST","/"+address+"/stop")
            stopped=False
            for _ in range(10):
                data=call("GET").json()
                items=data.get("items",[]) if isinstance(data,dict) else data
                entry=next((e for e in items if e.get("address")==address),{})
                if entry and not entry.get("running"):
                    stopped=True;break
                time.sleep(2)
            if not stopped:raise SystemExit("Hosted job is still stopping; retain its handle and inspect before another update")
            slot=store.provider("p1")["slots"][0]
            request=f"AC service in Indiranagar Bengaluru at {slot} under INR 1000"
            files=[{"language":"python","name":"agent.py","value":client_code(addresses["concierge"],request)}]
            call("PUT","/"+address+"/code",json={"code":json.dumps(files)})
            call("POST","/"+address+"/start")
            print("Updated result logging on the same hosted identity",flush=True)
    else:
        if PRIVATE_STATE.exists() and not json.loads(PRIVATE_STATE.read_text()).get("terminal"):
            raise SystemExit("An existing probe is pending. Use --resume; do not restart it.")
        address=call("POST",json={"name":"ServiceSetu remote proof"}).json()["address"]
        state={"address":address,"terminal":False,"cancelled":False,"created_at":datetime.now(timezone.utc).isoformat()}
        PRIVATE_STATE.write_text(json.dumps(state,indent=2));os.chmod(PRIVATE_STATE,0o600)
        slot=store.provider("p1")["slots"][0]
        request=f"AC service in Indiranagar Bengaluru at {slot} under INR 1000"
        files=[{"language":"python","name":"agent.py","value":client_code(addresses["concierge"],request)}]
        call("PUT","/"+address+"/code",json={"code":json.dumps(files)})
        call("POST","/"+address+"/start")
        print("Started temporary hosted transport probe:",address,flush=True)
    deadline=time.monotonic()+args.wait
    captured=[]
    terminal=None
    while time.monotonic()<deadline:
        response=call("GET","/"+address+"/logs/latest")
        logs=response.json()
        events=events_from_logs(logs if isinstance(logs,list) else [])
        captured=events or captured
        ready=next((e for e in events if e["kind"]=="cancel_ready"),None)
        waiting=next((e for e in events if e["kind"]=="waiting" and e.get("phase")=="wait_cancellation"),None)
        if ready is None and waiting and not state["cancelled"]:
            with store.connect() as db:
                candidates=db.execute("SELECT id FROM bookings WHERE owner LIKE ? AND state='confirmed'",(address+":%",)).fetchall()
            if len(candidates)==1:ready={"booking":candidates[0]["id"]}
        if ready and not state["cancelled"]:
            with store.connect() as db:
                row=db.execute("SELECT * FROM bookings WHERE id=?",(ready["booking"],)).fetchone()
            if not row or row["owner"].rsplit(":",1)[0]!=address:
                raise RuntimeError("Remote probe booking is not owned by this hosted client")
            control=requests.post("http://127.0.0.1:"+os.getenv("SERVICESETU_PORT","8000")+"/demo/cancel/"+row["provider"],
                json={"booking":row["id"],"token":os.getenv("DEMO_CONTROL_TOKEN")},timeout=15)
            control.raise_for_status()
            if not control.json().get("ok"):raise RuntimeError("Authenticated cancellation control failed")
            state["cancelled"]=True;PRIVATE_STATE.write_text(json.dumps(state,indent=2))
            print("Remote booking confirmed; provider cancellation triggered",flush=True)
        complete=next((e for e in events if e["kind"]=="complete"),None)
        failed=next((e for e in events if e["kind"]=="failed"),None)
        if complete or failed:
            terminal="passed" if complete else "failed";break
        time.sleep(5)
    # Observation timeout is not terminal: keep the same remote job for --resume.
    if not terminal:
        print("Probe remains pending. Resume this same hosted job with --resume.",flush=True)
        return
    state["terminal"]=terminal
    PRIVATE_STATE.write_text(json.dumps(state,indent=2))
    # Release only synthetic bookings owned by this scratch client.
    with store.connect() as db:
        bookings=db.execute("SELECT * FROM bookings WHERE owner LIKE ? AND state IN ('requested','held','confirmed')",(address+":%",)).fetchall()
    for b in bookings:Payments(store,mode="mock").cancel(b["owner"],b["id"],actor="system:proof_cleanup")
    call("POST","/"+address+"/stop")
    call("DELETE","/"+address)
    state["removed"]=True;PRIVATE_STATE.write_text(json.dumps(state,indent=2))
    evidence={"status":terminal,"verified_at":datetime.now(timezone.utc).isoformat(),"transport":"Agentverse hosted client → mailbox → local provider mesh",
              "test_data":True,"asi_ui_verified":False,"temporary_probe_removed":True,"events":captured}
    with store.connect() as db:
        records=db.execute("SELECT * FROM bookings WHERE owner LIKE ?",(address+":%",)).fetchall()
    evidence["booking_timelines"]=[{"booking":dict(b),"timeline":store.timeline(b["owner"],b["id"])} for b in records]
    evidence["all_synthetic_slots_released"]=all(b["state"]=="cancelled" for b in records)
    raw=re.sub(r"at_[a-f0-9]{32}","[redacted approval token]",json.dumps(evidence,indent=2))
    Path("artifacts/remote-mailbox-proof.json").write_text(raw)
    print(terminal.upper()+" remote mailbox flow; temporary hosted client removed",flush=True)
    if terminal!="passed":raise SystemExit(1)


if __name__=="__main__":main()
