import argparse
import asyncio
import importlib.util
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from .evidence import evidence_path
from .core import Store
from .conversation import Conversation
from .service import Services,LocalBus
from .reasoning import Reasoner


def local(store):
    reasoner=Reasoner();reasoner.key=None
    return Conversation(store,reasoner),LocalBus(Services(store,payment_mode="mock"))


async def demo():
    with tempfile.TemporaryDirectory() as tmp:
        store=Store(Path(tmp)/"demo.db");store.seed()
        conversation,bus=local(store)
        owner="demo-customer:demo-session"
        transcript=[]
        async def say(text):
            reply=await conversation.handle(owner,text,bus)
            transcript.append({"customer":text,"agent":reply})
            print("\nCUSTOMER:",text)
            print("SERVICESETU:",reply["text"])
            return reply
        await say("AC service in Indiranagar Bengaluru tomorrow 10am under INR 1000")
        state=store.session(owner)
        reply=await say("select "+state["quotes"][0])
        approve=json.loads(reply["metadata"]["card_payload"])["approve_cta"]["selection"]
        await say(json.dumps(approve))
        bid=store.session(owner)["booking"]
        Services(store,payment_mode="mock").payments.cancel(owner,bid,actor="provider:p1")
        print("\nDEMO CONTROL: CoolCare AC cancels; simulated payment reversed.")
        await say("recover")
        reply=await say("select "+store.session(owner)["quotes"][0])
        await say(json.dumps(json.loads(reply["metadata"]["card_payload"])["approve_cta"]["selection"]))
        await say("show what happened")
        Path("artifacts").mkdir(exist_ok=True)
        evidence_path("demo-transcript.json").write_text(json.dumps({"test_data":True,"transcript":transcript,"role_calls":bus.calls},indent=2))
        print("\nSaved", evidence_path("demo-transcript.json"))


async def chat():
    store=Store(os.getenv("SERVICESETU_DB","data/servicesetu.db"));store.seed()
    conversation,bus=local(store)
    # New session each invocation prevents a fresh terminal inheriting approval.
    from uuid import uuid4
    owner="terminal:"+str(uuid4())
    print("ServiceSetu local demo · simulated payments. Type help, or quit to exit.")
    while True:
        text=await asyncio.to_thread(input,"You: ")
        if text.lower() in ("quit","exit"): break
        reply=await conversation.handle(owner,text,bus)
        print(reply["text"])


def prove(include_mesh=True):
    from unittest.mock import patch
    class Evidence(unittest.TextTestResult):
        records=[]
        def addSuccess(self,test):
            super().addSuccess(test);self.records.append({"scenario":test.id(),"status":"passed"})
        def addFailure(self,test,err):
            super().addFailure(test,err);self.records.append({"scenario":test.id(),"status":"failed"})
        def addError(self,test,err):
            super().addError(test,err);self.records.append({"scenario":test.id(),"status":"error"})
    with patch.dict(os.environ,{"PAYMENT_MODE":"mock","ASI1_API_KEY":""}):
        suite=unittest.defaultTestLoader.discover("tests")
        result=unittest.TextTestRunner(verbosity=2,resultclass=Evidence).run(suite)
        report={"test_data":True,"passed":result.wasSuccessful(),"scenarios":result.records,"mesh":"not_run"}
        if result.wasSuccessful() and include_mesh and importlib.util.find_spec("uagents"):
            from .mesh_smoke import smoke
            for service in ("ac","cleaning","electrical","kitchen_cleaning","sofa_cleaning","washing_machine","furniture","mattress_cleaning","carpet_cleaning","refrigerator","water_purifier"):
                asyncio.run(smoke(service))
            report["mesh"]="passed"
        elif result.wasSuccessful() and include_mesh:
            print("Mesh proof not run: install the fetch extras and use .venv/bin/python.")
        Path("artifacts").mkdir(exist_ok=True)
        evidence_path("proof-results.json").write_text(json.dumps(report,indent=2))
        if not result.wasSuccessful(): raise SystemExit(1)


def main():
    parser=argparse.ArgumentParser(description="ServiceSetu seeded booking prototype")
    parser.add_argument("command",choices=["prove","demo","chat","mesh","prepare","seed-demo"])
    parser.add_argument("--core-only",action="store_true")
    parser.add_argument("--db",help="New database path for seed-demo; existing files are never overwritten")
    parser.add_argument("--days",type=int,choices=range(1,15),help="Days of demo appointments, starting tomorrow; default 3 (seed-demo only)")
    parser.add_argument("--expanded",action="store_true",help="Include bathroom cleaning and electrical inspection providers in a NEW demo database")
    parser.add_argument("--full-catalogue",action="store_true",help="Include all eight service packages in a NEW demo database")
    parser.add_argument("--extended-catalogue",action="store_true",help="Include twelve service packages using the same sixteen provider identities")
    parser.add_argument("--from-db",help="Copy an existing demo with SQLite backup before adding the full catalogue; original remains unchanged")
    args=parser.parse_args()
    if args.command!="seed-demo" and (args.db is not None or args.days is not None or args.expanded or args.full_catalogue or args.extended_catalogue or args.from_db):
        parser.error("Demo seed options are only supported with seed-demo; use SERVICESETU_DB for the runtime")
    if args.command=="seed-demo":
        if not args.db: parser.error("seed-demo requires --db with a new database path")
        path=Path(args.db)
        if path.exists(): parser.error("Database already exists; choose a new path to preserve saved bookings")
        if args.from_db:
            source=Path(args.from_db)
            if not (args.full_catalogue or args.extended_catalogue) or not source.is_file():
                parser.error("--from-db requires a catalogue option and an existing source demo database")
            path.parent.mkdir(parents=True,exist_ok=True)
            with closing(sqlite3.connect(source.resolve().as_uri()+"?mode=ro",uri=True)) as original:
                with closing(sqlite3.connect(path)) as destination: original.backup(destination)
        store=Store(path)
        store.seed(days=args.days or 3,expanded=args.expanded,full_catalogue=args.full_catalogue,extended_catalogue=args.extended_catalogue)
        if args.from_db:store.extend_demo_offerings(extended_catalogue=args.extended_catalogue)
        print("Created fictional demo appointments in",path)
        for slot in store.provider("p1")["slots"]: print(slot)
        print("Existing databases, credentials and agent identities were not changed.")
    elif args.command=="prove": prove(not args.core_only)
    elif args.command=="demo": asyncio.run(demo())
    elif args.command=="chat": asyncio.run(chat())
    elif args.command=="mesh":
        from .mesh import main as run_mesh
        run_mesh()
    else:
        from .register import prepare
        prepare()


if __name__=="__main__": main()
