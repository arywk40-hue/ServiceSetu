# ServiceSetu submission workbench

Status: local implementation and synthetic proofs ready; live platform acceptance pending.

## Links to record after verification

- Public GitHub repo: [arywk40-hue/ServiceSetu](https://github.com/arywk40-hue/ServiceSetu), published and public.
- ASI:One shared chat: pending full live conversation.
- Concierge profile: pending registration and fresh-account discovery.
- Specialist/provider profiles: pending registration (identities in `artifacts/registration-manifest.json`).
- Demo video: pending live platform capture.

Do not replace these with invented links or present local dispatch as an ASI:One session.

## Live acceptance

- [x] Confirm actual event date/rules: [official event](https://www.fetch.ai/events/fetch-a-thon-3), [official hackpack](https://www.fetch.ai/events/hackathons/fetch-a-thon-3/hackpack), checked October 13, 2026.
- [ ] ASI1 key returns a valid parsed request and evidence-based comparison.
- [ ] All 13 identities have registered profiles and running mailboxes.
- [ ] Only Concierge routes customer conversations; internal agents are described as internal.
- [ ] A fresh ASI:One account discovers Concierge and completes the full workflow.
- [ ] Form, shortlist, review and status cards render in the client.
- [ ] Both JSON selections and planner prose work; ambiguous approvals fail safely.
- [ ] Embedded Stripe TEST payment completes inside the chat and verifies server-side.
- [ ] Duplicate commit returns the same booking and only one test gateway payment.
- [ ] Expired hold never confirms; late test payment is refunded.
- [ ] Provider cancellation arrives as an actual agent notice and opens recovery.
- [ ] Replacement requires new consent and respects appointment/budget limits.
- [ ] Public audit export matches the accepted quote and payment reference.
- [ ] Public GitHub README contains actual addresses, profile URLs and chat link.
- [x] Public GitHub source and run instructions published; exact seed-derived addresses included. Live profile URLs and shared chat remain pending.
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
