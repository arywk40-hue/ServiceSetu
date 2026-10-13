"""Small synthetic live ASI1 probe. Fallback never counts as a successful proof."""
import asyncio
import json
import os
import tempfile
from pathlib import Path
from datetime import datetime,timezone
from dotenv import load_dotenv
from .core import Store
from .reasoning import Reasoner


async def verify():
    load_dotenv()
    reasoner=Reasoner()
    if not reasoner.key: raise SystemExit("Configure ASI1_API_KEY in private .env")
    with tempfile.TemporaryDirectory() as tmp:
        store=Store(Path(tmp)/"asi1-proof.db");store.seed()
        slot=store.provider("p1")["slots"][0]
        request=f"Book AC servicing in Indiranagar, Bengaluru at {slot}, maximum budget INR 1000."
        parsed=await reasoner.parse(request,store.clock())
        if reasoner.last_source.get("parse")!="asi1": raise SystemExit("Live ASI1 intake failed; offline fallback does not prove integration")
        job=store.normalize_job(parsed)
        choices,excluded=store.match(job)
        quotes=[store.quote("synthetic-live-probe",p["id"],job["slot"]) for p in choices]
        explanation=await reasoner.explain(quotes,excluded)
        if reasoner.last_source.get("explain")!="asi1": raise SystemExit("Live ASI1 comparison failed; offline fallback does not prove integration")
        evidence={"verified_at":datetime.now(timezone.utc).isoformat(),"test_data":True,
                  "model":os.getenv("ASI1_MODEL","asi1"),"source":dict(reasoner.last_source),
                  "request":request,"validated_job":job,"explanation":explanation,
                  "quotes_compared":[q["id"] for q in quotes],"excluded":excluded}
        Path("artifacts").mkdir(exist_ok=True)
        Path("artifacts/live-asi1-proof.json").write_text(json.dumps(evidence,indent=2))
        print("PASS live ASI1 intake and provider comparison;",len(quotes),"seeded provider quotes compared")


if __name__=="__main__": asyncio.run(verify())
