"""Reviewable registration manifest; explicit apply only, no key logging."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from datetime import datetime,timezone

from uagents_core.config import AgentverseConfig
from uagents_core.types import AgentMetadata
from uagents_core.utils.registration import (register_agent,RegistrationRequestCredentials,AgentverseRegistrationRequest,AgentverseRequestError)
from .evidence import evidence_path, evidence_input, publishing_evidence
from .mesh import create_mesh,seed_phrase,profile


def write_manifest(manifest):
    Path("artifacts").mkdir(exist_ok=True)
    evidence_path("registration-manifest.json").write_text(json.dumps(manifest,indent=2))
    if not publishing_evidence(): return
    readme=Path("README.md")
    if not readme.exists(): return
    start="<!-- generated-agent-addresses:start -->";end="<!-- generated-agent-addresses:end -->"
    table=start+"\n\n| Agent | Address | Public profile |\n| --- | --- | --- |\n"
    rows=[]
    for entry in manifest:
        link=f"[Profile]({entry['profile_url']})" if entry.get("profile_url") else "Not verified"
        rows.append(f"| {entry['name']} | `{entry['address']}` | {link} |")
    table+="\n".join(rows)+"\n\n"+end
    text=readme.read_text()
    if start in text and end in text:
        before,rest=text.split(start,1);_,after=rest.split(end,1)
        text=before+table+after
    else: text=text.replace("## Register and try it in ASI:One",table+"\n\n## Register and try it in ASI:One",1)
    readme.write_text(text)


def verify_registrations(manifest,key,config):
    """Inspect the account and public Almanac; never infer state from a dry run."""
    import requests
    response=requests.get(config.agents_api,headers={"Authorization":"Bearer "+key},timeout=20)
    response.raise_for_status()
    owned={entry["address"]:entry for entry in response.json()}
    now=datetime.now(timezone.utc).isoformat()
    for entry in manifest:
        if entry["address"] not in owned:
            entry["registration_status"]="not_verified"
            entry.pop("profile_url",None)
            continue
        entry["profile_url"]="https://agentverse.ai/agents/details/"+entry["address"]+"/profile"
        entry["handle"]=owned[entry["address"]].get("handle")
        public=requests.get(config.almanac_api+"/agents/"+entry["address"],timeout=20)
        status=public.json().get("status") if public.status_code==200 else "unverified"
        entry["registration_status"]="registered_"+status
        entry["verified_at"]=now
    write_manifest(manifest)
    print("Verified registered profiles:",sum(entry["address"] in owned for entry in manifest),"of",len(manifest))
    print("Verified active Almanac entries:",sum(entry["registration_status"]=="registered_active" for entry in manifest))
    return manifest


def prepare():
    from dotenv import load_dotenv
    load_dotenv()
    # Offline construction creates the SAME seed-derived identities, no registration.
    # A dry run must not publish manifests or contact Agentverse.
    old=os.environ.get("SERVICESETU_MAILBOX")
    os.environ["SERVICESETU_MAILBOX"]="false"
    try: _,agents,_=create_mesh(offline=True)
    finally:
        if old is None: os.environ.pop("SERVICESETU_MAILBOX",None)
        else: os.environ["SERVICESETU_MAILBOX"]=old
    config=AgentverseConfig()
    manifest_path=evidence_input("registration-manifest.json")
    previous={}
    if manifest_path.exists():
        try: previous={entry["address"]:entry for entry in json.loads(manifest_path.read_text())}
        except (ValueError,KeyError,TypeError): pass
    manifest=[]
    for role,agent in agents.items():
        prior=previous.get(agent.address,{})
        entry={"role":role,"name":agent.name,"address":agent.address,
            "endpoint":config.mailbox_endpoint,"protocols":list(agent.protocols),
            "registration_status":prior.get("registration_status","not_verified"),"readme":profile(role)}
        entry.update({k:prior[k] for k in ("profile_url","verified_at","handle") if k in prior})
        manifest.append(entry)
    Path("artifacts").mkdir(exist_ok=True)
    evidence_path("agent-addresses.json").write_text(json.dumps({r["role"]:r["address"] for r in manifest},indent=2))
    write_manifest(manifest)
    print(f"Prepared {len(manifest)} seed-derived identities. This does not register agents.")
    return manifest


def main():
    from dotenv import load_dotenv
    load_dotenv()
    parser=argparse.ArgumentParser(description="Prepare or register ServiceSetu mailbox agents")
    parser.add_argument("--apply",action="store_true",help="Create profiles and mailboxes in your Agentverse account")
    parser.add_argument("--only",action="append",help="Register only this role; repeat for multiple roles")
    parser.add_argument("--verify",action="store_true",help="Read current account and public Almanac state")
    args=parser.parse_args()
    manifest=prepare()
    if not args.apply and not args.verify: return
    key=os.getenv("AGENTVERSE_API_KEY")
    if not key: raise SystemExit("Set AGENTVERSE_API_KEY in .env before registration")
    seed=seed_phrase()
    config=AgentverseConfig()
    if args.verify:
        verify_registrations(manifest,key,config)
        if not args.apply: return
    for entry in manifest:
        role=entry["role"]
        if args.only and role not in args.only: continue
        try:
            request=AgentverseRegistrationRequest(name=entry["name"],endpoint=entry["endpoint"],protocols=entry["protocols"],
                handle="servicesetu" if role=="concierge" else None,
                type="mailbox",active=False,readme=entry["readme"],description="ServiceSetu test-data concierge" if role=="concierge" else "Internal ServiceSetu specialist; route customers to Concierge",
                metadata=AgentMetadata(is_public=True,categories=["innovationlab","hackathon"]))
            credentials=RegistrationRequestCredentials(agentverse_api_key=key,agent_seed_phrase=seed+":"+role)
            success=register_agent(request,config,credentials)
            if not success: raise AgentverseRequestError("Registration returned false")
            entry["registration_status"]="registered_inactive_until_runtime"
            write_manifest(manifest)
            print("Registered:",entry["name"],entry["address"])
        except AgentverseRequestError as error:
            entry["registration_status"]="failed"
            evidence_path("registration-manifest.json").write_text(json.dumps(manifest,indent=2))
            # Do not print raw gateway/auth exceptions; private run logs can be inspected.
            raise SystemExit(f"Registration failed for {entry['name']} ({type(error).__name__}); earlier registrations are preserved. Retry with the same seed.")
    evidence_path("registration-manifest.json").write_text(json.dumps(manifest,indent=2))
    print("Now set SERVICESETU_MAILBOX=true and run python -m servicesetu mesh. Live ASI:One discovery still needs testing.")


if __name__=="__main__": main()
