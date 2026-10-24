# ServiceSetu

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

Public hackathon repository: [arywk40-hue/ServiceSetu](https://github.com/arywk40-hue/ServiceSetu). [Remote proof runs](https://github.com/arywk40-hue/ServiceSetu/actions/workflows/proofs.yml).

Book a trusted local service, approve the exact price, and recover when the provider cancels — through one ASI:One conversation. ServiceSetu coordinates independent provider agents and keeps bookings and payments in deterministic code.

**Current demo and narrow pilot:** [complete ASI:One steps, Razorpay/Stripe test setup, operator commands and evidence limits](docs/demo-pilot-runbook.md). Customer status cards now expose messages, completion, history and booking-linked problem reports. A trusted operator can configure one consenting plumbing business using the existing `p4` identity in an isolated pilot database; fictional alternatives are disabled there. No real provider has joined through this work.

**Submission readiness:** the [current challenge audit](docs/showcase-readiness.md) records 343 passing tests and a new authenticated ASI:One journey with TomTom discovery, approved mock booking, provider cancellation/reversal, fresh replacement approval, confirmation and all 18 history events. Earlier expiry/retries and transport failures remain documented. A local 4:54 silent edited capture walkthrough is generated; the owner still adds voice, uploads it and verifies the public shared-chat URL. The official hackpack requires submission through the ASI:One event dashboard Project Submission Agent.

**Architecture:** [backend diagram and payment boundaries](docs/architecture.md).

**Recording package:** [timed video script and observed chat history](docs/video-script.md), with Word copies in [deliverables](deliverables/README.md). Google Places is an optional locally tested adapter; live Google calls are disabled for this showcase.

**Laptop shutdown:** registration does not host the backend. A persistent remote runtime is still required for fresh interaction while the laptop is off. See [free hosting constraints and migration steps](docs/hosting.md); no cloud deployment is claimed.

**Prototype only:** six fictional providers by default, twelve in the expanded demo, sixteen in the full catalogue; twelve service packages across cleaning, repairs, inspections and assembly. Location intake accepts Indian cities and localities with optional PIN codes; bookings require declared provider coverage. The original demo serves Indiranagar, Bengaluru; an optional demo copy adds fictional Powai, Mumbai branches. See [location intake and coverage](docs/nationwide-locations.md) and [optional Google Places adapter](docs/places-discovery.md). Uses a mock credential registry; simulated or Stripe/Razorpay/FET **test-only** payments. Native FET is Dorado-only. No actual service, identity verification, real money, UPI integration, escrow or payout. “Verified” always refers to the mock registry. Provider-supplied documents are explicitly unverified.

## Start in 30 seconds, no keys required

Python 3.10–3.13:

```sh
python3 -m servicesetu demo
python3 -m servicesetu chat
```

For the full test suite, install the fetch, communications and external extras using the command below, then run `.venv/bin/python -m servicesetu prove --core-only`. No Google key or billable Google request is needed.

`demo` prints the full booking, approval, cancellation, replacement approval and audit story, and writes `artifacts/demo-transcript.json`. `chat` offers the same flow in the terminal with simulated payment. This is a development surface; the intended customer surface is ACP inside ASI:One.

## Run the actual Fetch.ai mesh

Optional **Python backend MCP integrations** are documented in [TomTom and Taskrabbit setup](docs/external-mcp.md). TomTom provides separate business discovery, geocoding and qualified route estimates when a permitted `TOMTOM_API_KEY` is configured. Taskrabbit's current anonymous connector supports US assistance and an explicitly requested external draft link; India is refused. Discovery and links never become ServiceSetu bookings or payments. Install with `uv pip install --python .venv/bin/python -e '.[fetch,communications,external]'`. The original mock all-in-chat journey remains available.

Windows PowerShell setup and existing-identity startup: [Windows guide](docs/windows.md).

```sh
uv venv .venv
uv pip install --python .venv/bin/python -e '.[fetch,communications,external]'
# New checkout only: create private .env from .env.example; never overwrite an existing .env.
.venv/bin/python -m servicesetu prove --core-only
.venv/bin/python -m servicesetu prepare
.venv/bin/python -m servicesetu mesh
```

Without keys, the mesh runs locally. `prove` runs the deterministic scenarios and an actual uAgent message flow through the local dispatcher: shortlist → review → approval → confirmation → cancellation recovery → fresh approval → replacement confirmation → audit. The mesh proof does not test Agentverse hosting, ASI1 API responses or card rendering in ASI:One.

Seeded slots are tomorrow at 10:00 and 14:00 **Asia/Kolkata**, computed when a new database is seeded. Existing database slots are preserved. For a new demo date, use a new `SERVICESETU_DB` path. Keep your seed constant across registration and runtime. A private seed is generated at `data/agent-seed` if `SERVICESETU_SEED` is empty; never commit it or change it after registration.

## Agents

For a fresh multi-day demo database, run `python -m servicesetu seed-demo --db data/demo-three-days.db --days 3`, then start the runtime with `SERVICESETU_DB` pointing to that file. This creates 10 AM and 2 PM appointments for each of the next three local dates. Existing files are refused rather than overwritten, and normal startup preserves their seeded slots. Credentials and agent identities remain unchanged.

There are **eight role types**: seven specialists and one provider role type. The default demo has thirteen agent instances (six providers); the expanded demo has nineteen (twelve providers), and the full catalogue has twenty-three (sixteen providers). Only Concierge is a customer chat entry point. The rest accept signed typed requests from Concierge.

| Name | Role | Instance/address |
| --- | --- | --- |
| ServiceSetu-concierge | Intake, ASI1 comparisons, ACP cards and customer-facing payment proxy | `concierge` |
| ServiceSetu-matching | Category, area, budget and date eligibility | `matching` |
| ServiceSetu-verification | Credential claims, mock registry, service-date expiry | `verification` |
| ServiceSetu-booking | Holds, quote-bound consent, booking state and timeline | `booking` |
| ServiceSetu-payment | Test checkout, verified commit, retries and compensation | `payment` |
| ServiceSetu-recovery | Replacement candidates within original slot and budget | `recovery` |
| ServiceSetu-trust_monitor | Expiry checks, hold cleanup and payment reconciliation | `trust_monitor` |
| ServiceSetu-provider-p1 | CoolCare AC · INR 699 · mock verified | `provider:p1` |
| ServiceSetu-provider-p2 | Breeze AC · INR 749 · provider-supplied | `provider:p2` |
| ServiceSetu-provider-p3 | Lapsed AC · excluded for expired credential | `provider:p3` |
| ServiceSetu-provider-p4 | FlowFix Plumbing · INR 499 · mock verified | `provider:p4` |
| ServiceSetu-provider-p5 | TapCare Plumbing · INR 549 · provider-supplied | `provider:p5` |
| ServiceSetu-provider-p6 | Renewal Plumbing · check expiry at appointment | `provider:p6` |

**Exact addresses:** generated by `prepare` in [artifacts/agent-addresses.json](artifacts/agent-addresses.json). The reviewable [registration manifest](artifacts/registration-manifest.json) contains names, addresses, protocol digests and profile READMEs. Profile URLs are recorded after registration is verified; a shared chat must demonstrate the full ASI:One workflow. Both badges appear in each profile README under `docs/agents/`.

All thirteen mailbox identities are registered. Their public Almanac entries were verified active on October 13, 2026. Concierge has the handle `servicesetu`. The [direct ASI:One profile](https://asi1.ai/ai/agent1q02ftm6eu39lw0vc5kh3uhr4gtkkeqd6jpcaxzn4gyyrc2ac0p9ecvl39sz) reached Concierge and rendered provider and intake cards during the October 13 test. Personal-AI search did not find it. Direct card selections now accept the Concierge routing mention and a selection wrapper; quote ownership and exact approval binding remain enforced. The complete approval/payment/recovery UI workflow and fresh-account discovery still need live acceptance.

<!-- generated-agent-addresses:start -->

| Agent | Address | Public profile |
| --- | --- | --- |
| ServiceSetu-concierge | `agent1q02ftm6eu39lw0vc5kh3uhr4gtkkeqd6jpcaxzn4gyyrc2ac0p9ecvl39sz` | [Profile](https://agentverse.ai/agents/details/agent1q02ftm6eu39lw0vc5kh3uhr4gtkkeqd6jpcaxzn4gyyrc2ac0p9ecvl39sz/profile) |
| ServiceSetu-matching | `agent1q0k2tclxlfnags9m8qc6k8kwg4sfjwqeympvvu0t4nrm3e7mt6pp7x6qq53` | [Profile](https://agentverse.ai/agents/details/agent1q0k2tclxlfnags9m8qc6k8kwg4sfjwqeympvvu0t4nrm3e7mt6pp7x6qq53/profile) |
| ServiceSetu-verification | `agent1qfflx4d9w2j7nx2z64ajvjsz8jlmd6wekp6q2kv3dcerafyu3r8gsr7q8aj` | [Profile](https://agentverse.ai/agents/details/agent1qfflx4d9w2j7nx2z64ajvjsz8jlmd6wekp6q2kv3dcerafyu3r8gsr7q8aj/profile) |
| ServiceSetu-booking | `agent1qfs7ryjyx8y9cnyzduds9p6qg39fquzmscy97z86f4ytp49u2c29z9fzuuc` | [Profile](https://agentverse.ai/agents/details/agent1qfs7ryjyx8y9cnyzduds9p6qg39fquzmscy97z86f4ytp49u2c29z9fzuuc/profile) |
| ServiceSetu-payment | `agent1qdjrmxgpq6c5uxqmkr9j5g0appkn026zezv4juk7qchy8yyy6sx5szzylzt` | [Profile](https://agentverse.ai/agents/details/agent1qdjrmxgpq6c5uxqmkr9j5g0appkn026zezv4juk7qchy8yyy6sx5szzylzt/profile) |
| ServiceSetu-recovery | `agent1qtsmphqqq6du7cl0nrsepp092fqq7vmd97tygsmh4fu9yh5yagxejqvnd8j` | [Profile](https://agentverse.ai/agents/details/agent1qtsmphqqq6du7cl0nrsepp092fqq7vmd97tygsmh4fu9yh5yagxejqvnd8j/profile) |
| ServiceSetu-trust_monitor | `agent1qdldgm8c67xeh2q45pn3d7nm4hx297t3rzkju00z79vflev9kwlrc5jv84r` | [Profile](https://agentverse.ai/agents/details/agent1qdldgm8c67xeh2q45pn3d7nm4hx297t3rzkju00z79vflev9kwlrc5jv84r/profile) |
| ServiceSetu-provider-p1 | `agent1qw8325ts8p5zk08l65zl25v5587v60mxve939zysj3krsqaaazmu5lskhek` | [Profile](https://agentverse.ai/agents/details/agent1qw8325ts8p5zk08l65zl25v5587v60mxve939zysj3krsqaaazmu5lskhek/profile) |
| ServiceSetu-provider-p2 | `agent1qgjgspkhhlueg983p445y998xxnt8uek75nxc7gy8skmqwxnweeus29ln7k` | [Profile](https://agentverse.ai/agents/details/agent1qgjgspkhhlueg983p445y998xxnt8uek75nxc7gy8skmqwxnweeus29ln7k/profile) |
| ServiceSetu-provider-p3 | `agent1qgkktdv47ldl0qfrermy6u5vhedtzm599kux86yrpy7aqhagjysrudfddhl` | [Profile](https://agentverse.ai/agents/details/agent1qgkktdv47ldl0qfrermy6u5vhedtzm599kux86yrpy7aqhagjysrudfddhl/profile) |
| ServiceSetu-provider-p4 | `agent1qdsl2u234dwfpr4un02mkhxk073apx5h6cste5eukcwrmgykmy67vc4pyjr` | [Profile](https://agentverse.ai/agents/details/agent1qdsl2u234dwfpr4un02mkhxk073apx5h6cste5eukcwrmgykmy67vc4pyjr/profile) |
| ServiceSetu-provider-p5 | `agent1qwyurpzgm7y3luc5utlpgtu84e7gvy38axnkrpvnthcyechdhj9cxxr2zuy` | [Profile](https://agentverse.ai/agents/details/agent1qwyurpzgm7y3luc5utlpgtu84e7gvy38axnkrpvnthcyechdhj9cxxr2zuy/profile) |
| ServiceSetu-provider-p6 | `agent1q2n5kl49rvqrze00utqlpzakgxy0fgr99rnd3vpgrzlcarrpeg04wg2ecga` | [Profile](https://agentverse.ai/agents/details/agent1q2n5kl49rvqrze00utqlpzakgxy0fgr99rnd3vpgrzlcarrpeg04wg2ecga/profile) |

<!-- generated-agent-addresses:end -->

## Register and try it in ASI:One

1. Configure `AGENTVERSE_API_KEY`, `ASI1_API_KEY`, a persistent `SERVICESETU_SEED` and a private `DEMO_CONTROL_TOKEN` in `.env`.
2. Run `.venv/bin/python -m servicesetu.register` to review the identity/profile manifest.
3. Run `.venv/bin/python -m servicesetu.register --apply` to create mailbox profiles in your Agentverse account. Registration uses the installed SDK's mailbox registration path and records partial successes; retries must use the same seed. This command needs live verification with your account.
4. Set `SERVICESETU_MAILBOX=true` and run `.venv/bin/python -m servicesetu mesh`. Keep this process running during judging. Bureau retains separate mailbox identities and a shared local SQLite database. It starts receivers before processing queued work.
5. Find or directly mention the **Concierge** in ASI:One; test from a fresh account. Record actual profile URLs and a public shared chat in [docs/submission.md](docs/submission.md).

Run `.venv/bin/python -m servicesetu.register --verify` to inspect actual owned profiles and public active states. `prepare` preserves previous verification evidence; it does not establish new remote state. Use repeated `--only ROLE` flags to retry selected registrations after a quota or network failure.

Example prompts:

```text
AC service in Indiranagar Bengaluru tomorrow 10am under INR 1000
Plumbing in Indiranagar Bengaluru tomorrow 2pm under INR 600
Find real plumbers in Mandi, Himachal Pradesh.
Find AC service businesses in Indiranagar, Bengaluru.
Find cleaning services in Powai, Mumbai.
AC service in Indiranagar Bengaluru tomorrow 10am under INR 100
I need surgery in Mumbai
show what happened
```

Click a provider, review the exact scope, exclusions, document source/check date, slot, price and cancellation terms, then approve. For text fallback, copy the full `approve BOOKING_ID QUOTE_ID TOKEN` command from the review card. Planner-mediated approval prose is accepted only with all matching identifiers and explicit user-approved wording. Ambiguous prose requires using the exact fallback; ASI1 never authorizes payment.

To demonstrate a stale hold, wait more than two minutes before approving. To retry, use the same review-card selection; confirmed bookings return the same status without a new payment.

## Payment modes

The optional Razorpay path is `PAYMENT_MODE=razorpay_test`. Add `RAZORPAY_KEY_ID=rzp_test_…` and `RAZORPAY_KEY_SECRET` privately to `.env`; check access with `.venv/bin/python -m servicesetu.razorpay_payments`. After quote approval, open the labelled Razorpay TEST link, then return to the same ASI:One conversation and send `check payment`. Checkout is on Razorpay's hosted page. It conflicts with the hackathon's mandatory complete-primary-workflow-in-chat rule if used for the main demo. Use `PAYMENT_MODE=mock` for the all-in-chat demo; its confirmation is explicitly simulated. Server polling verifies Razorpay capture; retries reuse the stored link, and late capture/cancellation needs verified test refund. Actual Razorpay checkout and refunds remain unverified without test credentials. See the [current runbook](docs/demo-pilot-runbook.md).

For normal-language requests, missing-detail clarification and explicit
appointment alternatives, see [service intake](docs/intake.md). Customers can
choose appointment cards or reply `option 1`; no ISO timestamp is required.

`PAYMENT_MODE=mock` simulates payment inside the conversation and clearly labels it simulated. It creates no gateway charge and is the mode for a fully in-chat demo. It never presents a simulated payment as real gateway verification.

`PAYMENT_MODE=stripe_test` requires `sk_test_` and `pk_test_` keys. Payment Agent creates an embedded Stripe test Checkout session only after quote-bound approval. Concierge sends `RequestPayment` with Stripe metadata as the seller proxy for the single customer chat address. `CommitPayment` is forwarded to Payment Agent for server-side checks of the stored session ID, customer, booking, amount, currency, recipient and `livemode=false` before confirmation. The Trust Monitor polls persisted sessions every 30 seconds to recover a missing commit. Late payment is reversed if the short hold expired; gateway errors retain a pending intent for reconciliation. Refund failures remain explicitly `refund_required` for human review.

Run `.venv/bin/python -m servicesetu.stripe_check` after adding keys privately to `.env`; it checks test authentication without creating a payment or printing keys/balance data. Card-only checkout stays embedded (`redirect_on_completion=never`). The payment rail is persisted per booking, retries retrieve the same checkout, and `resume checkout` retries saved consent without creating another booking. A delayed reference-free checkout rejection cannot cancel a confirmed booking. Persisted result notices return reconciliation outcomes to the original conversation. Neither this check nor SDK-double tests prove ASI:One checkout rendering.

### Native FET on Dorado testnet

`PAYMENT_MODE=fet_testnet` enables only the Fetch Dorado testnet (`dorado-1`, `atestfet`, 18 decimals). Mainnet and other networks are refused. Set `FET_TEST_AMOUNT` to a positive amount with at most 18 decimal places (default `0.1`) and keep `FET_NETWORK=dorado-1` and `FET_USE_TESTNET=true` in the private `.env`. This amount is shown on the quote review before approval and is stored with that approval. It is a fixed test-token amount, **not an INR conversion**. The INR service quote remains separately visible.

The seller sends the official Agent Payment Protocol `RequestPayment` with `Funds(currency="FET", payment_method="fet_direct")`, a booking reference and Dorado metadata. The recipient is the Concierge's native ledger wallet (`fetch1…`), derived separately from the public ASI messaging identity (`agent1…`). The application never asks for or stores the customer's wallet recovery phrase/private key. ASI:One wallet support and the rendered payment card need a live check; local protocol tests do not prove that interactive experience.

To display the existing ServiceSetu recipient address (public address only), use the private configured ServiceSetu seed locally; the command does not print or upload it:

```sh
.venv/bin/python -m servicesetu.fet_wallet
```

For a customer test wallet, use a wallet explicitly configured for Dorado and copy only its public `fetch1…` address into Fetch's faucet. The official faucet grants test funds with no market value; the same wallet needs a small balance for network fees:

```sh
curl -X POST -H 'Content-Type: application/json' \
  -d '{"address":"<customer-fetch1-address>"}' \
  https://faucet-dorado.fetch.ai/api/v3/claims
```

After the customer approves the payment card, the server queries Dorado and verifies the transaction's success, hash, exact sender, recipient, `atestfet` amount, booking invoice, network and hold eligibility. A transaction hash alone never confirms a booking. Repeated commits and cross-booking transaction reuse are rejected. A verified transfer received after the invoice deadline or hold expiry cannot confirm; it becomes `refund_required`.

Cancellation does not send or claim a refund. A refund is a **separate on-chain Dorado transfer** from the configured recipient wallet back to the paying wallet. After an operator has sent that testnet transfer, record it only after server verification:

```sh
.venv/bin/python -m servicesetu.fet_refund BOOKING_ID DORADO_REFUND_TX_HASH
```

This command verifies an existing refund; it does not sign or send one. The current code does not automate refunds. Use testnet funds only. Local transfer-verifier tests do not establish that an ASI:One wallet can render or complete the card.

Live proof of Razorpay authentication, hosted checkout, capture or refund is pending; both test credentials are absent. The October 23 signed-in mock chat completed and visibly rendered the full booking, explicit quote approval, simulated confirmation, provider cancellation/reversal, fresh replacement approval, replacement confirmation and combined history. The expired first replacement was safely rejected; the customer then reviewed a fresh quote with the original constraints. This does not prove fresh-account discovery or public shared-chat access. A demo video was not captured because QuickTime screen recording was disabled. Stripe embedded rendering and native FET wallet-card rendering remain unverified. FET transaction tests use ledger doubles; no Dorado transaction was sent or received. Stripe test mode uses immediate capture, not production authorization/capture or an internal double-entry ledger. Discretionary refunds and payout changes have no agent tool. Policy compensation refunds run only through deterministic test-payment paths.

## Provider cancellation demo

Each provider exposes `/demo/cancel/pN` on the Bureau's local port. Send a JSON POST with `booking` and the `DEMO_CONTROL_TOKEN` as `token`. Use [scripts/cancel_provider.py](scripts/cancel_provider.py) so the token does not appear in shell history:

```sh
.venv/bin/python scripts/cancel_provider.py p1 BOOKING_ID
```

The provider can cancel only its own booking. It sends a signed notice to Concierge, which asks Recovery for alternatives and negotiates fresh quotes with the remaining provider agents. **Every replacement requires a fresh review and approval.** The original appointment and budget stay binding; raising the budget or changing time requires a new customer request. `recover` is a chat fallback if the notice is missed.

## Proofs

Routine reports and identity manifests are saved to ignored `artifacts/local/`.
Files directly under `artifacts/` remain published evidence snapshots. Registration
checks read local manifests first and do not rewrite the README unless evidence
publication is explicitly selected. See [generated evidence](docs/evidence.md).

One full command: `.venv/bin/python -m servicesetu prove`.

| Brief claim | Automated evidence |
| --- | --- |
| 1. Stale availability never confirms | `test_01`, `test_19` |
| 2. No double booking | `test_02` with two independent concurrent SQLite connections |
| 3. Accepted quote reconstructable | `test_03`, `test_11` |
| 4. Explicit approval before payment | `test_04`, `test_16`, `test_17` |
| 5. No duplicate charge on retry | `test_05` (mock rail), gateway SDK boundary tests |
| 6. Failure compensation | `test_06`, `test_07`, `test_14` |
| 7. Honest trust labels | `test_08` |
| 8. Credential valid on appointment date | `test_09` |
| 9. Recovery respects limits | `test_10`, `test_16`, actual mesh proof |
| 10. Reconstruct booking history | `test_11`, actual mesh audit |
| 11. Restricted actions gated | `test_12`, `test_13`, `test_17`, `test_18` |

The suite contains **343 scenarios**, including **32 workflow-hardening checks, 14 Razorpay API-double checks, and 18 Dorado FET protocol/ledger-double checks and 22 external MCP checks, plus 23 optional Google Places checks** for retries, ownership, exact transfer verification, replay, expiry and refund status. Stripe and FET boundary checks use SDK/ledger doubles, not actual transactions. The full harness also exercises actual local uAgent booking/recovery flows across the twelve packages plus two location variants. The current 343-test suite and a bounded local AC booking/recovery mesh smoke pass. An additional full catalogue rerun stalled after nine mesh workflows and is not counted as complete. Those checks prove binding and failure behavior locally; they do not claim a live gateway or wallet transaction. Routine evidence is written under ignored `artifacts/local/`; published examples remain under `artifacts/`. All use synthetic customer data. SQLite transactions and a unique active-slot index own reservation; quotes and events reject updates/deletes. File owners can still alter the database directly: append-only application audit is not cryptographic tamper-proof evidence. Shared SQLite is for a **single-machine Bureau**, not independently hosted Agentverse containers. Google Places is an optional adapter with mocked tests only; live Google queries are disabled for this showcase. See [video narration and observed chat history](docs/video-script.md).

Two live integration checks have also passed:

- [Live ASI1 intake/comparison](artifacts/live-asi1-proof.json): the actual adapters parsed a synthetic request and compared two seeded provider quotes. A fallback is rejected as evidence. Repeat with `.venv/bin/python -m servicesetu.live_reasoning`.
- [Remote mailbox proof](artifacts/remote-mailbox-proof.json): an Agentverse-hosted client exchanged actual ACP messages with the mailbox Concierge and completed booking, authenticated provider cancellation, replacement approval, confirmation and audit. Both synthetic booking timelines are included. The test released its slots and removed its temporary hosted agent. This verifies remote transport and the mesh, **not ASI:One UI rendering or discovery**.

The remote probe requires an already-running mailbox mesh and `PAYMENT_MODE=mock`. `.venv/bin/python -m servicesetu.remote_probe` creates a temporary hosted diagnostic client. If observation expires, use `--resume` on the same job; a timeout is not completion and does not justify creating a replacement. Keep private probe state under ignored `data/`.

The booking lifecycle persists `requested → held → confirmed → completed`, with cancellation from open states. A request reserves no capacity; the hold reserves one provider slot. Existing prototype databases migrate without changing their quote snapshots, payment references or event records. Review rejection is bound to the current card and cannot cancel a different or already confirmed booking.

## Current external checks and limits

History starts with the current saved booking status, provider, price, appointment and test-payment status. Every recorded event then appears as a numbered entry, grouped by local date with AM/PM times and seconds in IST. Appointment times are labelled separately from activity times. Unrecognised event types remain visible, and `audit details` preserves access to every original record field.

After a replacement is booked, `show what happened` presents a readable history with provider names, INR prices, appointment and event times in IST, approvals, cancellations and test-payment outcomes. It includes predecessor bookings in chronological order, including multiple replacements. Refunds awaiting completion are labelled as required rather than completed. Send `audit details` for the original event records, including quote snapshots and payment references. Each predecessor is checked against the conversation owner; an unrelated booking's history is never included. Querying an earlier booking shows its own history and predecessors, not later replacements.

The local proof harness, thirteen registrations, active public entries, live ASI1 adapters and actual remote mailbox workflow pass. The source is published in the public repository above. A complete all-in-chat mock flow was also observed in the existing signed-in account. Fresh-account discovery/routing, public share-link access, embedded Stripe test checkout and gateway compensation still need live acceptance. Stripe and Razorpay test credentials are not configured. A screen-captured demo video and Devpost submission remain pending. The [official event page](https://www.fetch.ai/events/fetch-a-thon-3) confirms October 24, 2026; the [official hackpack](https://www.fetch.ai/events/hackathons/fetch-a-thon-3/hackpack) confirms Agentverse/ACP/ASI:One requirements, a public repo and a 3–5 minute demo video (checked October 13, 2026).

A local authenticated [provider inbox and booking messages](docs/booking-communications.md) supports fictional visit coordination. No production Indian registry integration, legal assessment, real customer onboarding, real UPI, calendar sync, payouts, remotely hosted provider portal or live travel data. Intake supports the seeded visit scopes; additional work requires a new quote. A provider-confirmation failure is proven by injected failure in the core; the current seeded provider quote serves as provider confirmation. See [docs/submission.md](docs/submission.md) for the five-minute demo and remaining checks.

## Primary references

- [Fetch.ai uAgents](https://github.com/fetchai/uAgents) and the installed 0.25.5 SDK signatures/specifications.
- Official [Agent Payment Protocol](https://uagents.fetch.ai/docs/guides/agent-payment-protocol), [Dorado network settings](https://network.fetch.ai/docs/guides/ledger/references/active-networks), [Dorado faucet](https://network.fetch.ai/docs/guides/ledger/faucet), and [FET example](https://github.com/fetchai/innovation-lab-examples/tree/main/fet-example).
- [ACP interactive cards](https://docs.agentverse.ai/documentation/advanced-usages/agent-driven-interactive-cards) and [predefined card schemas](https://docs.agentverse.ai/documentation/advanced-usages/predefined-card-schemas).
- [Fetch.ai embedded Stripe example](https://github.com/fetchai/innovation-lab-examples/tree/main/stripe-horoscope-agent), consulted for metadata shape; implementation here is original.
- [ASI:One](https://asi1.ai), [Agentverse](https://agentverse.ai), [Stripe test dashboard](https://dashboard.stripe.com/test/apikeys).

Service catalogue and expansion readiness, including expanded demo setup, package boundaries and reasoning deadlines, are described in [service expansion](docs/service-expansion.md).

For all eight packages, quantity-based totals, grouped browsing and an upgrade that retains booking history, see [full catalogue](docs/full-catalogue.md).

The optional [twelve-package catalogue](docs/twelve-package-catalogue.md) adds mattress/carpet cleaning, refrigerator inspection and purifier servicing using the same sixteen provider identities. Activate it with a new database and --extended-catalogue; existing demo modes remain available.
