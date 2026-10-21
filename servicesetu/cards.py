"""Documented ACP card payloads with usable text fallbacks."""
import json
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo


def envelope(text, kind=None, payload=None, terminal=False):
    result = {"text": text}
    if kind:
        raw = json.dumps(payload)
        if len(raw.encode()) > 65536: raise ValueError("Card exceeds 64 KB")
        result["metadata"] = {"card_protocol_version":"1", "requires_card_interaction":"true",
                              "card_kind":kind, "card_payload":raw}
        if terminal: result["metadata"]["is_terminal"] = "true"
    return result


def chat_message(reply):
    from uagents_core.contrib.protocols.chat import ChatMessage, TextContent, MetadataContent
    content = [TextContent(type="text",text=reply["text"])]
    if reply.get("metadata"):
        content.append(MetadataContent(type="metadata",metadata=reply["metadata"]))
    return ChatMessage(timestamp=datetime.now(timezone.utc),msg_id=uuid4(),content=content)


def job_form(default_slot):
    return envelope("ServiceSetu demo uses fictional providers and test payments. I need the service, area, appointment and maximum budget. Demo slots are tomorrow at 10:00 or 14:00 IST.","form",{
        "title":"Find a local service · test data", "fields":[
            {"name":"service","kind":"select","label":"Service","required":True,"options":[{"value":"ac","label":"AC servicing"},{"value":"plumbing","label":"Plumbing"}]},
            {"name":"area","kind":"text","label":"Area (Indiranagar)","required":True},
            {"name":"slot","kind":"text","label":f"Appointment ISO date, e.g. {default_slot}","required":True},
            {"name":"budget_rupees","kind":"number","label":"Maximum budget (INR)","required":True}],
        "submit_cta":{"label":"Find providers","selection":{"action":"search"}}})


def shortlist(quotes, excluded, explanation="", recovery=False):
    lines = ["Recovery alternatives — your replacement needs approval." if recovery else "Provider-confirmed demo quotes:"]
    items = []
    for q in quotes:
        trust=q["trust"]
        label="Verified · mock registry" if trust["status"]=="verified" else "Provider-supplied · not independently verified"
        lines.append(f"{q['id']}: {q['name']}, INR {q['amount']/100:.2f}, {q['slot']}; {label}; source {trust['source']}; checked {trust['checked_at']}. Reply select {q['id']}.")
        items.append({"id":q["id"],"title":q["name"],"subtitle":q["slot"],"secondary_text":f"INR {q['amount']/100:.2f} · fixed visit price",
            "badges":[{"label":label,"variant":"success" if trust["status"]=="verified" else "warning"}],
            "primary_cta":{"label":"Review quote","selection":{"action":"select","quote_id":q["id"]}}})
    if explanation: lines.append(explanation)
    if excluded: lines.append("Why not: "+"; ".join(f"{p['name']}: {p['reason']}" for p in excluded))
    return envelope("\n".join(lines),"carousel",{"title":"Choose a replacement" if recovery else "Choose a provider", "subtitle":"Seeded demo · INR · slot freshness checked again at approval", "items":items})


def review(q,b,nonce):
    selection={"booking_id":b["id"],"quote_id":q["id"],"approval_token":nonce}
    rows=[("Provider",q["name"]),("Appointment",q["slot"]),("Fixed total",f"INR {q['amount']/100:.2f}"),
          ("Scope",q["scope"]),("Excluded",q["exclusions"]),("Documents",q["trust"]["status"]+" · "+q["trust"]["source"]),
          ("Checked",q["trust"]["checked_at"]),("Cancellation",q["cancellation"]),("Payment","Test mode only"),
          ("Quote version",str(q["version"])),("Hold expires",datetime.fromtimestamp(b["hold_until"],timezone.utc).isoformat())]
    text="Review before approving:\n"+"\n".join(f"{k}: {v}" for k,v in rows)
    text+=f"\nTo approve this exact test booking, click Approve or reply: approve {b['id']} {q['id']} {nonce}"
    return envelope(text,"review",{"title":"Approve this test booking", "summary_rows":[{"label":k,"value":v} for k,v in rows],
         "approve_cta":{"label":"Approve test payment","selection":dict(selection,action="approve"),"primary":True},
         "reject_cta":{"label":"Release slot","selection":dict(selection,action="reject")}})


def booking_status(b,q):
    text=f"Booking {b['id']}: {b['state']}. {q['name']}, {q['slot']}, INR {q['amount']/100:.2f}. Payment: {b['payment_state']} (test mode). Ask 'show what happened' for the audit timeline."
    return envelope(text,"detail",{"title":f"Booking {b['state']} · test mode", "summary_rows":[
        {"label":"Booking","value":b["id"]},{"label":"Provider","value":q["name"]},{"label":"Appointment","value":q["slot"]},{"label":"Payment","value":b["payment_state"]}],"ctas":[]},terminal=True)


