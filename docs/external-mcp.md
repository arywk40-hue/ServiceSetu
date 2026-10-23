# TomTom and Taskrabbit backend integrations

ServiceSetu connects to these services from its Python backend through the official MCP Python SDK (`mcp>=1.28,<2`). A Claude connector alone does not configure this application. The Concierge calls an allowlisted adapter, initializes the HTTP MCP session, lists tools, validates arguments against the current server JSON Schemas, and then renders results with the existing ACP envelope. External tool responses are never passed to the reasoning model as instructions.

## Setup

From the existing checkout, install the optional external dependencies alongside the normal runtime:

```sh
uv pip install --python .venv/bin/python -e '.[fetch,communications,external]'
```

Privately add `TOMTOM_API_KEY` to the existing `.env`. Preserve the existing `SERVICESETU_SEED`, Agentverse keys, database and payment settings. Never replace an existing `.env` with the example. The backend sends the key only in the `tomtom-api-key` header to `https://mcp.tomtom.com/maps?apps=false`; it is not sent to Taskrabbit, prompts, cards, URLs or public evidence.

TomTom's [official quick setup](https://docs.tomtom.com/tomtom-maps-mcp/documentation/quick-setup) requires MCP Server access and the underlying API permissions. It lists Map Display, Routing, Search, Geocoding, Reverse Geocoding and Traffic. This integration uses Geocoding, Search and Routing data tools; if the server refuses access, check the full documented product configuration in the developer portal. Do not enable paid usage or increase quotas merely to make a demo work.

Taskrabbit uses `https://mcp.taskrabbit.com/mcp`. No Taskrabbit credential variable is introduced: anonymous initialization and tool calls actually worked on October 23, 2026. This is evidence of present access, not a guarantee of unlimited or permanent public access. Auth failures and rate limits fail safely.

Restart exactly one mailbox runtime after changing environment or source:

```sh
SERVICESETU_MAILBOX=true PAYMENT_MODE=mock .venv/bin/python -m servicesetu mesh
```

Keep the original seed and database. Do not start another mesh for these same registered identities while one is already running. Mock remains the established all-in-chat booking demonstration; all existing payment modes are preserved.

## Read only operator checks

These commands use the same backend adapters as the Concierge. They create no booking, payment or Taskrabbit draft. Summaries are saved under ignored `artifacts/local/`; a passed backend check is not proof of ASI:One rendering.

```sh
.venv/bin/python -m servicesetu.mcp_check taskrabbit tools
.venv/bin/python -m servicesetu.mcp_check taskrabbit services --country US --postal 10001
.venv/bin/python -m servicesetu.mcp_check taskrabbit availability --country US --postal 10001 --service 'furniture assembly'
.venv/bin/python -m servicesetu.mcp_check tomtom tools
.venv/bin/python -m servicesetu.mcp_check tomtom geocode --location 'Mandi, Himachal Pradesh, India'
.venv/bin/python -m servicesetu.mcp_check tomtom search --service plumbers --location 'Mandi, Himachal Pradesh, India'
.venv/bin/python -m servicesetu.mcp_check tomtom search --service 'repair shops' --location 'Indiranagar, Bengaluru, India'
.venv/bin/python -m servicesetu.mcp_check tomtom route --origin 'SPECIFIC PUBLIC ORIGIN IN INDIA' --destination 'SPECIFIC PUBLIC DESTINATION IN INDIA'
```

Use public or synthetic locations for a showcase. A customer requesting a location lookup supplies that location for the corresponding external service. Do not put private addresses or task descriptions into screenshots, shell history or published evidence.

## Customer prompts and behavior

In the existing Concierge conversation, select `@servicesetu` and try:

- `TomTom plumbers in Mandi, Himachal Pradesh`
- `TomTom repair shops in Indiranagar, Bengaluru`
- `TomTom geocode Mandi, Himachal Pradesh, India`
- `TomTom route from SPECIFIC ORIGIN IN INDIA to SPECIFIC DESTINATION IN INDIA`
- `Taskrabbit plumber in Mandi, Himachal Pradesh`
- For a deliberately requested US demonstration only: `Taskrabbit services in US 10001` or `Taskrabbit furniture assembly in US 10001`.

TomTom returns at most five Indian location or business matches. It uses `tomtom-geocode`, `tomtom-fuzzy-search` (POI index, without guessed category codes), and `tomtom-routing`, only when the live server exposes them. Search returns businesses discovered through TomTom, with an explicit not-onboarded/not-verified label. It does not import providers, issue quotes, reserve slots or take payment. Routes require two unambiguous geocoded locations, use GeoJSON longitude/latitude order, and show meters/seconds as km/minute estimates. They do not represent technician availability, tracking or dispatch. Empty results do not fall back to fictional providers.

Taskrabbit's [published locations](https://www.taskrabbit.com/locations) do not include India. Its current MCP schemas are narrower than its global marketplace: postal codes must have five US digits, city/state are US style, and draft links allow only `en-US`. ServiceSetu therefore refuses India before calling Taskrabbit, collects an explicit country, and accepts US requests only. Other countries may have Taskrabbit websites but are not claimed supported by this connector. It never changes an Indian request to an overseas location.

For a supported US request, the Concierge shows the returned currency and rate basis, clearly qualifies hourly averages, and collects the actual scoping questions returned by the server. Answer using the form, or send `task answer: YOUR ANSWER`. Closed-choice answers must match the returned options. Before requesting a link it presents a review containing the resolved location, answers and price qualifications. Only **Create draft and continue on Taskrabbit** calls `generate_deep_link`.

