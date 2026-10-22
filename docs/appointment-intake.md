# Appointment language

Appointment intake combines the existing ASI1 language interpretation with deterministic extraction of explicit dates and times. Recognized explicit values take precedence over model omissions. The offline path uses the same extractor, so a model timeout does not discard a supported date format.

Supported examples:

- `25 October 2026 at 2 pm`
- `October 25th, 2026 at 2 PM`
- `25 Oct 2026 2pm`
- `25 OCTOBER 2026 at 2:00 p.m.`
- `25/10/2026 14:00` (numeric dates use day/month/year)
- `2026-10-25 at 14:00`
- `tomorrow at 10 am`, `day after tomorrow at 2 pm`
- Timezone-qualified ISO timestamps, normalized to IST

AM/PM is case-insensitive and accepts common punctuation/spacing. Noon and midnight follow normal 12-hour clock rules. Times without an explicit ISO offset are interpreted as service-local IST. Month names without a year use the current IST calendar year; past appointments are still rejected by booking validation.

During intake, a time-only reply combines with the retained date, and a date-only reply combines with a retained exact time. Service, location and budget are retained. If only one appointment component is missing, the question names that component instead of asking for the whole appointment again.

Invalid calendar dates and clock values require clarification rather than normalization into a different day or time. Vague periods such as morning do not establish an exact appointment time and clear a previously remembered exact time when used as a date/time correction. A fresh quote and explicit booking approval remain necessary; recognizing a date never authorizes a payment.

This extractor is scoped to the documented formats. It is not a general parser for every language, ambiguous expression, spoken number or timezone name. Live mailbox delivery remains a separate concern from intake correctness.