def booking_history(events, booking=None):
    """Describe persisted facts without using model inference or changing them."""
    quotes = {e["entity"]: e["payload"]["quote"] for e in events
              if e["kind"] == "quote_created" and "quote" in e["payload"]}
    bookings = {}
    replacements = set()
    for event in events:
        payload = event["payload"]
        if isinstance(payload.get("quote"), str):
            bookings[event["entity"]] = payload["quote"]
        if event["kind"] == "slot_held" and payload.get("recovery_of"):
            replacements.add(event["entity"])

    def money(amount):
        return f"INR {amount / 100:.2f}"

    def appointment(slot):
        return datetime.fromisoformat(slot).astimezone(ZoneInfo("Asia/Kolkata")).strftime("%d %B %Y, %I:%M %p IST")

    def reversal(state):
        return {
            "refunded": "Test payment reversed.",
            "refund_required": "Refund required; not yet confirmed.",
            "pending": "Payment is pending; reconciliation is required.",
            "voided": "Test payment voided.",
            "declined": "Test payment declined.",
        }.get(state, "No completed payment reversal recorded.")

    lines = ["Booking history (test data)", "Fictional services and test payments only."]
    if booking:
        current_quote = quotes.get(booking.get("quote"), {})
        lines.extend(["", "### Current booking", f"**Status:** {booking['state'].replace('_', ' ').title()}"])
        if current_quote:
            lines.extend([f"**Provider:** {current_quote.get('name', 'Provider')}",
                          f"**Total:** {money(current_quote['amount'])}",
                          f"**Appointment:** {appointment(current_quote['slot'])}"])
        payment = booking.get("payment_state", "none")
        payment_label = {"paid": "Paid", "none": "No payment", "pending": "Pending",
                         "refunded": "Reversed", "refund_required": "Refund required; not yet confirmed",
                         "voided": "Voided", "declined": "Declined"}.get(payment, payment.replace("_", " "))
        lines.append(f"**Test payment:** {payment_label}")
    lines.extend(["", "### Full history", "Every recorded event is listed below. All times are IST."])
    previous_day = None
    for number, event in enumerate(events, start=1):
        kind, payload = event["kind"], event["payload"]
        quote = quotes.get(bookings.get(event["entity"]), {})
        name = quote.get("name", "the provider")
        text = None
        if kind == "booking_requested":
            job = payload.get("job", {})
            text = "Service request received."
            if job.get("slot") and job.get("budget") is not None:
                text += f" Appointment: {appointment(job['slot'])}. Maximum budget: {money(job['budget'])}."
        elif kind == "quote_created":
            offer = payload.get("quote", {})
            if offer.get("name") and offer.get("amount") is not None:
                text = f"Quote received from {offer['name']}: {money(offer['amount'])}."
        elif kind == "slot_held":
            label = "Replacement appointment" if event["entity"] in replacements else "Appointment"
            text = f"{label} temporarily held with {name}; approval required."
            if payload.get("hold_until"):
                deadline = datetime.fromtimestamp(payload["hold_until"], ZoneInfo("Asia/Kolkata"))
                text += " Hold expires: " + deadline.strftime("%d %b, %I:%M:%S %p IST") + "."
        elif kind == "customer_approved":
            text = f"You approved the exact quote from {name}."
        elif kind == "payment_started":
            text = f"Test payment started: {money(payload['amount'])}."
        elif kind == "booking_confirmed":
            label = "Replacement booking" if event["entity"] in replacements else "Booking"
            text = f"{label} confirmed with {name}: {money(payload['amount'])}."
            if quote.get("slot"):
                text += f" Appointment: {appointment(quote['slot'])}."
        elif kind in ("provider_cancelled", "customer_cancelled"):
            actor = "Provider cancelled" if kind == "provider_cancelled" else "You cancelled"
            text = f"{actor} the booking with {name}. {reversal(payload.get('payment_state'))}"
        elif kind == "recovery_proposed":
            count = len(payload.get("alternatives", []))
            options = "option" if count == 1 else "options"
            text = (f"Replacement search found {count} {options}; fresh review and approval required."
                    if count else "No eligible replacement found within the request limits.")
        elif kind == "hold_expired":
            text = "Temporary reservation expired; a fresh quote is required."
        elif kind == "payment_compensated":
            text = f"Booking could not be confirmed. {reversal(payload.get('payment_state'))}"
        elif kind == "stripe_test_refunded":
            text = "Test refund confirmed."
        elif kind == "action_rejected":
            text = "Request could not proceed: " + payload.get("reason", "Please review the booking status.")
        elif kind == "service_completed":
            text = f"Service with {name} marked completed."
        elif kind == "slot_released":
            text = "Reserved appointment released."
        elif kind == "stripe_test_checkout_created":
            text = "Stripe test checkout created; payment is not yet confirmed."
        if not text:
            text = kind.replace("_", " ").capitalize() + ". See 'audit details' for the recorded information."
        at = datetime.fromtimestamp(event["at"], ZoneInfo("Asia/Kolkata"))
        day = at.strftime("%d %B %Y")
        if day != previous_day:
            lines.extend(["", f"#### {day}"])
            previous_day = day
        clock = at.strftime("%I:%M:%S %p").lstrip("0")
        lines.extend(["", f"**{number}. {clock}**", text])
    if not events:
        lines.append("No booking events recorded yet.")
    lines.extend(["", "For all original record fields and references, send **audit details**."])
    return envelope("\n".join(lines))
