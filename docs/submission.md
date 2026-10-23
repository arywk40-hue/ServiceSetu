# ServiceSetu submission workbench

Status (October 23, 2026): **298 local checks passed, plus 14 local uAgent workflows**. In the signed-in existing ASI:One Concierge chat, the full mock customer journey rendered: quote comparison and review, explicit approval, simulated confirmation, provider cancellation/reversal, fresh replacement quote and approval, replacement confirmation, and combined 17-event history. Both bookings preserved the service, area, appointment and INR 1,000 budget. This does not prove a gateway transaction or fresh-account/public chat access. The first replacement quote expired safely; a fresh quote was used. Razorpay test credentials remain absent. FET ledger checks use test doubles; no wallet payment was made and the live ASI:One payment card remains unverified. See the [current demo, payment and pilot runbook](demo-pilot-runbook.md).

## Current implementation evidence

Razorpay test support has 14 API-double tests in the 298-test passing suite. Razorpay uses external hosted Payment Links and returns the customer to ASI:One for `check payment`; it is not native in-chat checkout. Both Razorpay test credentials were absent. The completed mock chat kept the customer workflow in ASI:One and used no external payment page. No gateway transaction is claimed.

The optional FET path adds `PAYMENT_MODE=fet_testnet` on Dorado only. Eighteen local ledger-double tests cover the approval-bound invoice, exact `fet_direct` request, transaction verification, wrong terms, replay, hold expiry and separate refund verification. No Dorado transfer or authenticated ASI:One payment-card rendering was completed; the test results are local code evidence only.

