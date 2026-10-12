# Prototype completion audit · October 13, 2026

The requested final state is the Fetch-A-Thon prototype in Parts II–III of the attached brief. Production pilot phases and Tier 3 bonuses are later work; they are not represented as completed. A green local suite does not prove remote registration or ASI:One completion.

| Requirement | Authoritative evidence | Status |
| --- | --- | --- |
| Six to eight seeded providers in one or two trades | `Store.seed`: six providers, AC and plumbing, Bengaluru | Implemented |
| Eight agent role types, independent provider identities | `servicesetu.mesh`, actual mesh transcript and 13-address manifest | Locally verified |
| Shared database-backed requested/held/confirmed/completed/cancelled lifecycle | `tests/test_intake.py`, preserved-data migration test, core timeline | Verified locally |
| ACP on Concierge | Installed locked protocol specification, actual ChatMessage/Acknowledgement flow | Verified locally; remote use pending |
| Agentverse registration for every submitted agent | Registration manifest says `not_verified`; no API key configured | Not achieved |
| Discoverable and usable from a fresh ASI:One account | No fresh-account shared chat or discovery evidence | Not achieved |
| ASI1 core reasoning | Intake and evidence comparison adapters implemented; no ASI1 key configured | Live behavior unverified |
| Clarification, shortlist and honest trust levels | Conversation, card payloads, proof suite, synthetic transcript | Verified locally |
| “Why not” exclusions | Expired credential, budget and occupied-slot proofs | Verified locally |
| Form JSON and planner prose selections | Intake/card tests; exact review identifiers checked | Verified locally; planner wording/rendering needs live acceptance |
| Customer approval tied to quote, booking and review token | Approval tests, stale-reject and session-isolation tests | Verified locally |
| Payment Protocol and Stripe test session binding | Installed seller spec, Payment adapter, SDK-double tests | Locally verified; real test checkout/commit missing |
| Whole workflow entirely in ASI:One | Local dispatch is not an ASI:One session | Not achieved |
| Failure paths: expired hold, race, declined and duplicate payment | Automated proofs | Verified locally on mock rail |
| No orphan slot/payment after failure | Compensation proofs, pending gateway intent/reconciliation path | Local behavior verified; gateway behavior needs live test |
| Immutable accepted quote versions | Core append-only quote table and revision test | Verified locally |
| Service-date credential expiry | Date-specific eligibility test | Verified locally against mock registry |
| Visible provider cancellation/recovery inside user limits | Real local provider notice, original-session recovery and new approval transcript | Verified locally; ASI:One scene pending |
| Restricted AI actions routed to human review | No refund/payout/override tool; logged refusal tests | Verified locally; no live operations workbench claimed |
| Reconstruct any booking | Quote snapshot, request, hold, consent, payment and transition events | Verified locally; file-level tamper resistance not claimed |
| Public GitHub repository and run instructions | `https://github.com/arywk40-hue/ServiceSetu`, public visibility checked via GitHub API | Achieved |
| Agent names and addresses, resources, both badges | Public README, exact address table and per-agent profile READMEs | Local/source part achieved; profile URLs pending |
| One-command proof harness | `.venv/bin/python -m servicesetu prove`, JSON verdicts and actual local mesh transcript | Verified locally |
| Public ASI:One shared chat URL | No live shared chat exists | Not achieved |
| Public Agentverse profile URLs | Profiles not registered yet | Not achieved |
| Three-to-five minute demo video | Timed script in `docs/submission.md`; no live capture | Not achieved |
| Devpost problem/users/outcome description | Draft in `docs/submission.md` | Draft ready; submission not achieved |
| Runtime running through judging | No remote mailbox runtime or uptime evidence | Not achieved |

Required next inputs: configure `ASI1_API_KEY`, `AGENTVERSE_API_KEY`, `STRIPE_SECRET_KEY` (`sk_test_…`) and `STRIPE_PUBLISHABLE_KEY` (`pk_test_…`) in private `.env`. Preserve `SERVICESETU_SEED`. Then perform live registration, card/payment acceptance, fresh-account discovery, shared chat and video capture before submitting. The active goal remains incomplete.
