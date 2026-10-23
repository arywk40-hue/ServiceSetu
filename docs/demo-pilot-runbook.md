# ASI:One demonstration and one-business pilot

This work builds on GitHub `bf708c2`, inspected before implementation. The original checkout was seven commits behind; it was fast-forwarded without changing the seed, identities, registration profiles or the untracked handoff document. No provider has been contacted or joined.

## Latest payment choice is Razorpay test

The user selected Razorpay after checking Stripe's invite-only onboarding in India. Set `PAYMENT_MODE=razorpay_test`, `RAZORPAY_KEY_ID=rzp_test_…` and `RAZORPAY_KEY_SECRET` privately in `.env`. Run `.venv/bin/python -m servicesetu.razorpay_payments` for read-only test authentication, then restart the single mailbox mesh. No Razorpay credentials were available during implementation, and no actual test capture/refund is claimed.

After exact quote approval, ASI:One presents a labelled Razorpay test link. Checkout opens on Razorpay's hosted page; return to the same conversation and send `check payment`. The Payment Agent and 30-second monitor fetch the saved link and captured payment from Razorpay, verify booking/quote/owner hash, INR amount and order linkage, then confirm or compensate. No native embedded Razorpay client support is claimed. `resume checkout` reuses the same link. Customer SMS/email notifications are disabled and no customer contact details are sent by the integration.

Link creation uses the booking's unique reference and a persisted operation claim. A lost create response is recovered by reference lookup; an unresolved outcome is not re-created. Refunds use a stable `X-Refund-Idempotency` key and remain `refund_required` until the API confirms `processed`. Local coverage adds 14 Razorpay API-double tests; total unit suite is 280 tests. See [Razorpay create link](https://razorpay.com/docs/api/payments/payment-links/create-standard/), [fetch link](https://razorpay.com/docs/api/payments/payment-links/fetch-id-standard), and [idempotent refund](https://razorpay.com/docs/api/refunds/normal-refunds-idempotent). Existing mock and Stripe test modes remain available.

## Inspection and changes

Already implemented: deterministic matching and holds, immutable quotes, quote/token approval, mock and embedded Stripe test rails, cancellation/recovery, booking history, encrypted booking messages, local provider inbox and completion logic. The baseline passed 234 tests with loopback networking enabled. Four inbox tests require permission to bind a local socket; their sandbox errors were environmental.

Gaps addressed:

- Persist the payment rail with each payment. Switching runtime modes cannot settle a Stripe intent through mock payments or label its cancellation as a simulated refund.
- Retrieve the stored checkout on retry; keep a stable creation/refund idempotency key. Resume checkout uses saved consent and does not approve a new quote. Recover a lost session-create response or commit through reconciliation.
- Recheck service coverage/availability at settlement. An expired/cancelled hold or failed provider confirmation releases the slot and requires a test refund when capture succeeded. Failed refunds remain `refund_required`; they do not prevent the provider cancellation notice or recovery.
- Require the payment commit's original customer **and ACP session**. A reference-free, delayed `RejectPayment` cannot cancel a later/confirmed booking.
- Queue payment/cancellation result notices for delivery to the original conversation. Transient customer-reply failures have bounded retries with the same message ID; `status` can retrieve a missed shortlist.
- Expose messaging, completion, history and problem reporting in status cards with text fallbacks. Completion is customer-owned and idempotent. Problems are encrypted, booking-linked, acknowledged as received, and visible through a private operator export. No automated dispute/refund decision is made.
- Add one local pilot import/acceptance command using existing provider identity `p4`. Real pilot and fictional records have distinct labels; manual checks are described explicitly, without a mock registry badge. Fictional capacity is disabled in the pilot database.

## Run a fresh demo

Install the existing environment including messaging support:

```sh
uv pip install --python .venv/bin/python -e '.[fetch,communications]'
.venv/bin/python -m servicesetu prove
.venv/bin/python -m servicesetu seed-demo --db data/judging-demo.db --days 3
```

Use a new database filename each time; existing dates/bookings are preserved. In the private `.env`, point `SERVICESETU_DB` to that file, set `SERVICESETU_MAILBOX=true`, choose `PAYMENT_MODE=mock` for an entirely in-chat demo, `razorpay_test` for external Razorpay TEST checkout, or `stripe_test` for embedded Stripe TEST checkout, and keep the existing seed and Agentverse configuration unchanged. Start exactly one mailbox mesh for these identities:

```sh
.venv/bin/python -m servicesetu mesh
```