- [x] Existing source, README, submission checklist, booking/payment/messaging/inbox/lifecycle implementation inspected at `bf708c2` before changes; baseline 234 tests passed with loopback access.
- [x] Quote-bound approval, stored payment rail, same-checkout retry/resume, missing-commit/session-create recovery, late-payment compensation and refund failure behavior covered locally with Stripe SDK doubles.
- [x] Customer/session ownership, assigned-provider cancellation, internal worker restrictions, idempotent completion and encrypted booking-linked reports covered locally.
- [x] Existing status cards expose messaging, completion, history and problem reports, with text fallbacks.
- [x] Private operator import/acceptance and problem acknowledgement commands; pilot labels distinguish real records from fictional data, and fictional alternatives are disabled in the pilot database.
- [x] Final local proof harness: 298 tests (0 failed, 0 skipped) and 14 actual local uAgent scenarios; `artifacts/local/proof-results.json` records `passed: true`, `mesh: passed`. These are not live gateway or wallet evidence.
- [x] Dorado FET testnet implementation locally verified; exact approved test amount is persisted, `fet_direct` uses a native `fetch1…` recipient separate from `agent1…`, transaction checks use Dorado, and refunds stay pending until a separate transfer is verified.
- [x] October 23 live ASI:One: direct Concierge profile accessible, synthetic request reaches the running registered mesh, provider shortlist cards render; `status` recovers/refreshed the comparison after transport trouble.
- [x] Complete signed-in ASI:One mock sequence through approval, simulated confirmation, provider cancellation/reversal, fresh replacement approval, replacement confirmation and combined history. The first expired replacement quote was rejected and not reused.
- [ ] Razorpay test authentication, hosted checkout, server capture confirmation and refund. `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` are absent; no gateway transaction is claimed.
- [ ] Razorpay hosted checkout conflicts with the [official Fetch-A-Thon 3.0 mandatory requirement](https://innovationlab.fetch.ai/events/hackathons/fetch-a-thon-3/hackpack) that the complete primary user workflow be demonstrated entirely inside an ASI:One conversation. Use `PAYMENT_MODE=mock` for that all-in-chat demo; keep Razorpay as the separately tested hosted-checkout integration. The hackpack lists Payment Protocol as a bonus criterion, not a mandatory requirement. Checked October 23, 2026.
- [ ] Stripe test authentication and actual embedded checkout/PaymentIntent/refund observed (optional rail). No gateway transaction is claimed.
- [ ] FET `RequestPayment` card rendered and completed in an authenticated ASI:One session with a separately funded Dorado customer wallet; no on-chain transaction is claimed.
- [ ] Real business permission, actual services/prices/coverage/availability, exact manual checks and per-booking provider acceptance. None has been obtained by this task.

## Links to record after verification

- Public GitHub repo: [arywk40-hue/ServiceSetu](https://github.com/arywk40-hue/ServiceSetu), published and public.
- ASI:One conversation: full lifecycle observed in the signed-in existing chat; a private link is retained in the local handoff. Fresh-account/public link access remains unverified.
- Concierge profile: [ServiceSetu-concierge](https://agentverse.ai/agents/details/agent1q02ftm6eu39lw0vc5kh3uhr4gtkkeqd6jpcaxzn4gyyrc2ac0p9ecvl39sz/profile), registered and active; fresh-account ASI:One discovery is unverified.
- Specialist/provider profiles: all thirteen names, addresses and verified URLs are in `artifacts/registration-manifest.json` and the README.
- Demo video: pending live platform capture.

Do not replace these with invented links or present local dispatch as an ASI:One session.

## Live acceptance

- [x] Confirm actual event date/rules: [official event](https://www.fetch.ai/events/fetch-a-thon-3), [official hackpack](https://www.fetch.ai/events/hackathons/fetch-a-thon-3/hackpack), checked October 13, 2026.
- [x] ASI1 key returns a valid parsed request and evidence-based comparison (`artifacts/live-asi1-proof.json`).
- [x] All 13 identities have registered profiles and verified active Almanac entries.
- [x] Actual hosted client → mailbox → local mesh booking/recovery/audit passes (`artifacts/remote-mailbox-proof.json`).
- [ ] Only Concierge routes customer conversations; internal agents are described as internal.
- [ ] A fresh ASI:One account discovers Concierge and completes the full workflow.
- [ ] Form, shortlist, review and status cards render in the client.
- [ ] Both JSON selections and planner prose work; ambiguous approvals fail safely.
- [ ] Razorpay TEST payment (hosted external checkout) returns to ASI:One and verifies server-side. For the mandatory all-in-chat primary workflow demo, use the already implemented mock payment path until checkout is embedded or the official rules change.
- [ ] Duplicate commit returns the same booking and only one test gateway payment.
- [ ] Expired hold never confirms; late test payment is refunded.
- [ ] Provider cancellation arrives as an actual agent notice and opens recovery.
- [ ] Replacement requires new consent and respects appointment/budget limits.
- [ ] Public audit export matches the accepted quote and payment reference.
- [ ] Public GitHub README contains actual addresses, profile URLs and chat link.
- [x] Public GitHub source and run instructions published; exact seed-derived addresses included. The successful full-flow chat was observed in the existing signed-in account. Fresh-account discovery and public accessibility of the share link remain pending.
- [ ] No secrets, seed files, database files or customer data are published.
- [ ] 3–5 minute video, description and links entered in Devpost.
- [ ] Runtime kept alive through judging.

## Video, 4 minutes 45 seconds

| Time | Scene |
| --- | --- |
| 0:00–0:20 | Problem: finding a local service, knowing whom to trust, starting over after cancellation. Show the actual registered mesh. |
| 0:20–1:20 | Ask for AC service in Indiranagar. Show the shortlist, mock-verified and provider-supplied labels; explain why the expired provider is excluded. |
| 1:20–2:00 | Review the quote and approve. Show actual Stripe test checkout if live verified, otherwise honestly label mock payment. Confirm booking. |
| 2:00–2:40 | Show stale-hold rejection and the proof run for duplicate payment/race protection. |
| 2:40–3:40 | Trigger provider cancellation. Show fresh provider-agent offers and new approval. |
| 3:40–4:20 | Request the audit timeline; show immutable quote details and the public repo's one-command proofs. |
| 4:20–4:45 | State seeded providers/mock registry/test payments. Explain the narrow real-provider pilot path. |

## Devpost draft

ServiceSetu helps households book local AC servicing and plumbing without chasing availability or guessing what “verified” means. A Concierge coordinates Matching, Verification, independent Provider agents, Booking, Payment, Recovery and Trust Monitor. The customer compares documented trust, scope, price and appointment, approves one immutable quote, and receives a confirmed test booking. If the provider cancels, agent-to-agent requests find alternatives within the original limits and ask for fresh approval.

The prototype uses six fictional providers in Bengaluru, a mock credential registry and simulated or Stripe test payments. SQLite transactions prevent double booking; expiring holds stop stale confirmations; idempotency prevents duplicate payment intents; compensation releases slots and reverses failed payments. An append-only timeline reconstructs the booking. The intended customer experience is one ASI:One conversation using ACP cards. Live platform and gateway claims should be added only after the acceptance checklist passes.
