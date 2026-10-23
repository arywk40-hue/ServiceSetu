# Real Local-Service Discovery via Google Places API (New)

ServiceSetu includes an optional Google Places API (New) Text Search adapter and ASI:One result cards. Live Google Places is disabled for this showcase: keep `GOOGLE_PLACES_API_KEY` unset. No live Google search, account billing or India result coverage has been verified. The adapter is covered by local tests with mocked responses.

The card and booking boundaries are implemented, but live rendering and Google policy/attribution acceptance remain unverified. In the video, call this an implemented optional adapter with mocked tests; use the separately verified TomTom results for live discovery evidence.

---

## 1. Architecture & Security

```
Customer (ASI:One)
       │
       ▼
Concierge Agent (Conversation.handle)
       │
       ├─► Live Discovery Intent? (e.g. "Find real plumbers in Mandi, HP")
       │         │
       │         ▼
       │   servicesetu.places.search_places() (Server-side only)
       │         │
       │         ▼
       │   POST https://places.googleapis.com/v1/places:searchText
       │   [Headers: X-Goog-Api-Key, X-Goog-FieldMask]
       │         │
       │         ▼
       │   Returns up to 5 real businesses
       │         │
       │         ▼
       │   ACP Cards (cards.places_results)
       │   - Clear label: "Found on Google Maps; not onboarded to ServiceSetu"
       │   - Working Google Maps link
       │   - "View on Google Maps" CTA
       │   - NO booking, appointment reservation, or payment
       │
       └─► Onboarded Booking Flow?
                 │
                 ▼
           Matching & Verification Agents
           (Only consenting providers with configured arrangements)
```

### Implemented boundaries and remaining policy checks
- **Server-side only:** The `GOOGLE_PLACES_API_KEY` is loaded exclusively from the local server environment (`os.getenv("GOOGLE_PLACES_API_KEY")`). It is never exposed in ACP card metadata, model prompts, logs, or git commits.
- **Explicit Field Mask:** Requests request only necessary fields:
  `places.id,places.displayName,places.formattedAddress,places.googleMapsUri,places.rating,places.userRatingCount,places.businessStatus,places.pureServiceAreaBusiness`.
- **Limited application storage:** Only discovered place IDs are saved in the session, not business details in provider/quote/booking/payment tables. ASI:One may retain rendered chat responses, so platform retention must be reviewed before enabling live Google content. No policy compliance certification is claimed.
- **Safe transport/results:** Requests use the fixed official endpoint, up to five results and bounded retry/timeout behavior. Raw upstream errors and credentials are not echoed. Card links accept HTTPS Google Maps URLs only. Booking requests with appointment/budget constraints remain in the booking workflow.
- **Geography:** `regionCode=IN` is regional behavior, not a strict country filter or proof that a business covers the requested service area. No India-only search-result guarantee is claimed.
- **Attribution and public policies:** The prototype has a textual Google credit. Before displaying live Google data, review Google's required Google Maps logo/text treatment, third-party attributions, public Terms of Use and Privacy Policy, and content retention restrictions. See the [official Places policies](https://developers.google.com/maps/documentation/places/web-service/policies). These live-enablement checks are not completed.
- **Fail-Closed Resilience:** If the Google Places API is unavailable, timed out, or unauthenticated, Concierge returns an honest error card. An API failure **never silently substitutes fictional demo providers**.

---

## 2. Google Cloud Setup, Billing & API Restrictions

Follow these official steps to obtain and configure an API key:

### Step 1: Create a Google Cloud Project
1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Click the project dropdown at the top and select **New Project**.
3. Name your project (e.g., `ServiceSetu-Local-Discovery`) and click **Create**.

