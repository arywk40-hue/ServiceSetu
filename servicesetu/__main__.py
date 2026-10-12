import argparse
import asyncio
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

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
        Path("artifacts/demo-transcript.json").write_text(json.dumps({"test_data":True,"transcript":transcript,"role_calls":bus.calls},indent=2))
        print("\nSaved artifacts/demo-transcript.json")


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
            asyncio.run(smoke())
            report["mesh"]="passed"
        elif result.wasSuccessful() and include_mesh:
            print("Mesh proof not run: install the fetch extras and use .venv/bin/python.")
        Path("artifacts").mkdir(exist_ok=True)
        Path("artifacts/proof-results.json").write_text(json.dumps(report,indent=2))
        if not result.wasSuccessful(): raise SystemExit(1)


def main():
    parser=argparse.ArgumentParser(description="ServiceSetu seeded booking prototype")
    parser.add_argument("command",choices=["prove","demo","chat","mesh","prepare"])
    parser.add_argument("--core-only",action="store_true")
    args=parser.parse_args()
    if args.command=="prove": prove(not args.core_only)
    elif args.command=="demo": asyncio.run(demo())
    elif args.command=="chat": asyncio.run(chat())
    elif args.command=="mesh":
        from .mesh import main as run_mesh
        run_mesh()
    else:
        from .register import prepare
        prepare()


if __name__=="__main__": main()
