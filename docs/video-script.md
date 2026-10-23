# ServiceSetu submission video script

Target length: about 4 minutes 50 seconds. Record the actual ASI:One conversation, with readable cards and cursor actions. The owner records and uploads the video. No video file is supplied by this document.

Use the previously completed conversation as a **recorded walkthrough** while live mailbox delivery is unstable. It was requested on 23 October for 24 October 2026 at 10 AM IST. Do not call that conversation a new live run. Do not click its expired approval buttons. For a genuinely new recording on 24 October, `tomorrow 10am` means **25 October**, and every quote/hold must be current.

## Timed narration and screen actions

| Time | Show on screen | Say this |
| --- | --- | --- |
| 0:00–0:20 | ServiceSetu Concierge and the completed ASI:One chat. | “Finding a local service is only the first step. Customers also need a clear price, an available appointment, and a way forward when a provider cancels. ServiceSetu coordinates that journey. I’ll walk through a completed demonstration inside one ASI:One conversation.” |
| 0:20–0:40 | Public Concierge Agentverse profile, ACP and Chat with Agent link; return to ASI:One. | “The Concierge is registered on Agentverse and implements the Agent Chat Protocol. It coordinates matching, verification, booking, payment and recovery specialists, together with independent provider agents. Customers interact with one Concierge.” |
| 0:40–1:10 | Original service request and provider comparison cards. | “The customer asks for AC service in Indiranagar, Bengaluru, at 10 AM, with a maximum budget of one thousand rupees. CoolCare offers a visit for 699 rupees and Breeze for 749. These are explicitly fictional demo providers. The expired mock credential excludes another provider.” |
| 1:10–1:40 | CoolCare review, exact scope, exclusions, appointment, price and approval. | “The customer reviews the exact quote: one AC service visit for 699 rupees. Parts and extra work require a new quote and approval. The appointment is held temporarily, and approval is tied to this specific quote. An expired hold cannot confirm.” |
| 1:40–2:00 | Actual original confirmation and the simulated payment label. | “After explicit approval, the mock payment flow records the booking. The chat clearly says simulated payment, with no gateway charge. No real money is collected and no real business appointment is being claimed.” |
| 2:00–2:35 | Actual provider cancellation notice and reversal, then replacement offers. For a new valid flow only, the operator uses the cancellation command below. | “Now the original provider can no longer attend. A provider cancellation event cancels that booking and reverses its simulated payment. Recovery searches for eligible alternatives using the original service, location, appointment and budget. The customer stays in this conversation.” |
| 2:35–3:10 | Breeze replacement review and its separate approval. | “Breeze is offered at 749 rupees, still under the original one thousand rupee budget and for the same appointment. ServiceSetu asks for fresh review and approval. Approval of CoolCare does not authorize a replacement automatically.” |
| 3:10–3:35 | Actual Breeze confirmation and full history. | “After fresh approval, the replacement is confirmed. The full history explains the original request, quote, approval, simulated payment, provider cancellation, reversal, replacement search, new approval and replacement confirmation.” |
| 3:35–4:00 | Separate TomTom results chat with discovered/not-onboarded labels and attribution. | “As a separate discovery tool, TomTom returned live business results in Mandi and Bengaluru. These are discovered businesses, not verified or onboarded ServiceSetu providers. A map listing does not create an appointment or prove availability.” |
| 4:00–4:15 | `servicesetu/places.py` and the Google Places test result; keep `.env` closed. | “An optional Google Places adapter is also implemented and tested locally with mocked responses. Live Google Places is disabled for this showcase. We are not claiming a successful Google API call or spending on it.” |
| 4:15–4:35 | Actual test summary and public repository run instructions. | “Local tests cover quote approval, ownership, expiry, duplicate payment handling and cancellation recovery. The local uAgent flow also passes. These local results are separate from the recorded ASI:One conversation.” |
| 4:35–4:50 | Public repo/profile and final confirmed replacement history. | “The current prototype uses fictional providers, a mock registry and simulated payments. The latest fresh retry hit intermittent message-delivery failures, so this video uses the completed recorded chat. A real pilot needs a consenting business and operator-confirmed services, prices and availability. Source and run instructions are public.” |

Keep narration conversational. Pause briefly on the two prices, both approvals, the cancellation notice and the final history. Do not show private configuration, tokens, customer addresses, terminal environment dumps or wallet secrets.

Taskrabbit is optional and need not appear in this short video. If mentioned, say: “Taskrabbit assistance is US-only in this connector and hands booking off to Taskrabbit. It does not confirm a ServiceSetu booking and is unavailable for our India request.”

## Customer prompts and actions for a new valid recording

Use one conversation addressed to `@servicesetu`. The runtime must use `PAYMENT_MODE=mock` and exactly one mailbox mesh. Check the appointment date rather than reusing an old card.

