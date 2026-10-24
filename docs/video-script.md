# ServiceSetu silent video and voiceover script

Team: **Ariyan Bhakat** and **Palak Mittal**.

Current cut: **ServiceSetu_Demo_v2.mp4**, 4 minutes 54 seconds, silent. It is an edited walkthrough assembled from actual ASI:One screen captures, with short captions, a backend architecture diagram and a dedicated FET implementation section. It is not continuous real-time screen recording. The owner adds their voice and uploads the final video. Raw captures and video stay local and are excluded from Git.

The [official Fetch-A-Thon 3.0 hackpack](https://innovationlab.fetch.ai/events/hackathons/fetch-a-thon-3/hackpack), checked 24 October 2026, specifies a **3–5 minute** video and **mandatory submission through the ASI:One event dashboard Project Submission Agent**. Follow any additional organizer instructions, including Devpost if separately requested.

## What the recorded conversation proved

A new authenticated conversation named **Book TomTom Plumbers And AC Service** returned live TomTom Mandi results, then completed a new mock booking and recovery. The successful branch ran on 24 October for **25 October 2026 at 10 AM IST**, maximum INR 1,000. CoolCare at INR 699 was explicitly approved and confirmed, then cancelled through the existing authenticated local operator command. The simulated payment was reversed. Breeze at INR 749 required fresh review and approval, then was confirmed. All **18 history events** rendered. Backend state was checked independently. Earlier quotes in the same conversation expired safely; a short invalid address was rejected and replaced with fictional details. Do not describe the whole session as a first-attempt uninterrupted success.

TomTom remains configured and returned four real discovered business results. Taskrabbit India refusal also rendered. No Taskrabbit draft, reservation or payment was created. Google Places is implemented and tested locally with mocked responses; live Google calls remain disabled.

## Changes in this cut

The opening now starts on the actual chat, with a short title. Long side panels and slogan text were removed. The [architecture diagram](architecture.md) is based on the current Python backend. A dedicated section shows native FET Dorado source and the rerun of all **18 FET tests in 1.312 seconds**. Those tests use ledger doubles; no live FET card, wallet transfer or refund is claimed. The original silent cut is preserved locally.

## Timed voiceover

| Time | Screen | Suggested narration |
| --- | --- | --- |
| 0:00–0:08 | ServiceSetu | This is ServiceSetu. Here’s an AC booking in ASI:One, including recovery when the provider cancels. |
| 0:08–0:28 | How it works | The customer talks to one Concierge through Agentverse. Behind it, specialist and provider agents handle quotes, approval, booking and recovery. They share a SQLite database. TomTom and Taskrabbit are separate discovery tools. The Payment agent uses the configured payment rail. |
| 0:28–0:46 | TomTom search | First, TomTom searches for plumbers in Mandi. Four business results appear with TomTom attribution. These are discoveries, not verified or onboarded ServiceSetu providers, and the search does not create a reservation or payment. |
| 0:46–1:06 | The service request | The customer then requests AC service in Indiranagar, Bengaluru, for the twenty-fifth of October at ten AM, under one thousand rupees. CoolCare offers a visit for six hundred ninety-nine rupees; Breeze offers seven hundred forty-nine. |
| 1:06–1:18 | Provider comparison | The comparison includes scope, price, appointment and honest demo trust labels. Lapsed AC is excluded because its mock credential expires before the service date. |
| 1:18–1:42 | The quote | The exact CoolCare quote is reviewed before approval: one AC service visit, its exclusions, the appointment, six hundred ninety-nine rupees, and the temporary hold deadline. Parts or extra work require a new quote. Earlier quotes expired safely, and fresh quotes were requested without changing the expiry protections. |
| 1:42–2:00 | Approval and confirmation | The current quote is explicitly approved. CoolCare is confirmed with simulated payment paid and no gateway charge. The original approval, payment and confirmation are also recorded in the audit. Backend evidence was checked separately from what ASI:One displays. |
| 2:00–2:18 | The provider cancels | Next, the operator uses the existing authenticated control to simulate the assigned provider cancelling. The customer receives the cancellation and the simulated reversal in the same conversation. This represents an unavailable provider; it is not an invented direct message from a real business. |
| 2:18–2:36 | A replacement offer | Recovery looks for an alternative within the original service, area, appointment and one thousand rupee limit. Breeze is eligible at seven hundred forty-nine rupees. Offering a replacement does not automatically confirm it or reuse the original customer approval. |
| 2:36–2:58 | The replacement quote | The customer reviews Breeze separately. A short invalid address was rejected and corrected using fictional demo details. The new exact quote, exclusions, appointment, price and hold deadline are shown. Fresh approval is required before its separate simulated payment. |
| 2:58–3:16 | Breeze is confirmed | After that fresh approval, Breeze is confirmed for the original appointment. The payment rail again says simulated, with no gateway charge. The database independently confirms the original cancellation and refund status, and this approved replacement. |
| 3:16–3:26 | Booking history | The customer asks for the history. It shows the original request, quote, approval, simulated payment and confirmation. |
| 3:26–3:36 | Cancellation history | Next are the provider cancellation, simulated reversal and replacement search. The original appointment and budget are retained. |
| 3:36–3:46 | Replacement history | The final events show the corrected demo address, fresh Breeze approval, its simulated payment and the confirmed replacement. |
| 3:46–3:56 | Booking controls | The confirmed booking card also exposes messaging, message history, completion and problem reporting. Here we show those controls; we do not claim a real service was completed or a problem resolved. |
| 3:56–4:06 | Taskrabbit in India | Taskrabbit is unavailable for the India request. The response offers TomTom discovery instead of substituting an overseas location. Supported US assistance has a separate external handoff and never confirms a ServiceSetu booking. |
| 4:06–4:26 | FET testnet payments | FET payments are implemented for Dorado testnet. ServiceSetu uses fet_direct, a native fetch1 wallet and a stored invoice. It checks the ledger transfer and blocks transaction reuse. All eighteen local tests pass. Live wallet signing and ASI:One checkout still need verification. |
| 4:26–4:34 | Other integrations | Google Places is implemented but live-disabled. Stripe and Razorpay test support remains optional; neither was used for this booking. |
| 4:34–4:44 | Verification | The core suite passed three hundred forty-three tests. The eighteen FET tests passed again using ledger doubles. These tests do not prove live wallet checkout. |
| 4:44–4:54 | ServiceSetu | That’s the completed demo. The repository and run instructions are public. A real pilot still needs a consenting provider. |

## Actual new history

All times are AM IST on **24 October 2026**. This is an outline of the actual rendered history, not a fabricated transcript to paste into ASI:One.

1. 03:10:05 — Service request received; appointment 25 October 10 AM IST, maximum INR 1,000.
2. 03:10:05 — CoolCare quote received: INR 699.
3. 03:10:50 — CoolCare temporarily held; approval required; hold expires 03:12:50.
4. 03:10:50 — Service address skipped for now.
5. 03:10:55 — Exact CoolCare quote approved.
6. 03:10:55 — Simulated test payment started: INR 699.
7. 03:10:55 — CoolCare booking confirmed.
8. 03:11:26 — CoolCare provider cancellation; test payment reversed.
9. 03:11:26 — Reserved appointment released.
10. 03:11:26 — Recovery request retained the original appointment and budget.
11. 03:11:26 — One eligible replacement found; fresh review and approval required.
12. 03:11:26 — Breeze quote received: INR 749.
13. 03:13:59 — Short address rejected by validation; no new booking confirmed.
14. 03:14:40 — Breeze temporarily held; approval required; hold expires 03:16:26.
15. 03:14:40 — Fictional service address recorded for review.
16. 03:14:59 — Exact Breeze quote freshly approved.
17. 03:14:59 — Separate simulated test payment started: INR 749.
18. 03:14:59 — Breeze replacement confirmed for the original appointment.

## Prompts and operator step

Use the same conversation addressed to `@servicesetu`:

```text
TomTom plumbers in Mandi, Himachal Pradesh, India
AC service in Indiranagar Bengaluru tomorrow 10am budget 1000
```

Choose the current CoolCare review, skip the optional address, read the exact quote and explicitly approve test payment. If expired, send the original service request again and review fresh quotes. After actual confirmation, use the authenticated local operator cancellation command for the actual assigned provider and booking:

```sh
.venv/bin/python scripts/cancel_provider.py ASSIGNED_PROVIDER_ID BOOKING_ID
```

Wait for the cancellation, simulated reversal and replacement offer. Review Breeze, use only fictional address details or skip, explicitly approve the new exact quote, wait for its actual confirmation, then send `show what happened`. Do not click old approval cards while replaying the video.

## Before submission

- Add your own voiceover to the silent video and verify the final audio/video length remains 3–5 minutes. No voice recording is included.
- Share **this new conversation** through ASI:One Share and verify the resulting public shared-chat URL without your session. A private `/chat/` URL is insufficient. The owner will supply this link; none has been verified by this task.
- Submit the public repository and agent profile URLs using the mandatory ASI:One event dashboard Project Submission Agent. The repository is https://github.com/arywk40-hue/ServiceSetu; the Concierge profile is linked in README.
- Hosting remains unresolved: the laptop need not stay on for days, but a verified persistent remote host is required for fresh interactions while it is off. See [free hosting options](hosting.md). No paid service or cloud deployment was created.
- One fresh journey passed; this is not a root-cause fix or continuous-uptime guarantee for the earlier mailbox timeouts/401.
- Do not expose private configuration, approval/control tokens, customer data, private chat URLs or wallet secrets. No live gateway/on-chain transaction, real provider verification or real service reservation is claimed.
