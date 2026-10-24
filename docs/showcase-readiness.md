# ServiceSetu showcase readiness

Checked 23 October 2026 against the ASI:One Agent Challenge statement supplied by the owner. The primary demonstration uses fictional providers and `PAYMENT_MODE=mock`; all customer actions stay inside ASI:One. A simulated confirmation is not a real service reservation or a gateway transaction.

**Latest October 24 result:** a new authenticated conversation, **Book TomTom Plumbers And AC Service**, returned four live TomTom Mandi discoveries and completed a new mock booking/cancellation/replacement journey. Its full **18-event** history rendered. The successful branch used 25 October 2026 at 10 AM IST, INR 1,000 maximum: CoolCare INR 699 was approved and confirmed, cancelled by the authenticated local operator control and simulated-refunded; Breeze INR 749 required fresh approval and was confirmed. Read-only backend checks independently matched those states and payment mode `mock`. Earlier quotes expired safely and one short address was corrected. This is a successful fresh journey after retries, not a first-attempt uninterrupted recording or a root-cause fix for transport failures.

A **4:44 silent edited walkthrough** was generated from actual captures of this new conversation, encoded as H.264 at 1600×900 with no audio. Raw captures and the local video are excluded from Git. The owner adds voiceover and shares this same conversation publicly; a verified public shared-chat URL remains outstanding. The earlier October 23 failed fresh attempt and the older 17-event completed conversation remain historical evidence.