1. Customer sends: `AC service in Indiranagar Bengaluru tomorrow 10am under INR 1000`.
2. Show the real response. Choose **Review quote** on the current CoolCare card.
3. Choose **Skip for now** for the optional address. Do not use real customer details in a showcase.
4. Read the exact scope, INR 699 total, appointment and expiry. Choose **Approve test payment** while valid.
5. Wait for the actual rendered **Booking confirmed** response with **Simulated · no gateway charge**. A backend database row alone is not this scene.
6. The operator triggers cancellation for the actual assigned provider and booking ID:

   ```sh
   .venv/bin/python scripts/cancel_provider.py p1 BOOKING_ID
   ```

   Use `p1` only if it is the assigned provider. The command reads its private control token; do not display that token. This operator event represents the provider saying they cannot attend; do not invent a direct provider message that the UI did not send.

7. Wait for the real cancellation notice and reversal. If a notice is missed, send `status`, then `recover`.
8. Choose **Review quote** on the current Breeze alternative. Read the INR 749 quote and approve its fresh review separately.
9. Wait for the actual replacement confirmation, then send `show what happened`.
10. Show the complete history. Use `audit details` only when its identifiers and private references can be kept out of the recording.

If a quote expires, say “This hold expired safely; I’m requesting a fresh quote,” and send the original request again. Do not approve an old card or change expiry protections. If message delivery remains unstable, stop the fresh recording and use the honestly labelled prior walkthrough.

## Proper chat history outline from the completed demo

This is an outline of the observed prior conversation, not a newly generated agent transcript. Use the actual ASI:One messages/cards on screen rather than pasting this outline into a chat as evidence.

| Participant or event | What the actual completed demo showed |
| --- | --- |
| Customer request | AC service, Indiranagar Bengaluru, 24 October 2026 at 10 AM IST, maximum INR 1,000. The request was made on 23 October. |
| Concierge comparison | CoolCare AC INR 699; Breeze AC INR 749. Fictional/demo trust labels; Lapsed AC excluded for expired mock credential. |
| Customer selection | CoolCare quote review; optional service address skipped. |
| Concierge review | Exact visit scope, exclusions, INR 699, appointment and temporary hold. |
| Customer approval | Explicit approval of the exact CoolCare quote. |
| Concierge confirmation | Simulated payment and confirmed CoolCare demo booking. |
| Provider event | CoolCare cancellation, simulated reversal and reserved appointment release. |
| Concierge recovery | One eligible alternative within the original limits; fresh review required. |
| Customer replacement selection | Breeze quote at INR 749; address skipped. |
| Customer fresh approval | Explicit approval of the new Breeze quote. |
| Concierge replacement confirmation | Breeze confirmed with a separate simulated payment. |
| Customer history request | `show what happened`. |
| Concierge history | All 17 recorded events below, ending with Breeze confirmed. |

## Actual 17-event history shown in the prior chat

All times below are IST on **23 October 2026**. The appointment is **24 October 2026, 10 AM IST**. These are fictional demo records and test payments.

1. 12:10:49 PM — Service request received; maximum budget INR 1,000.
2. 12:10:49 PM — CoolCare quote received: INR 699.
3. 12:11:52 PM — CoolCare appointment temporarily held; approval required; hold expires 12:13:52 PM.
4. 12:11:52 PM — Service address skipped for now.
5. 12:12:13 PM — Customer approved the exact CoolCare quote.
6. 12:12:13 PM — Test payment started: INR 699.
7. 12:12:13 PM — CoolCare booking confirmed for the stated appointment.
8. 12:14:54 PM — CoolCare cancelled; test payment reversed.
9. 12:14:54 PM — Reserved appointment released.
10. 12:14:54 PM — Recovery request retained the appointment and maximum INR 1,000 budget.
11. 12:14:55 PM — Replacement search found one option; fresh review and approval required.
12. 12:14:55 PM — Breeze quote received: INR 749.
13. 12:15:45 PM — Breeze replacement appointment temporarily held; approval required; hold expires 12:17:45 PM.
14. 12:15:45 PM — Service address skipped for now.
15. 12:16:08 PM — Customer approved the exact Breeze quote.
16. 12:16:08 PM — Test payment started: INR 749.
17. 12:16:08 PM — Breeze replacement booking confirmed for the original appointment.

The prior finished chat and this outline do not prove a newly completed live run, a real provider agreement, an actual gateway charge or an on-chain transfer. Keep those distinctions in the narration and Devpost text.

## Submission checklist for the owner

- Copy the **public ASI:One Shared Chat URL** of the completed conversation and check it without the owner's session. A private `/chat/` URL does not satisfy this deliverable.
- Submit the public repository: https://github.com/arywk40-hue/ServiceSetu.
- Use the [Concierge Agentverse profile](https://agentverse.ai/agents/details/agent1q02ftm6eu39lw0vc5kh3uhr4gtkkeqd6jpcaxzn4gyyrc2ac0p9ecvl39sz/profile); other submitted agent profile URLs are in README.
- Record and upload the video yourself, then add its actual accessible URL to Devpost.
- Paste the brief description from [showcase readiness](showcase-readiness.md), with fictional provider and simulated payment qualifications intact.
- The owner cannot leave the laptop running. Fresh interaction therefore requires a verified persistent remote host; see [free hosting options and migration checklist](hosting.md). No host has been deployed. A recorded walkthrough does not prove the agent remains online, and a successful mailbox health request alone does not resolve the delivery issue.
