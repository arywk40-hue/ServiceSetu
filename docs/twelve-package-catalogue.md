# Twelve-package demo catalogue

This extends the [eight-package catalogue](full-catalogue.md) using the same
sixteen provider identities and seven specialists. No additional Agentverse
profiles are needed. All companies, credentials and payments remain fictional
or test-only; coverage remains Indiranagar, Bengaluru.

| Additional package | Details required | Seeded pricing |
| --- | --- | --- |
| Mattress surface cleaning | One size: single/double/queen/king; 1–3 mattresses | Single INR 499 / 599; double 699 / 799; queen 799 / 899; king 899 / 999, per mattress |
| One synthetic carpet cleaning | Length and width in feet; synthetic material | INR 15 / 18 per square foot, minimum INR 499 / 599 per visit |
| Household refrigerator inspection | Single-door/double-door/side-by-side; reported problem | INR 499 / 599 |
| Household water-purifier servicing | RO/UV/UF or combination; servicing purpose | INR 699 / 799 |

Mattress cleaning excludes mould remediation, hazardous contamination, internal
repairs and guaranteed stain/pest removal. Mixed sizes need separate quotes.
Carpet cleaning covers one synthetic carpet up to 150 square feet; dimensions
must each be 0.5–20 feet with at most two decimal places. Wool, silk, fitted
carpets and multiple rugs are excluded. Area totals are calculated with Decimal
and rounded upward to whole paise before comparison with the customer's budget.

Refrigerator inspection is diagnosis only. Parts, refrigerant, repairs and
commercial equipment require other packages. Purifier servicing covers exterior
cleaning, visual filter-housing inspection and a basic flow check. Filters,
membranes, parts, installation, repairs and water-quality certification are
excluded. No package promises real qualification or water/food safety checks.

## Existing identities and shared appointments

FreshNest and SparkleSpace offer the new cleaning packages through their
existing agents. The expired cleaning example remains excluded. SpinCheck and
DrumCare offer refrigerator and purifier packages through their existing agents.
Each company's appointment capacity is shared across its packages: a washing
machine reservation blocks a refrigerator or purifier visit for the same
provider and appointment. Existing reservations retain their ownership.

`show services` opens four group cards. Cleaning and appliance groups include
the new packages; typed `show cleaning services` and `show appliance services`
also work. Package-specific questions precede matching, quote review and payment
approval. Existing quote binding, expiry, compensation and fresh replacement
approval rules apply to these packages.

## Upgrade after completing current tests

Stop the current runtime with Ctrl+C before copying its latest database. Use a
new target path; an existing target is refused. This keeps bookings made during
testing in the upgrade snapshot. The original remains unchanged.

```powershell
.\.venv\Scripts\python.exe -m servicesetu seed-demo --db data/demo-twelve-services-2026-10-23-to-25.db --days 3 --extended-catalogue --from-db data/demo-catalogue-2026-10-23-to-25.db
$env:SERVICESETU_MAILBOX = 'true'
$env:PAYMENT_MODE = 'mock'
$env:SERVICESETU_DB = 'data/demo-twelve-services-2026-10-23-to-25.db'
.\.venv\Scripts\python.exe -m servicesetu mesh
```

The copy retains bookings, quotes, payments, events, sessions, provider prices
and slots. New service offerings are added only in the target. Existing
offerings are not overwritten. Source and target are separate snapshots, so
continue using the target after switching. Keep the seed unchanged and one
runtime per identity. Do not re-register the existing profiles.

For a fresh demo without copied history, omit `--from-db`. Fresh seed dates are
the next three local dates; copied providers retain their existing dates and
reservations. `--full-catalogue` keeps the earlier eight-package seed behavior;
`--extended-catalogue` explicitly enables all twelve packages.

## Verification and evidence

The additional tests cover complete booking, test-payment reversal, replacement
approval, detail follow-ups, unit totals, material/type exclusions, shared
capacity, source-copy preservation and group discovery. The real local-uAgent
proof includes all four new package lifecycles alongside the earlier seven
flows. These checks do not establish ASI:One rendering or current Agentverse
delivery health. Complete the live UI check after switching the runtime.
