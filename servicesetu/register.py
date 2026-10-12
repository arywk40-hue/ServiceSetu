"""Reviewable registration manifest; explicit apply only, no key logging."""
import argparse
import asyncio
import json
import os
from pathlib import Path

from uagents_core.config import AgentverseConfig
from uagents_core.utils.registration import (register_agent,RegistrationRequestCredentials,AgentverseRegistrationRequest,AgentverseRequestError)
from .mesh import create_mesh,seed_phrase,profile


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
    manifest=[]
    for role,agent in agents.items():
        manifest.append({"role":role,"name":agent.name,"address":agent.address,
            "endpoint":config.mailbox_endpoint,"protocols":list(agent.protocols),
            "registration_status":"not_verified","readme":profile(role)})
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/agent-addresses.json").write_text(json.dumps({r["role"]:r["address"] for r in manifest},indent=2))
    Path("artifacts/registration-manifest.json").write_text(json.dumps(manifest,indent=2))
    readme=Path("README.md")
    if readme.exists():
        start="<!-- generated-agent-addresses:start -->"
        end="<!-- generated-agent-addresses:end -->"
        text=readme.read_text()
        table=start+"\n\n| Agent | Seed-derived address (registration pending) |\n| --- | --- |\n"
        table+="\n".join(f"| {entry['name']} | `{entry['address']}` |" for entry in manifest)+"\n\n"+end
        if start in text and end in text:
            before,rest=text.split(start,1)
            _,after=rest.split(end,1)
            text=before+table+after
        else:
            text=text.replace("## Register and try it in ASI:One",table+"\n\n## Register and try it in ASI:One",1)
        readme.write_text(text)
    print("Prepared 13 seed-derived identities. This does not register agents.")
    return manifest


def main():
    from dotenv import load_dotenv
    load_dotenv()
    parser=argparse.ArgumentParser(description="Prepare or register ServiceSetu mailbox agents")
    parser.add_argument("--apply",action="store_true",help="Create profiles and mailboxes in your Agentverse account")
    args=parser.parse_args()
    manifest=prepare()
    if not args.apply: return
    key=os.getenv("AGENTVERSE_API_KEY")
    if not key: raise SystemExit("Set AGENTVERSE_API_KEY in .env before registration")
    seed=seed_phrase()
    config=AgentverseConfig()
    for entry in manifest:
        role=entry["role"]
        try:
            request=AgentverseRegistrationRequest(name=entry["name"],endpoint=entry["endpoint"],protocols=entry["protocols"],
                type="mailbox",active=False,readme=entry["readme"],description="ServiceSetu test-data concierge" if role=="concierge" else "Internal ServiceSetu specialist; route customers to Concierge",
                metadata={"is_public":"True","categories":["innovationlab","hackathon"]})
            credentials=RegistrationRequestCredentials(agentverse_api_key=key,agent_seed_phrase=seed+":"+role)
            success=register_agent(request,config,credentials)
            if not success: raise AgentverseRequestError("Registration returned false")
            entry["registration_status"]="registered_inactive_until_runtime"
            print("Registered:",entry["name"],entry["address"])
        except AgentverseRequestError:
            entry["registration_status"]="failed"
            Path("artifacts/registration-manifest.json").write_text(json.dumps(manifest,indent=2))
            raise SystemExit(f"Registration failed for {entry['name']}; check credentials and Agentverse. Earlier registrations are recorded; retry with the same seed.")
    Path("artifacts/registration-manifest.json").write_text(json.dumps(manifest,indent=2))
    print("Now set SERVICESETU_MAILBOX=true and run python -m servicesetu mesh. Live ASI:One discovery still needs testing.")


if __name__=="__main__": main()
