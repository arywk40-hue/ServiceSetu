# ServiceSetu submission workbench

**Current readiness:** see the [requirement-by-requirement audit](showcase-readiness.md). Current core tests: **343 passed in 34.247 seconds**, zero failures/skips. The local AC uAgent smoke passed. A new authenticated October 24 ASI:One conversation completed a fresh mock booking/cancellation/replacement journey after safe quote refreshes, with fresh replacement approval and **18 displayed history events**. Backend states were independently checked: original cancelled/refunded, replacement confirmed/paid, both `mock`. Earlier expiry and invalid-address rejection remain recorded; no uninterrupted first-attempt success is claimed. A local **4:44 silent edited walkthrough of actual captures** was generated. The owner still adds voice, uploads it and verifies a public shared-chat URL. Remote hosting is not deployed.

**Official submission check October 24:** the [hackpack](https://innovationlab.fetch.ai/events/hackathons/fetch-a-thon-3/hackpack) requires a **3–5 minute video** and **mandatory ASI:One event dashboard submission via the Project Submission Agent**. Follow any separately supplied organizer/Devpost instructions as well. The source and recording package were published at `1220381` before this fresh evidence update.

**October 24 publication review:** 343 core tests passed in 34.247 seconds, zero failures/skips; all 23 Google Places adapter tests passed. The adapter is implemented but live Google calls are disabled for this showcase, with no configured key or billing action. The [video script and observed 17-event chat outline](video-script.md) are ready for the owner to record. Overnight mailbox timeouts and one provider 401 remain reliability evidence; fresh signed checks passed, but the issue and a new full live run are not proven resolved.

**Hosting blocker:** the owner cannot keep a laptop running. No remote backend has been deployed. [Free hosting options](hosting.md) describe the account/access and persistence checks still needed; a registered profile alone does not keep the Python mesh online.

Prior FET and mock evidence (October 23, 2026): **298 local checks passed, plus 14 local uAgent workflows**. In the signed-in existing ASI:One Concierge chat, the full mock customer journey rendered: quote comparison and review, explicit approval, simulated confirmation, provider cancellation/reversal, fresh replacement quote and approval, replacement confirmation, and combined 17-event history. Both bookings preserved the service, area, appointment and INR 1,000 budget. This does not prove a gateway transaction or fresh-account/public chat access. The first replacement quote expired safely; a fresh quote was used. Razorpay test credentials remain absent. FET ledger checks use test doubles; no wallet payment was made and the live ASI:One payment card remains unverified. See the [current demo, payment and pilot runbook](demo-pilot-runbook.md).

## Latest external MCP verification

The TomTom and Taskrabbit Python backend connections are implemented. The MCP source snapshot passes 320 local tests (0 failed, 0 skipped), including 22 new external integration checks; the complete workspace has 336 passing checks including 16 separately preserved Google Places tests. A bounded current AC mock uAgent message workflow passes through approval, messaging, cancellation, fresh replacement approval and history. An additional unbounded full-catalogue rerun stalled after nine mesh workflows and was stopped; it is not counted as completed.

Anonymous live Taskrabbit initialization/schema discovery, 53 services at the public US test ZIP 10001, and availability with USD pricing and two scoping questions passed through the implemented backend. No Taskrabbit draft, reservation, booking or payment was created. After the operator privately configured TomTom, live tool discovery succeeded and geocoding/search returned India-filtered results for Mandi and Indiranagar, Bengaluru; ASI:One rendered Mandi plumber results with the required discovery labels and attribution. A Mandi route attempt was rejected as ambiguous, so no live route is claimed. The current Taskrabbit connector is US-only; India is refused before a Taskrabbit request. Authenticated ASI:One separately rendered the India refusal, live USD estimate, suggestion cards and returned scoping forms; the draft creation action was not performed. See [external MCP setup and evidence](external-mcp.md).

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
- ASI:One conversation: full lifecycle observed in the signed-in existing chat. A public shared-chat URL and independent access check remain unverified. Private chat links are excluded from the repository and this handoff.
- Concierge profile: [ServiceSetu-concierge](https://agentverse.ai/agents/details/agent1q02ftm6eu39lw0vc5kh3uhr4gtkkeqd6jpcaxzn4gyyrc2ac0p9ecvl39sz/profile), registered and active. It rendered without Agentverse sign-in, advertised ACP and Payment Protocol, and exposed a Chat with Agent link to ASI:One. Broad search from a fresh ASI:One account remains unverified.
- Specialist/provider profiles: all thirteen names, addresses and verified URLs are in `artifacts/registration-manifest.json` and the README.
- Demo video: `deliverables/ServiceSetu_Silent_Walkthrough.mp4`, local 4:44 silent edited capture walkthrough. Voiceover, public upload and mandatory ASI:One event dashboard submission remain owner actions. See [timed narration](video-script.md).

Do not replace these with invented links or present local dispatch as an ASI:One session.

## Live acceptance

- [x] Confirm actual event date/rules: [official event](https://www.fetch.ai/events/fetch-a-thon-3), [official hackpack](https://www.fetch.ai/events/hackathons/fetch-a-thon-3/hackpack), checked October 13, 2026.
- [x] ASI1 key returns a valid parsed request and evidence-based comparison (`artifacts/live-asi1-proof.json`).
- [x] All 13 identities have registered profiles and verified active Almanac entries.
- [x] Actual hosted client → mailbox → local mesh booking/recovery/audit passes (`artifacts/remote-mailbox-proof.json`).
- [ ] Only Concierge routes customer conversations; internal agents are described as internal.
- [ ] A fresh ASI:One account discovers Concierge and completes the full workflow.
- [x] Shortlist, optional address, exact review and status cards rendered in the authenticated client; prior complete mock flow rendered confirmation and history. This does not prove native wallet checkout.
- [ ] Both JSON selections and planner prose work; ambiguous approvals fail safely.
- [ ] Razorpay TEST payment (hosted external checkout) returns to ASI:One and verifies server-side. For the mandatory all-in-chat primary workflow demo, use the already implemented mock payment path until checkout is embedded or the official rules change.
- [ ] Duplicate commit returns the same booking and only one test gateway payment.
- [ ] Expired hold never confirms; late test payment is refunded.
- [x] New October 24 ASI:One conversation completed original approval/confirmation, authenticated provider cancellation/reversal, fresh replacement approval/confirmation and all 18 history events after safe quote refreshes. Earlier expiry and address rejection remained enforced.
- [x] Replacement requires new consent and respects appointment/budget limits in the local suite and prior completed mock chat.
- [ ] Public audit export matches the accepted quote and payment reference.
- [ ] Public GitHub README contains actual addresses, profile URLs and chat link.
- [x] Public GitHub source and run instructions published; exact seed-derived addresses included. The successful full-flow chat was observed in the existing signed-in account. Fresh-account discovery and public accessibility of the share link remain pending.
- [x] Scoped current tracked-file scan found no configured private seed/key/token values or private chat URL patterns; `.env`, databases and token files are ignored and untracked. This is not an exhaustive secret-history certification.
- [ ] Add voice to the generated 4:44 silent video, upload it, verify the public chat/video links, and submit through the mandatory ASI:One event dashboard Project Submission Agent. Follow additional organizer instructions.
- [ ] Runtime kept alive through judging.

## Current video 4 minutes 44 seconds

The local silent video uses actual captures of the new conversation with explanatory titles. It is an edited walkthrough, not continuous real-time footage. [Current chapter timings, full voiceover text and actual 18-event history](video-script.md) match the generated file. No audio is included. No gateway or on-chain checkout is shown.

## Submission description draft

ServiceSetu helps households book local AC servicing and plumbing without chasing availability or guessing what “verified” means. A Concierge coordinates Matching, Verification, independent Provider agents, Booking, Payment, Recovery and Trust Monitor. The customer compares documented trust, scope, price and appointment, approves one immutable quote, and receives a confirmed test booking. If the provider cancels, agent-to-agent requests find alternatives within the original limits and ask for fresh approval.

The prototype uses six fictional providers in Bengaluru, a mock credential registry and simulated or Stripe test payments. SQLite transactions prevent double booking; expiring holds stop stale confirmations; idempotency prevents duplicate payment intents; compensation releases slots and reverses failed payments. An append-only timeline reconstructs the booking. The intended customer experience is one ASI:One conversation using ACP cards. Live platform and gateway claims should be added only after the acceptance checklist passes.
