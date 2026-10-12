"""Local provider demo control; never prints the authentication token."""
import argparse
import json
import os
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1]/".env")
parser=argparse.ArgumentParser()
parser.add_argument("provider",choices=[f"p{i}" for i in range(1,7)])
parser.add_argument("booking")
args=parser.parse_args()
token=os.getenv("DEMO_CONTROL_TOKEN")
if not token: raise SystemExit("Configure DEMO_CONTROL_TOKEN in .env")
port=int(os.getenv("SERVICESETU_PORT","8000"))
data=json.dumps({"booking":args.booking,"token":token}).encode()
request=urllib.request.Request(f"http://127.0.0.1:{port}/demo/cancel/{args.provider}",data=data,headers={"Content-Type":"application/json"},method="POST")
with urllib.request.urlopen(request,timeout=10) as response: print(response.read().decode())