### Step 2: Enable Billing
1. Navigate to **Billing** in the Google Cloud Console.
2. Link an active billing account.
3. Check the [current per-SKU pricing and allowances](https://developers.google.com/maps/billing-and-pricing/overview). Requested fields affect billing. Do not assume an old blanket monthly credit or free searches. No billing setup or live request is needed for the showcase's mocked adapter tests.

### Step 3: Enable Places API (New)
1. Go to **APIs & Services > Library**.
2. Search for **Places API (New)**.
3. Click **Enable**.
   *(Reference: [Places API (New) Overview](https://developers.google.com/maps/documentation/places/web-service/text-search))*

### Step 4: Generate an API Key
1. Go to **APIs & Services > Credentials**.
2. Click **Create Credentials > API Key**.
3. Copy the generated key.

### Step 5: Apply Security Restrictions (Recommended)
1. In the Credentials list, click on your new API Key to edit it.
2. Under **API Restrictions**:
   - Select **Restrict key**.
   - Check **Places API (New)** only.
   - Click **Save**.
3. Under **Application Restrictions**:
   - For production servers, select **IP addresses** and enter your server's IP address.
   - For local development, you may leave as None or restrict to your development machine.

### Step 6: Configure Usage Quotas & Budget Alerts
1. Go to **APIs & Services > Places API (New) > Quotas**.
2. Set a maximum daily request quota (e.g., 500 requests/day) to prevent accidental overages.
3. Set a Google Cloud **Budget Alert** (e.g. at $1.00) in **Billing > Budgets & alerts** to receive email notifications if usage exceeds expectations.

### Step 7: Configure ServiceSetu
Add the key to your private `.env` file (do not commit `.env`):
```ini
GOOGLE_PLACES_API_KEY=AIzaSy...your_actual_key_here...
```

---

## 3. The Booking & Payment Boundary

A business discovered on Google Maps is **unpartnered**. ServiceSetu strictly enforces the following boundary:

| Feature | Onboarded Provider (Demo / Pilot) | Discovered Business (Google Maps) |
|---|---|---|
| **Origin** | Verified seed or operator-approved pilot | Live Google Places API (New) Text Search |
| **Pricing** | Bounded, binding quote in INR paise | None invented; subject to direct inquiry |
| **Appointments** | Verified slot hold and confirmation | None invented; contact provider directly |
| **Consent & Agreement** | Recorded consent & booking arrangement | Unpartnered; no agreement with ServiceSetu |
| **Credentials** | Mock registry or manual operator review | None; Google rating is not verification |
| **Primary Action** | "Review quote" / "Approve payment" | "View on Google Maps" |
| **Booking & Payment** | Supported via deterministic state machine | **Strictly prohibited & rejected** |

If a customer attempts to select, approve, or pay for a Google Maps business ID, ServiceSetu immediately rejects the action:
> *"Businesses found on Google Maps are not onboarded to ServiceSetu. They cannot be booked, scheduled, or paid through ServiceSetu. Only onboarded providers with verified booking arrangements may be booked."*

---

## 4. Example Customer Prompts

Example prompts for the optional adapter are below. They produce only a missing-key message in the current showcase; the example locations are not live Google coverage evidence:

```text
Find real plumbers in Mandi, Himachal Pradesh.
Find AC service businesses in Indiranagar, Bengaluru.
Find cleaning services in Powai, Mumbai.
Find real electricians in New Delhi.
Search real sofa cleaning in Whitefield, Bengaluru.
```

### Clarifying Ambiguous Locations
If a customer provides a typo or an incomplete location, ServiceSetu clarifies rather than guessing:
- *"Find real AC service in Indiranagr"* -> Concierge proposes: *"Did you mean Indiranagar? Reply yes to search Google Maps there..."*
- *"Find real plumbers"* -> Concierge prompts: *"Please specify your city and locality in India to search for local businesses on Google Maps..."*

### Unserved Area Recommendations
When a customer submits an appointment request for a locality not covered by onboarded providers (e.g. Mandi, HP):
```text
Customer: Plumbing in Mandi, Himachal Pradesh tomorrow 10am under INR 1000
```
ServiceSetu returns:
1. Clear statement: *"No onboarded demo provider currently covers Mandi, Himachal Pradesh for Plumbing. Your location was accepted. No appointment was reserved or payment taken."*
2. Suggestion: *"To discover real local businesses on Google Maps, send: 'Find real plumbing in Mandi, Himachal Pradesh'."*
3. ACP Card CTA: **[Search Google Maps]** button that triggers Places discovery with one tap.

---

## 5. Verification & Blocker Status

Run the verification script to check your local configuration:
```sh
.venv/bin/python -m servicesetu.places
```

- **Current Status:** `GOOGLE_PLACES_API_KEY` is not present in the local environment.
- **Verification Blocker:** Live Google Places queries require an active `GOOGLE_PLACES_API_KEY` in `.env`.
- **Automated Test Evidence:** 23 local tests in `tests/test_places_discovery.py` passed, including missing fields, empty/error responses, credential redaction, HTTPS Maps links, bounded results, preservation of constrained booking requests, optional-dependency behavior and the prohibition on booking discovered businesses. These do not prove Google access or live ASI:One rendering.