That tool creates a Taskrabbit job draft. A secure Taskrabbit link is returned as **Continue booking on Taskrabbit** in the chat; the customer completes booking and any payment on Taskrabbit. No ServiceSetu booking or payment record is created. The link is not a confirmed appointment, service quote, payment, or reservation. ServiceSetu does not claim Taskrabbit cancellation or refund controls. This external handoff does not satisfy the primary all-in-chat workflow requirement and is separate from the mock demonstration.

## Reliability and access boundaries

- Each attempt has an 18-second overall deadline and seven-second HTTP/message timeouts. Read-only operations may retry once after transient transport or server failures. Auth errors, 429 responses, unsupported schemas and tool errors do not loop. Draft creation never retries automatically.
- An operation can call at most five allowlisted tools. Tool discovery has a maximum of two pages/80 tools, results are limited to 200 KB, and request arguments are bounded. Per-process admission limits allow eight operations per customer/session and forty overall per minute. These limits are not a billing or distributed quota guarantee.
- No arbitrary endpoint, general-purpose MCP tool execution, sampling access, local files, roots, customer wallet keys or payment tools are exposed to the servers. TomTom and Taskrabbit use separate connections; TomTom headers do not reach Taskrabbit.
- Taskrabbit state is stored under the existing owner/session key, with a ten-minute deadline and an unpredictable review token. Each scoped answer is bound to its current question. A database transaction claims draft generation before sending it; duplicates, stale/foreign cards and uncertain outcomes cannot create another draft automatically. Successful link retries reuse the stored link.
- Availability, rates, discovery results and route estimates never satisfy ServiceSetu quote approval. Existing matching, provider access, payments, cancellation recovery, lifecycle and history checks continue to enforce their own boundaries.

## TomTom allowances and attribution

The [current official pricing page](https://docs.tomtom.com/pricing), checked October 23, 2026, advertises free **monthly allowances per API**: Geocoding 20,000; Routing 20,000; previous-generation Search 2,500; Places Search Discover 5,000, Suggest 10,000 and Details 5,000. The MCP server runs on Orbis and bills underlying API usage. Confirm which API products your account is charged for; these are not a single combined allowance or an unlimited MCP grant. Avoid relying on older daily-quota figures. Account plans, product access, free quota and paid overages must be checked in the TomTom portal before a real pilot.

Data cards include visible **Location data © TomTom** attribution. Preserve TomTom and any third-party/source notices returned with data. This integration renders data cards, not map tiles or a TomTom basemap. If maps are added later, implement TomTom's required logo, map copyright and data-source notices using the applicable Maps SDK/API guidance and account terms; the data-card credit is not a claim that future map rendering is licensed or compliant. See [TomTom terms](https://docs.tomtom.com/legal/terms-and-conditions).

## Actual evidence and blockers

The implemented backend anonymously initialized Taskrabbit, discovered all three current schemas, listed **53 services** for the public test ZIP `10001`, and obtained available furniture assembly with **USD** hourly pricing and **two** scoping questions. These were read-only checks. No draft link, real booking or payment was created.

At implementation time `TOMTOM_API_KEY` was absent and the backend correctly returned `missing_key`. On October 23, 2026, after the operator configured the key privately, authenticated tool discovery succeeded and exposed `tomtom-geocode`, `tomtom-fuzzy-search`, and `tomtom-routing`. Live India-filtered geocoding returned 4 Mandi matches, plumber search returned 4 Mandi results, and repair-shop search returned 5 Indiranagar, Bengaluru results. The authenticated ASI:One Concierge then rendered the Mandi plumber results with `Location data © TomTom` and the clear discovered/not-onboarded/not-verified label. No ServiceSetu booking or payment was created. A route estimate attempt between two named Mandi landmarks was rejected as ambiguous; no route is claimed verified. Published country coverage plus these small live checks do not guarantee listing quality, completeness, availability or current business status. Never present local fixtures as live results.

Taskrabbit draft creation/link format is locally tested with protocol doubles; a real draft was deliberately not generated during read-only verification. Separately, the authenticated ASI:One Concierge visibly rendered the India refusal, qualified USD hourly estimate, external marketplace suggestion cards and both returned scoping forms. Synthetic task details and Small size were submitted through those forms. The final draft creation action was not performed. This is rendered client evidence, separate from the backend database and MCP checks. Provider permission, actual services, prices, coverage, availability, per-booking acceptance, completion and problem follow-up remain operator/provider responsibilities.

## Changed files

| File | Purpose |
| --- | --- |
| `servicesetu/external_mcp.py` | Official SDK connection, initialization, discovery, schema checks, limits, safe errors and retries |
| `servicesetu/discovery.py` | TomTom geocoding/POI/route adapters and Taskrabbit geography, availability and draft-link adapter |
| `servicesetu/external_conversation.py` | Owner/session scoped customer flow, returned scoping questions, explicit draft review and retry protection |
| `servicesetu/external_cards.py` | Existing ACP card schemas, labels, exact returned currency and route qualifications |
| `servicesetu/mcp_check.py` | Reproducible read-only backend connection checks with private local summaries |
| `servicesetu/conversation.py` | Routes explicit external requests to the adapters while retaining existing booking/payment flow |
| `pyproject.toml` | Optional `external` dependency extra |
| `.env.example` | Empty TomTom key variable and backend setup notes |
| `tests/test_external_mcp.py` | Protocol, result, geography, auth, retry, state/ownership and no-booking boundaries |
| `tests/fixtures/taskrabbit-mcp-tools.json` | Public input schemas observed from the actual anonymous server |
| `README.md`, `docs/external-mcp.md`, `docs/submission.md` | Setup, commands, evidence and remaining acceptance |

Previously present FET, Google Places and handoff work is retained. No seeds, private `.env` values, databases, runtime logs or private conversation evidence belong in GitHub.
