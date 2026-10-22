# Eight-package demo catalogue

The optional [twelve-package extension](twelve-package-catalogue.md) adds mattress
and carpet cleaning, refrigerator inspection and purifier servicing while
retaining the same provider identities. The eight-package seed below is retained.

All companies, credentials and services are fictional. Coverage remains
Indiranagar, Bengaluru. Payments are simulated or Stripe test payments.

The full catalogue adds these packages to AC servicing, plumbing, bathroom
cleaning and electrical inspection:

| Package | Required details | Demo price |
| --- | --- | --- |
| One kitchen cleaning | Explicit acceptance of one-kitchen scope | INR 1199 / 1399 |
| Fabric sofa cleaning | 1–6 seats; fabric material | INR 249 / 299 per seat |
| Washing-machine inspection | Front/top loading; reported problem | INR 449 / 549 |
| Flat-pack furniture assembly | Chair/table/bookshelf; 1–3 of one type; instructions available | Chair INR 349 / 449, table INR 549 / 649, bookshelf INR 699 / 799 per item |

Kitchen cleaning covers accessible counters, sink, hob exterior and floor;
cabinet interiors, chimney dismantling and appliance interiors are excluded.
Sofa cleaning excludes leather, suede, repairs and guaranteed stain removal.
Machine inspection is diagnosis only: parts, repair and installation require a
separate quote. Assembly excludes wardrobes, custom carpentry, missing parts,
wall mounting and drilling. All quotes show scope and exclusions before approval.

## Discovery and clarification

`show services` lists the catalogue with package-selection cards. Filter with:

- `show cleaning services`
- `show appliance services`
- `show repair services`
- `show assembly services`

Selecting a package starts intake; it does not hold a slot or approve payment.
Missing service details are requested individually. Short answers such as `3`,
`fabric`, `top-loading` and `instructions available` retain location, budget and
appointment. They do not require an ASI1 call. Unsupported materials, quantities,
item types or absent instructions prevent quotes. Model-invented service details
are discarded; only explicit customer answers or form fields are used.

## Providers and capacity

FreshNest and SparkleSpace offer bathroom, kitchen and sofa cleaning through
their existing agent identities. Their capacity is shared across packages: a
provider reserved for bathroom cleaning cannot accept kitchen or sofa cleaning
at the same appointment. The expired cleaning provider remains excluded.

SpinCheck Appliances and DrumCare Appliances handle machine inspections.
AssemblyWorks and BuildBuddy Assembly handle furniture assembly. Four new
provider identities bring the full demo to sixteen providers and twenty-three
agents, including the seven existing specialists. Default seeding remains six
providers; `--expanded` remains twelve providers.

## Prepare a new demo or preserve existing history

From the project directory in PowerShell, create a fresh full demo:

```powershell
.\.venv\Scripts\python.exe -m servicesetu seed-demo --db data/demo-catalogue.db --days 3 --full-catalogue
```

To carry forward existing bookings, use a new target path and a source database:

```powershell
.\.venv\Scripts\python.exe -m servicesetu seed-demo --db data/demo-catalogue-copy.db --days 3 --full-catalogue --from-db data/demo-expanded-2026-10-23-to-25.db
```

The command uses SQLite backup, preserves booking/payment/audit/session records,
adds new providers and adds cleaning offerings only in the copy. The source is
opened read-only; existing configured prices are retained. Dates and slots of
copied providers are retained, including reservations. New providers get slots
for the next three local dates. Existing target files are refused. The copy is
a snapshot, not a live synchronised database: stop using the old runtime before
switching, so later bookings are not left behind in the source database.

Register only the four new profiles once, if not already registered, using the
full database environment:

```powershell
$env:SERVICESETU_DB = 'data/demo-catalogue-copy.db'
.\.venv\Scripts\python.exe -m servicesetu.register --apply --only provider:p13 --only provider:p14 --only provider:p15 --only provider:p16
```

Stop the existing mesh with Ctrl+C, then start the runtime with the full database:

```powershell
$env:SERVICESETU_MAILBOX = 'true'
$env:PAYMENT_MODE = 'mock'
.\.venv\Scripts\python.exe -m servicesetu mesh
```

Keep the seed unchanged and run identities on one machine at a time. Expect
twenty-three profiles after registration; active status requires runtime startup.

## Architecture and validation

`catalogue.py` owns package definitions, provider offerings, totals and scope.
`service_details.py` extracts and validates explicit details. Conversation intake
collects them; `Store.normalize_job` independently validates them. Matching uses
the complete price, not a per-seat starting price. Typed provider requests carry
the validated job, and immutable quote snapshots include service, details, total,
scope and exclusions. The customer must approve that exact quote. Removed
offerings are rechecked before reservation and payment.

SQLite transactions and the existing unique provider-slot index still enforce
capacity. Payments, compensation and replacement approval use the existing
services. Local tests cover all four new package lifecycles, detail corrections,
total budgets, shared capacity, stale approval, invalid fields and copy safety.
The real local-uAgent proof includes booking, authenticated cancellation,
replacement approval and audit for all four new packages. Live ASI:One rendering
and delivery must be tested after switching the runtime.