Open the [existing Concierge](https://asi1.ai/ai/agent1q02ftm6eu39lw0vc5kh3uhr4gtkkeqd6jpcaxzn4gyyrc2ac0p9ecvl39sz). Keep this same conversation for ownership and all lifecycle actions. When replying in a general chat, directly mention `@servicesetu` or select it as the recipient.

1. Send `AC service in Indiranagar Bengaluru tomorrow 10am under INR 1000` (or plumbing under INR 800). Supply any missing location, appointment or budget details.
2. Compare eligible providers, prices, scope and honest trust labels. Select **Review quote** or send `option 1`.
3. Add a fictional visit address or **Skip for now**. The review shows the exact price, scope, exclusions, appointment, cancellation policy and hold deadline.
4. Explicitly choose **Approve test payment**. The review also includes the exact `approve BOOKING_ID QUOTE_ID TOKEN` fallback. Generic yes/approval prose cannot authorize a different quote.
5. Mock mode immediately returns a confirmed **simulated** payment, entirely in the conversation and with no gateway charge. Stripe mode sends the embedded **Stripe TEST** checkout. Razorpay mode presents an external hosted **Razorpay TEST Payment Link**: open it, complete the test payment, return to this same ASI:One conversation and send `check payment`. Server-side verification, not the checkout callback or customer claim, confirms the booking. Use `status` to refresh; `resume checkout` reopens only the previously approved payment while its hold remains valid.
6. The operator triggers cancellation of the assigned fictional provider, using the private demo token already configured:

   ```sh
   .venv/bin/python scripts/cancel_provider.py p1 BOOKING_ID
   ```

7. Observe the cancellation notice and fresh alternatives within the original location, appointment, scope and budget. If delivery fails, send `status`, then `recover`. Review the replacement and explicitly approve its fresh quote/token; it has a separate test payment. Confirm the replacement status.
8. Send `show what happened`. When completed, history includes the original quote/approval/payment, cancellation and reversal status, replacement proposal, new approval and new confirmation. `audit details` preserves access to original records. The replacement requires its own explicit quote approval and payment; it never inherits the original consent.
9. Send `message provider: Please use the fictional side gate.`, then `show messages`. The operator can open the existing provider inbox against the same database for the assigned provider. After work, use **Confirm completion** and its confirmation review, or send `complete service`.
10. Use **Report a problem** or `report a problem: Synthetic issue for the operator`. Check its acknowledgement and booking history. Reporting does not claim resolution or a refund.

Razorpay's hosted checkout opens outside ASI:One and returns to the conversation. This conflicts with the current official Fetch-A-Thon 3.0 hackpack's mandatory rule that the complete primary workflow be demonstrated entirely inside an ASI:One conversation. Use `PAYMENT_MODE=mock` for the mandatory all-in-chat demonstration; it returns a clearly labelled simulated payment and creates no gateway transaction. Razorpay hosted test checkout can be demonstrated separately as an integration path, but should not be described as satisfying that all-in-chat requirement. The hackpack lists Payment Protocol as a bonus criterion. Terminal commands are operator controls and local proof tools.

## Enable Stripe test payments

Use keys from the same Stripe test account/sandbox. Privately configure `STRIPE_SECRET_KEY` (`sk_test_…`), `STRIPE_PUBLISHABLE_KEY` (`pk_test_…`) and `PAYMENT_MODE=stripe_test` in `.env`. Do not paste keys in chat, command arguments, logs, screenshots or commits. Live keys are refused. The card-only embedded checkout uses `redirect_on_completion=never`, so it does not redirect the customer out of the conversation. `STRIPE_RETURN_URL` is retained only for compatibility with older configuration; this path does not use it.

```sh
.venv/bin/python -m servicesetu.stripe_check
```

This reads credentials privately, checks test authentication and prints no keys or balance data. It creates no payment and is not checkout proof. Restart the single mailbox mesh after changing payment mode. Use a fresh booking; payment rail switching on an existing intent is deliberately rejected.

During an actual test, verify the session and single PaymentIntent in the Stripe **test** dashboard. Retry the same approval/resume and commit; they must retain one booking/payment. Cancel a paid booking and verify the test refund. Let a hold expire, then finish checkout: it must never confirm and must refund the captured test payment. The short booking hold is two minutes; Stripe session expiry is separate, and the monitor expires unpaid checkouts after cancellation/hold expiry. `pending` and `refund_required` are unfinished compensation states, never success claims. No real-money checkout, payouts or escrow are enabled.

The metadata follows the [official Fetch embedded Stripe example](https://github.com/fetchai/innovation-lab-examples/blob/main/stripe-horoscope-agent/stripe_payments.py); card payloads follow [official ACP schemas](https://docs.agentverse.ai/documentation/advanced-usages/predefined-card-schemas). Stripe's [idempotency rules](https://docs.stripe.com/api/idempotent_requests) and [Checkout session lifecycle](https://docs.stripe.com/api/checkout/sessions) inform retries and expiry. SDK doubles verify our boundaries, not client rendering or actual gateway outcomes.

## One willing plumbing business, one area

Use an isolated `data/pilot.db`, not a judging/demo database. The first pilot supports one agreed fixed-price plumbing/tap visit package in one area. The trusted operator and provider must be available together during booking, because the current hold is short. All payments remain simulated or Stripe test transactions; agree on any real-world service/payment arrangements separately before an actual visit.

Before enabling a record, the operator obtains permission directly from the willing business and records the agreement privately: business name, one service scope, exclusions/parts policy, fixed total including agreed fees, locality/PIN coverage, appointment slots, cancellation handling, and who can accept work. Explain what customer address/messages will be shared, the local-only inbox, test-payment limitation, and how to stop the pilot. Ask permission to enter these business details. This task has not performed those actions.

Create `data/pilot-provider.json` privately. This intentionally incomplete template cannot be imported until actual agreement and availability are recorded:

```json
{
  "provider_id": "p4",
  "service": "plumbing",
  "name": "REPLACE WITH AGREED BUSINESS NAME",
  "scope": "REPLACE WITH EXACT AGREED TAP VISIT SCOPE",
  "exclusions": "REPLACE WITH AGREED PARTS AND EXTRA-WORK EXCLUSIONS",
  "amount_paise": 0,
  "city": "bengaluru",
  "area": "indiranagar",
  "pincodes": ["560038"],
  "slots": ["REPLACE WITH PROVIDER-CONFIRMED FUTURE ISO SLOT WITH TIMEZONE"],
  "permission_obtained": false,
  "availability_confirmed": false,
  "agreement_reference": "PRIVATE LOCAL AGREEMENT REFERENCE",
  "operator": "REPLACE WITH OPERATOR NAME",
  "checked_items": ["DESCRIBE EXACTLY WHAT YOU ACTUALLY CHECKED"],
  "review_valid_until": "REPLACE WITH YYYY-MM-DD"
}
```

Examples of check descriptions, **only if actually performed**: owner gave permission on a recorded date; owner confirmed the menu/price; owner confirmed the named service area and appointment slots. Do not claim a licence, government identity, registry check or background check unless that specific check occurred. Manual review validity is an operator review window, not a certification.

```sh
.venv/bin/python -m servicesetu.operator --db data/pilot.db import-pilot --config data/pilot-provider.json
```

The command reuses `p4`; it creates no new public registration or seed. Other fictional providers remain stored for compatibility but are unavailable and cannot be offered as pilot recovery alternatives. Old databases lacking a record label are treated as demo records. Active held/confirmed bookings block reconfiguration.

Point the single mesh at `data/pilot.db`. When the customer holds/reviews a quote:

```sh
.venv/bin/python -m servicesetu.operator --db data/pilot.db queue
.venv/bin/python -m servicesetu.operator --db data/pilot.db accept BOOKING_ID --operator "OPERATOR NAME"
```

The operator first confirms that exact appointment, scope and price with the business, then records acceptance. This does **not** supply customer consent. The customer must approve the quote separately; approval attempted before operator acceptance explains that it is waiting. Retry the same approval after acceptance while the hold is active, or request a fresh quote if it expired. New holds/quotes require new operator acceptance.

For visit coordination, set `SERVICESETU_DB=data/pilot.db` in the provider-inbox terminal and run `python -m servicesetu provider-inbox --provider p4`. Its private token is saved to an ignored owner-only `.token` file rather than printed. The operator opens that file locally and supplies it to the assigned provider on the same PC. The inbox lists only that provider's confirmed work; it does not expose other customers/providers. No public provider portal is added.

The customer confirms completion in their ASI:One conversation. The operator records provider cancellation when necessary:

```sh
.venv/bin/python -m servicesetu.operator --db data/pilot.db cancel BOOKING_ID --operator "OPERATOR NAME"
.venv/bin/python -m servicesetu.operator --db data/pilot.db reports --output data/problems-review.json
.venv/bin/python -m servicesetu.operator --db data/pilot.db acknowledge PROBLEM_ID --operator "OPERATOR NAME"
```

Reports are exported only to a new private file under `data/`; the command never prints report bodies. Review that file locally, agree the next action with the customer/business, and record acknowledgement. No automatic resolution, discretionary refund, payout or customer/provider credential bypass exists. With one business, cancellation may yield **no eligible alternative**; explain that honestly instead of mixing fictional providers into a real pilot.

The operator controls the local machine, database and encryption key. Keep private backups together, restrict machine access, define deletion/retention with the participants, and avoid real customer data until they agree to these limits. The loopback inbox is for an operator-supervised pilot, not remote public hosting or production readiness. No Swiggy or API Setu integration is included.

## Evidence and remaining acceptance

Local evidence goes under ignored `artifacts/local/`; historical published snapshots remain unchanged. The final saved proof report has 280 passed checks, 0 failed, 0 skipped, and 14 passed local uAgent workflows. Consult `docs/submission.md` for current results. Local tests and local uAgent dispatch do not establish live checkout. In the October 23 signed-in chat, provider comparison/quote review, simulated confirmation, cancellation/refund status and an eligible replacement card rendered. The offered replacement quote expired before approval; subsequent fresh recovery delivery timed out. Replacement approval, confirmation and combined history therefore remain unverified live. Razorpay credentials are absent, so authentication, actual test checkout, capture and refund are blocked. Registration evidence from October 13 remains historical unless explicitly rechecked.

Before claiming a completed live demo, observe all of: rendered intake/shortlist/review/status cards; approval followed by configured payment; confirmation; actual cancellation notice; fresh replacement approval and confirmation; readable combined history; messages; completion; report acknowledgement. For Stripe, separately observe a real **test** Checkout/PaymentIntent and refunds in the test dashboard. A provider agreement, business details, confirmed slots, per-booking acceptance and problem follow-up all require real operator/provider action.