The [official hackpack](https://innovationlab.fetch.ai/events/hackathons/fetch-a-thon-3/hackpack), rechecked October 24, specifies a **3–5 minute video** and **mandatory submission through the ASI:One event dashboard Project Submission Agent**. Use Devpost too only if separately requested by organizers.

## October 24 publication review

The remaining Google Places work originally added in Antigravity was preserved and reviewed for publication. It now has safe upstream error handling, HTTPS Google Maps link validation, bounded results, preservation of constrained booking requests, and optional HTTP dependency loading. **343 core tests passed in 34.247 seconds**, with zero failures/skips; the 23 targeted Google Places tests and the bounded local AC uAgent smoke also passed. Keep `GOOGLE_PLACES_API_KEY` unset: no live Google call, billing setup or Google card acceptance is claimed. The single October 24 runtime was reloaded with an explicit empty Google key, unchanged identities/database and mock payments. See the [timed video script and actual prior chat history](video-script.md).

The latest fresh journey proves delivery for that run. It does not establish a permanent mailbox fix or continuous uptime. An overnight provider mailbox log included HTTP 401 credential validation in addition to timeouts. Fresh signed read-only checks for Concierge, Matching and that provider returned HTTP 200 (0.47, 0.99 and 0.53 seconds). No additional email service is required: this mailbox is agent transport, not SMTP or Gmail.

## Mandatory requirements and deliverables

The owner cannot keep a laptop running during judging. A persistent remote runtime is another unresolved availability requirement. [Free hosting options and migration steps](hosting.md) document the checked limits; no free VM, cloud deployment or remote restart/persistence check has been completed. Existing recorded evidence does not establish fresh availability while the laptop is off.

| Requirement | Evidence and present status |
| --- | --- |
| Defined real-world problem | Coordinate a local service appointment and recover when its provider cancels. The showcase demonstrates this with fictional AC providers in Indiranagar, Bengaluru. |
| Multi-step reasoning and orchestration | Concierge gathers constraints and coordinates Matching, Verification, independent Provider agents, Booking, Payment, Recovery and Trust Monitor. Current local AC uAgent flow passed through both approvals, cancellation, replacement and audit. |
| Registered on Agentverse | All 13 existing public Almanac entries returned active. Expected protocol digests matched after normalizing the API's omitted `proto:` prefix. One booking-agent request timed out and passed one retry; this is not continuous-uptime evidence. |
| Agent Chat Protocol | Concierge advertises the ACP digest. The signed-in ASI:One client rendered provider comparison, optional address and exact quote review cards. The prior full flow also rendered confirmation, cancellation/recovery and history. |
| Discoverable and usable in ASI:One | The public Concierge Agentverse profile rendered without Agentverse sign-in, showed AgentChatProtocol v0.3.0 and AgentPaymentProtocol v0.1.0, and exposed a Chat with Agent link targeting ASI:One. Selecting `@servicesetu` worked in the authenticated ASI:One account. The direct [ASI:One Concierge profile](https://asi1.ai/ai/agent1q02ftm6eu39lw0vc5kh3uhr4gtkkeqd6jpcaxzn4gyyrc2ac0p9ecvl39sz) is documented. Broad search from a fresh ASI:One account remains unverified. |
| Primary workflow inside one conversation | A new October 24 mock journey completed after fresh quotes, with exact approval, confirmation, provider cancellation/reversal, fresh replacement approval, confirmation and all 18 history events. Earlier expiry and address validation remained enforced. No custom customer frontend is required. Provider cancellation uses an authenticated operator simulation. |
| Public GitHub with run/test instructions | [arywk40-hue/ServiceSetu](https://github.com/arywk40-hue/ServiceSetu) was verified public through GitHub. Source commits `78e14e3` and `0ddd83a` contain FET and MCP work. The October 24 publication review adds the preserved optional Google Places adapter; it is not part of those older FET/MCP commits. |
| Public ASI:One Shared Chat URL | **Unresolved.** The completed private conversation is not a public submission link. The Share action did not expose a verifiable public URL. Obtain the public link through ASI:One and check it without the owner's authenticated session. Do not publish a private `/chat/` link. |
| Agentverse profiles | [Concierge profile](https://agentverse.ai/agents/details/agent1q02ftm6eu39lw0vc5kh3uhr4gtkkeqd6jpcaxzn4gyyrc2ac0p9ecvl39sz/profile); all 13 public profile URLs and unchanged messaging identities are in [README](../README.md) and the [registration manifest](../artifacts/registration-manifest.json). |
| Short demo video | A local 4:44 silent edited walkthrough of actual new ASI:One captures is generated and checked. The owner still adds voice, uploads the final video and verifies its public URL. It is not continuous real-time footage. |
| Brief submission description | Ready below. Final submission remains an owner action through the mandatory ASI:One event dashboard; follow additional organizer instructions. |

## Historical October 23 delivery diagnosis

The existing process was the only ServiceSetu mesh. Its logs reported `Connection timeout` on AgentVerse mailbox polling and ASI:One message submission, `Server disconnected`, destination-resolution errors, and HTTP 503 responses containing `upstream connect error or disconnect/reset before headers`. No signed-mailbox 401/403 rejection was observed. An unauthenticated agents API returning 401 is expected and is not evidence that the configured identity was rejected.

Bounded signed read-only checks subsequently returned HTTP 200 for Concierge, Matching and Payment mailboxes in under one second, with active Almanac records. The official [Fetch status feed](https://status.fetch.ai/) reported all systems operational and no active incident at the check. These observations show intermittent connectivity/service failures; they do not identify a confirmed global outage or a proven local network cause.

After stopping the old process, one mock mailbox mesh was started against a **new isolated database**. Startup reported 13 mailbox clients and 13 active registrations. The old database and identity configuration were retained. The fresh ASI:One chat rendered both eligible AC providers, the address step and a review. The first review failed to arrive before expiry. A fresh quote was requested; its review arrived, but approval reached an expired hold and the client displayed `Hold expired; refresh before approving`. Read-only backend inspection found two cancelled, unapproved bookings with payment state `none` and zero payment rows. No provider cancellation was triggered in this incomplete attempt.

This earlier attempt was blocked by round-trip delivery during the protected hold window. The later October 24 journey succeeded after fresh quotes. Reliable future delivery remains a concern. Never extend an expired quote, silently approve, confirm from a database event alone, or label a local smoke test as an ASI:One checkout.

## Verification results

| Check | Actual result |
| --- | --- |
| October 23 workspace core suite | 336 tests passed in 28.752 seconds; 0 failed, 0 skipped. Includes 16 preserved local Google Places tests. |
| First sandboxed core run | 336 tests ran; 4 errors because the sandbox denied provider-inbox localhost binding. Rerun with loopback access passed. This first run was not counted as a pass. |
| Current local AC message smoke | Passed availability, shortlist, address, approval, confirmation, customer/provider messages, authenticated provider cancellation, replacement shortlist, fresh approval, replacement confirmation and audit. Uses real local uAgent envelopes with Almanac version lookups stubbed; it is not a live ASI:One run. |
| Installed dependencies | `uv pip check` reported 66 compatible packages. |
| Public registration read checks | All 13 active and expected protocols present after one bounded retry of an Almanac timeout. |
| Private configuration scan | No configured seed/key/token value matched the 118 tracked working files. No tracked `.env`, database or token file; no private ASI:One chat URL pattern found in tracked files. This is a scoped scan, not a guarantee about every possible secret. |
| Full catalogue mesh proof | Not rerun here. A previous additional catalogue rerun stalled after nine flows and was stopped; do not claim that run completed all 14. |

Private local reports remain under ignored `artifacts/local/`. No customer data, approval tokens or private chat links are included in this document.

## Exact setup and fresh demonstration

Run from the existing checkout with its private configuration and unchanged seed:

```sh
uv pip install --python .venv/bin/python -e '.[fetch,communications,external]'
.venv/bin/python -m servicesetu prove --core-only
```

To preserve prior bookings, use a new database filename that does not already exist:

```sh
.venv/bin/python -m servicesetu seed-demo --db data/showcase-NEXT.db --days 3
SERVICESETU_DB=data/showcase-NEXT.db SERVICESETU_MAILBOX=true PAYMENT_MODE=mock .venv/bin/python -m servicesetu mesh
```

For this verification, the new file is `data/showcase-readiness-20261023.db` and the runtime uses that file. It already exists; do not run seed-demo over it. Start exactly one mesh for the existing identities. The private `.env` still has mailbox disabled by default, so keep the explicit `SERVICESETU_MAILBOX=true` runtime override. Do not run another copy beside the current process.

In one conversation addressed to `@servicesetu`:

1. Send `AC service in Indiranagar Bengaluru tomorrow 10am under INR 1000`.
2. Compare CoolCare AC at INR 699 and Breeze AC at INR 749. Both are fictional. Explain that Lapsed AC is excluded for expired mock credentials.
3. Choose **Review quote** and **Skip for now** for the optional address. Review scope, exclusions, exact total, appointment and expiry.
4. Choose **Approve test payment** only on the current valid review. Observe **Simulated · no gateway charge** and a rendered confirmed booking. If expired, request fresh providers and approve the new review.
5. Only after confirmation, the operator obtains the actual assigned provider and booking ID privately, then runs:

   ```sh
   .venv/bin/python scripts/cancel_provider.py p1 BOOKING_ID
   ```

6. Observe the cancellation notice and simulated reversal in that same chat. Use `status`, then `recover` if a notice is missed. Review the eligible replacement within the same service, location, appointment and INR 1,000 budget.
7. Explicitly approve its **fresh** review. Observe a new simulated confirmation, then send `show what happened`. Verify the full history includes both approvals, cancellation/reversal and replacement confirmation.
8. Check messaging, completion and problem acknowledgement on a separate synthetic booking if those actions would change the recording's final confirmed state. The local suite covers ownership and provider access boundaries.

The local AC smoke can be repeated independently:

```sh
.venv/bin/python - <<'PY'
import asyncio, os, signal
from dotenv import load_dotenv
from unittest.mock import patch
load_dotenv('.env')
from servicesetu.mesh_smoke import smoke
signal.alarm(100)
with patch.dict(os.environ, {'SERVICESETU_MAILBOX': 'false', 'PAYMENT_MODE': 'mock', 'ASI1_API_KEY': ''}), patch('uagents.agent.get_almanac_contract', return_value=None):
    asyncio.run(smoke('ac'))
PY
```

## Owner video sequence

Record a short video of the **actual rendered chat**: explain the household's problem; show constraints and provider comparison; show exact review, approval and simulated confirmation; trigger provider cancellation; show recovery and fresh approval; end with replacement confirmation and full history. Show the public repository and profile briefly. Clearly state fictional providers, mock registry and simulated payments. If live delivery is unstable, identify a replay of the prior completed chat as recorded evidence rather than presenting it as a new live booking.

## Submission description draft

ServiceSetu helps households coordinate local service appointments and recover when a provider cancels. Its Concierge collects the service, location, appointment and budget, then coordinates specialist and independent provider agents to compare eligible quotes. The customer reviews the exact scope and price, explicitly approves one quote, and receives a test booking. A provider cancellation starts a constrained replacement search with fresh customer approval. The booking history explains the entire sequence.

Target users are households seeking local AC or plumbing help and small service businesses coordinating availability. The showcase uses fictional Bengaluru providers, a mock credential registry and simulated payments inside one ASI:One conversation. The outcome is an auditable demonstration booking and replacement, not a real-world reservation. TomTom supplies separately labelled live India business discovery; Taskrabbit supplies US-only external booking assistance. Discovery and external links never count as confirmed ServiceSetu bookings.

## Remaining human and optional work

- Obtain and independently verify the new conversation's public shared-chat URL; add voice to the silent walkthrough, upload it and submit links/text through the mandatory ASI:One event dashboard Project Submission Agent. The owner cannot keep the laptop on for days: persistent remote hosting remains unresolved, and local startup checks do not prove future uptime.
- Native FET payment-card rendering, a funded Dorado customer wallet, signing, on-chain confirmation and a separately verified refund remain unperformed. Stripe/Razorpay live test checkout is also unverified. They are optional rails, not evidence of a successful gateway transaction. Razorpay's hosted checkout and Taskrabbit's handoff leave ASI:One and are separate from the primary mock demo.
- TomTom routing still needs two unambiguous public endpoints for a successful live route check. Discovery results do not establish technician availability or onboarding.
- A real pilot requires provider permission, actual services/prices/coverage/availability, exact descriptions of manual checks, per-booking provider/operator acceptance, completion recording and problem follow-up. No real provider joined through this work. Do not use fictional alternatives for a real pilot booking.
