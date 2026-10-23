# Prototype completion audit · October 13, 2026

This is a historical October 13 audit. For the October 23 implementation and verification, see [submission status](submission.md) and the [demo/pilot runbook](demo-pilot-runbook.md). The final local proof records 280 checks and 14 local uAgent workflows passed. A later signed-in ASI:One chat rendered the complete mock booking, approval, confirmation, provider cancellation/reversal, fresh replacement approval and confirmation, and full history. Razorpay test credentials are absent; no actual gateway transactions are claimed. No real business has been onboarded.

The requested final state is the Fetch-A-Thon prototype in Parts II–III of the attached brief. Production pilot phases and Tier 3 bonuses are later work; they are not represented as completed. A green local suite does not prove remote registration or ASI:One completion.

| Requirement | Authoritative evidence | Status |
| --- | --- | --- |
| Six to eight seeded providers in one or two trades | `Store.seed`: six providers, AC and plumbing, Bengaluru | Implemented |
| Eight agent role types, independent provider identities | `servicesetu.mesh`, actual mesh transcript and 13-address manifest | Locally verified |
| Shared database-backed requested/held/confirmed/completed/cancelled lifecycle | `tests/test_intake.py`, preserved-data migration test, core timeline | Verified locally |
| ACP on Concierge | Installed locked protocol specification, actual hosted-client ChatMessage/Acknowledgement flow | Verified over the live mailbox network; ASI:One UI pending |
| Agentverse registration for every submitted agent | Live owned-agent API verified all 13 identities; public Almanac states and profile URLs recorded | Achieved |
| Discoverable and usable from a fresh ASI:One account | No fresh-account shared chat or discovery evidence | Not achieved |
| ASI1 core reasoning | Actual adapters parsed a synthetic request and compared two quotes; `artifacts/live-asi1-proof.json` rejects fallback as proof | Verified live on synthetic input |
| Clarification, shortlist and honest trust levels | Conversation, card payloads, proof suite, synthetic transcript | Verified locally |
| “Why not” exclusions | Expired credential, budget and occupied-slot proofs | Verified locally |
| Form JSON and planner prose selections | Intake/card tests; exact review identifiers checked | Verified locally; planner wording/rendering needs live acceptance |
| Customer approval tied to quote, booking and review token | Approval tests, stale-reject and session-isolation tests | Verified locally |
| Payment Protocol and Stripe/Razorpay test session binding | Installed seller spec, payment adapters and SDK/API-double tests | Locally verified; real test checkout/commit missing |
| Whole workflow entirely in ASI:One | Current [Fetch-A-Thon 3.0 hackpack](https://innovationlab.fetch.ai/events/hackathons/fetch-a-thon-3/hackpack) makes this mandatory; hosted Razorpay leaves chat | Full signed-in mock journey including replacement and history rendered; fresh-account/public share access not checked |
| Failure paths: expired hold, race, declined and duplicate payment | Automated proofs | Verified locally on mock rail |
| No orphan slot/payment after failure | Compensation proofs, pending gateway intent/reconciliation path | Local behavior verified; gateway behavior needs live test |
| Immutable accepted quote versions | Core append-only quote table and revision test | Verified locally |
| Service-date credential expiry | Date-specific eligibility test | Verified locally against mock registry |
| Visible provider cancellation/recovery inside user limits | Actual hosted client received mailbox recovery cards, approved replacement, received confirmation and audit; server timelines reconstruct both bookings | Verified over the live mailbox network; ASI:One scene pending |
| Restricted AI actions routed to human review | No refund/payout/override tool; logged refusal tests | Verified locally; no live operations workbench claimed |
| Reconstruct any booking | Quote snapshot, request, hold, consent, payment and transition events | Verified locally; file-level tamper resistance not claimed |
| Public GitHub repository and run instructions | `https://github.com/arywk40-hue/ServiceSetu`, public visibility checked via GitHub API | Achieved |
| Agent names and addresses, resources, both badges | Public README, verified profile URLs, exact address table and each profile README | Achieved; shared chat remains pending |
| One-command proof harness | `.venv/bin/python -m servicesetu prove`, JSON verdicts and actual local mesh transcript | Verified locally |
| Public ASI:One shared chat URL | Signed-in chat URL recorded locally; public/fresh-account access not tested | Pending independent access check |
| Public Agentverse profile URLs | All 13 verified URLs in registration manifest and README | Achieved |
| Three-to-five minute demo video | Timed script in `docs/submission.md`; QuickTime New Screen Recording disabled | Not captured; screen recording still required |
| Devpost problem/users/outcome description | Draft in `docs/submission.md` | Draft ready; submission not achieved |
| Runtime running through judging | Local mailbox runtime is active and remotely tested; persistent hosting through judging is not established | Not achieved |

The final local suite and saved proof artifact pass; those checks do not substitute for the mandatory end-to-end ASI:One scene. The October 23 signed-in session rendered the original mock booking and cancellation/recovery response, but the replacement quote expired and a fresh response timed out during Agentverse delivery. Razorpay TEST credentials remain absent. Use `PAYMENT_MODE=mock` to keep the demonstrated primary workflow in chat; Razorpay hosted checkout is a separate external integration path. Preserve `SERVICESETU_SEED`. No new business has joined.
