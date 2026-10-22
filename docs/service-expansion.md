# Expanded demo services

All providers, credentials and services below are fictional. Coverage remains Indiranagar, Bengaluru. Payments remain simulated or Stripe test payments.

| Category | Fixed package | Demo prices |
| --- | --- | --- |
| AC servicing | One AC service visit; parts excluded | INR 699 / 749 |
| Plumbing | One standard tap repair visit; parts excluded | INR 499 / 549 |
| Bathroom cleaning | One bathroom: accessible floor, wall tiles, basin and toilet surfaces | INR 799 / 899 |
| Electrical inspection | One inspection visit for one reported household issue; assessment only | INR 399 / 499 |

Cleaning excludes extra bathrooms, whole-home cleaning, mould remediation, hazardous waste and repairs. Electrical inspection excludes repairs, parts, rewiring, mains work and emergency response. Extra work requires a fresh quote and approval. General cleaning or electrician requests ask the customer to choose the bounded package before matching. Explicit form labels select that package. Model output cannot invent package acceptance.

Each category has three seeded providers: mock-registry checked, provider-supplied evidence, and a credential-expiry case. Expired providers are excluded during matching. Final eligibility depends on appointment date, budget and whether the slot is free. `show services` reflects providers in the active database; it does not promise that every seeded provider is eligible.

## Create an expanded demo

From the project directory in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m servicesetu seed-demo --db data/demo-expanded-2026-10-23-to-25.db --days 3 --expanded
```

Creation refuses an existing filename. Dates are relative to creation day; the filename is a label, not a date override. Existing databases are untouched. Default seeding still creates only the original six providers. The expanded database contains twelve providers and uses nineteen agents: seven specialists plus one agent per provider. Existing seed-derived addresses are preserved.

## Activate

Only if the six new profiles have not already been registered, register them once:

```powershell
$env:SERVICESETU_DB = 'data/demo-expanded-2026-10-23-to-25.db'
.\.venv\Scripts\python.exe -m servicesetu.register --apply --only provider:p7 --only provider:p8 --only provider:p9 --only provider:p10 --only provider:p11 --only provider:p12
```

Stop the existing mesh with Ctrl+C before starting the expanded runtime. Keep the configured seed. Run these identities on one machine at a time.

```powershell
$env:SERVICESETU_MAILBOX = 'true'
$env:PAYMENT_MODE = 'mock'
$env:SERVICESETU_DB = 'data/demo-expanded-2026-10-23-to-25.db'
.\.venv\Scripts\python.exe -m servicesetu mesh
```

After startup, in another terminal with the same database environment:

```powershell
.\.venv\Scripts\python.exe -m servicesetu.register --verify
```

Expect nineteen registered profiles and nineteen active agents once activation finishes. Registration verification is not an end-to-end delivery proof. In ASI:One, use the existing ServiceSetu-concierge address and try:

> Book one bathroom cleaning in Indiranagar, Bengaluru tomorrow at 2 PM under INR 1000. Use simulated payment.

> Book an electrical inspection in Indiranagar, Bengaluru tomorrow at 10 AM under INR 700. Use simulated payment.

## Technical structure

`servicesetu/catalogue.py` defines categories, package recognition, quote scope and exclusions. Both ASI1 extraction and the local parser recognise four categories. Conversation intake requires explicit package wording for new categories; core validation independently checks the package. Quotes retain their exact scope and exclusions in the existing immutable snapshot.

SQLite owns capacity, holds, approval and payment state. Provider agents use typed uAgent messages. The same booking/payment/recovery services apply to all categories. The default proof runs local uAgent booking, authenticated provider cancellation and replacement-approval flows for AC, cleaning and electrical inspection. This does not prove ASI:One rendering or live Agentverse delivery. Tests also cover plumbing and existing safeguards.

Further categories require a bounded package, suitable credential policy, independent provider capacity, explicit intake and complete lifecycle checks. Real companies require actual onboarding and verification; seeded names are not real businesses available for hire.

## Reasoning latency

ASI1 request extraction has an eight-second deadline; quote comparison has a three-second deadline. Neither automatically retries. Timeout fallbacks use the conservative local parser and existing quote facts. Missing details require clarification. Neither fallback approves bookings or payments. These limits do not bound Agentverse mailbox or reply delivery time.
