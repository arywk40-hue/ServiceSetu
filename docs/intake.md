# Service requests and appointment alternatives

Customers can describe the request in normal language, for example:

> My AC is not cooling. I am in Indiranagar, Bengaluru. Can someone come tomorrow at 10 AM, under INR 1,000?

ASI1 extracts the service, location, appointment and budget into structured fields.
The deterministic fallback supports AC/plumbing keywords, today/tomorrow,
explicit dates, AM/PM or 24-hour times and common INR budget formatting. It is a
limited fallback, not a replacement for general language understanding.

Missing fields are requested explicitly. Partial intake details are retained
within the same customer session, so a customer can reply with just `10 AM` or
`under INR 1000`. Vague periods such as morning require an exact time rather than
silently becoming a fixed appointment. Forms also accept ordinary day/time text.
The initial scope remains AC servicing and plumbing in Indiranagar, Bengaluru.

Location matching ignores letter case and extra spaces; Bangalore and Bengaluru
are the same supported city, and Indira Nagar normalizes to Indiranagar. Close
misspellings produce a location confirmation question, not an automatic location
change. Dissimilar names such as Gandhinagar are not treated as spelling variants.
Unsupported location values are removed from follow-up context so they cannot
keep overriding a customer's correction. Service, budget and appointment details
are retained while the location is clarified. A yes to this question confirms
only the location; quote review and payment approval remain separate.
Location-only corrections cannot overwrite the saved budget or appointment,
even if a model repeats unrelated fields. Internal budgets are stored in paise;
the model's follow-up context labels their converted value as `budget_rupees`.

Requests can contain frustration or worry as well as service details. Explicit
emotional wording can receive a short acknowledgement; it never supplies missing
details or authorizes a booking. Sentiment handling is limited and does not imply
that every emotion, language or ambiguous intention will be understood.

Provider shortlists separate price, appointment, document status, included work
and exclusions into labelled sections. The stored trust status controls the
document label: fictional mock-registry checks and provider-supplied documents
remain distinct. ASI1 comparisons return a quote identifier and a constrained
reason, which are validated against the actual quotes before text is rendered.
Unvalidated model prose is not displayed as evidence. With one quote, a local
description avoids an unnecessary comparison call. Customers can reply `option 1`
to review a provider; that selection still does not authorize payment.

When no provider matches a requested future appointment, Matching checks other
persisted, future provider slots against the same service, location, budget,
credential validity and reservation rules. Up to four appointment choices are
shown with explicit local dates and starting prices. These are availability
observations, not quotes, holds, payments or confirmations.

The customer chooses an appointment card or replies `option 1`, `option 2`, etc.
Only then is the request time changed and provider availability checked again.
Card selections are bound to the current session's option list; stale or foreign
cards are rejected. Selecting a time never substitutes for provider selection,
quote review or approval. A concurrent reservation can remove an offered option.

Cancellation recovery never suggests a different appointment or higher budget.
If no replacement fits the original limits, the customer must make a new request
to change those limits. Existing confirmed bookings are not automatically changed
by browsing availability or making another request.

Local tests cover date rollover, follow-up clarification, form input, stale cards,
cross-session rejection, budget constraints, changed capacity and recovery limits.
The local uAgent proof also exercises appointment selection before booking and
recovery. Actual ASI:One rendering and ASI1 interpretations require live acceptance.
