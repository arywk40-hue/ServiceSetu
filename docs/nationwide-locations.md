# Indian location intake and provider coverage

ServiceSetu accepts service requests for Indian cities and localities, including names outside a fixed alias list. This expands location intake; it does not establish a real nationwide provider network. Providers, credentials, appointments and payments remain fictional test data.

## Location collection

A request carries `city`, `area` (locality), optional `pincode`, and `country` (`IN`). Names are normalized for case and spacing; common city aliases are recognized. Close spelling matches require confirmation rather than silently moving a request. Unfamiliar valid names, including names in Indian scripts, are retained.

City and locality are sufficient for locality-based provider coverage. PIN is optional in intake and the search form. A provider declaring coverage only by PIN can request postal clarification; an unserved city does not require a PIN merely to report missing coverage. Format validation does not verify that a PIN exists or belongs to the entered locality. No postal-directory, geocoding or address-verification API is connected. India Post defines PIN as a six-digit code; see the [government postal standard](https://egovstandards.gov.in/postal-index-number-pin).

Explicit location corrections override earlier answers. A city change clears the previous locality and PIN; a locality change clears the previous PIN. Service, appointment, budget and package answers are retained. A location confirmation never approves a booking or payment.

Original Indiranagar, Bengaluru requests remain compatible without a PIN. If a PIN is supplied for that legacy demo area, it must match its declared 560038 coverage.

## Provider declarations

A provider can declare explicit coverage in its stored payload:

```json
{
  "coverage": [
    {
      "country": "IN",
      "city": "mumbai",
      "areas": ["powai"],
      "pincodes": ["400076"]
    }
  ]
}
```

City and locality restrictions must match; when a customer supplies a PIN, its declared restriction must also match. An omitted PIN does not block a locality-covered request. A region needs at least locality or PIN restrictions; malformed declarations and empty coverage lists provide no coverage. There is no nationwide wildcard. Providers without explicit coverage retain their original city/locality declaration; explicit declarations take precedence.

Coverage is enforced during matching, alternative-slot searches, quote creation, reservation and payment. Quotes include a location snapshot displayed at review. Cancellation recovery keeps the original location, appointment, service details and recorded maximum budget; moving to another city requires a new request. A company serving multiple regions shares its existing appointment capacity across those regions.

An accepted location with no covered provider receives a coverage-unavailable response. Providers from another locality are not offered as substitutes. No booking or payment is made.

## Service address before approval

After selecting a provider, the customer enters house/flat, building and street details; a landmark is optional. A structured form and a plain-text reply are supported. Use fictional addresses in the demo. The address is not parsed by the reasoning model and is not added to provider shortlist/explanation requests.

The address is collected before the short slot hold begins. Quote expiry and provider availability are rechecked on submission. The review shows the service area, entered address and exact price before approval. New conversation quotes require a saved address before approval/payment. Previously persisted legacy quotes/bookings remain readable.

The entered line is stored with the quote's city/locality/PIN snapshot in an append-only booking event. It is shown in booking status and customer history. This is customer-supplied data, not a verified address; the application does not geocode it, validate its real-world existence or check locality claims within the street text. The customer must review it.

`change address` before approval releases the current hold and requires a new review and approval token. A stale address form or approval cannot apply to a newer selection. Confirmed bookings require a new request to change address. Replacements reuse the original recorded address; the backend rejects a different address for that recovery. Older bookings without an address collect one on replacement selection.

Addresses are stored in the configured local database and travel through the existing customer chat and booking-agent transport. Database files remain ignored by Git. They are not encrypted by this change. Production deployment still needs a retention/deletion policy and appropriate access controls. No phone number or contact identity is collected in this step.

## Optional two-region demo

`seed-demo --nationwide-demo` creates a new twelve-package demo using the same sixteen provider identities and twenty-three agents. Eligible seeded providers gain fictional branches in:

- Indiranagar, Bengaluru, PIN 560038.
- Powai, Mumbai, PIN 400076.

Other Indian locations can be entered but have no available provider unless coverage is explicitly configured. Existing custom coverage declarations are retained. This option does not add real companies, perform document verification or connect food-delivery platforms.

Stop the running mesh before copying its database so its latest history is included. In PowerShell, from the repository folder:

```powershell
.\.venv\Scripts\python.exe -m servicesetu seed-demo --db data/demo-nationwide-2026-10-23-to-25.db --days 3 --nationwide-demo --from-db data/demo-catalogue-2026-10-23-to-25.db
$env:SERVICESETU_DB = 'data/demo-nationwide-2026-10-23-to-25.db'
$env:SERVICESETU_MAILBOX = 'true'
$env:PAYMENT_MODE = 'mock'
.\.venv\Scripts\python.exe -m servicesetu mesh
```

Use the actual active database as `--from-db` if a different copy is running. The command refuses to overwrite the destination. It retains copied bookings/history and existing provider slots; new providers receive appointments for the next three days at creation time. It does not refresh occupied or expired slots for existing providers. The original database remains unchanged. Credentials and identities remain the same; do not register the agents again or run their identities on two machines.

A normal restart on an existing database enables the new intake and coverage checks without adding Mumbai demo branches. The optional copy above is needed to test those branches.

## Validation

The automated suite covers unknown locations, Indian-script names, aliases, confirmation, PIN corrections, unserved areas, retained request details, provider coverage at booking boundaries, immutable quote locations, replacement restrictions, shared capacity and source-copy preservation. Local uAgent checks additionally exercise Mumbai AC and sofa-cleaning booking/cancellation/replacement lifecycles. They use local messaging and mock payments; they do not prove live Agentverse availability or real nationwide fulfilment.
