"""Documented ACP card payloads with usable text fallbacks."""
import json
import re
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo
from .catalogue import SERVICES,CATEGORIES,catalogue_text,provider_services
from .coverage import location_label


def service_menu(providers,category=None):
    items=[]
    if category is None:
        labels={"cleaning":"Cleaning","appliances":"Appliance care","repairs":"Home repairs","assembly":"Furniture assembly"}
        for group,keys in CATEGORIES.items():
            available=[key for key in keys if any(key in provider_services(p) for p in providers)]
            if not available:continue
            items.append({"id":group,"title":labels[group],"subtitle":", ".join(SERVICES[key]["label"] for key in available),
                          "primary_cta":{"label":"Browse packages","selection":{"action":"choose_category","category":group}}})
    else:
        for key in CATEGORIES[category]:
            definition=SERVICES[key]
            count=sum(key in provider_services(p) for p in providers)
            if not count: continue
            items.append({"id":key,"title":definition.get("package",definition["label"]),
                          "subtitle":definition["scope"],
                          "primary_cta":{"label":"Choose service","selection":{"action":"choose_service","service":key}}})
    text=catalogue_text(providers,category)
    text+="\n\nBrowse a group: 'show cleaning services', 'show appliance services', 'show repair services' or 'show assembly services'."
    if not items: return envelope(text)
    return envelope(text,"carousel",{"title":"Choose a service group" if category is None else "Choose a service package","items":items})


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
    return envelope("ServiceSetu demo uses fictional providers and test payments. Tell me the service, area, preferred day and time, and maximum budget in normal language, or use this form. Availability will be checked for your requested date.","form",{
        "title":"Find a local service · test data", "fields":[
            {"name":"service","kind":"select","label":"Service package","required":True,"options":[{"value":key,"label":item.get("package",item["label"])} for key,item in SERVICES.items() if item["bookable"]]},
            {"name":"city","kind":"text","label":"City in India","required":True},
            {"name":"area","kind":"text","label":"Locality or neighbourhood","required":True},
            {"name":"pincode","kind":"text","label":"PIN code (optional)","required":False},
            {"name":"slot","kind":"text","label":"Preferred day and time (e.g. tomorrow at 10 AM)","required":True},
            {"name":"budget_rupees","kind":"number","label":"Maximum budget (INR)","required":True}],
        "submit_cta":{"label":"Find providers","selection":{"action":"search"}}})


def appointment_label(slot):
    return datetime.fromisoformat(slot).astimezone(ZoneInfo("Asia/Kolkata")).strftime("%d %B %Y, %I:%M %p IST")


def clarification(partial):
    missing = []
    if not partial.get("service"):
        missing.append("which service you need (send 'show services' to browse the packages)")
    if not partial.get("area") or not partial.get("city"):
        missing.append("your area and city" if not partial.get("area") and not partial.get("city")
                       else "your area" if not partial.get("area") else "your city")
    if not partial.get("slot"):
        if partial.get('requested_day'):
            missing.append('your preferred time; the appointment day is already retained as '+str(partial['requested_day']))
        elif partial.get('requested_time'):
            missing.append('your preferred day or date; the time is already retained as '+str(partial['requested_time'])+' IST')
        else:missing.append("your preferred day and time, such as 'tomorrow at 10 AM'")
    if partial.get("budget") is None:
        missing.append("your maximum budget in INR")
    return envelope("I need a few more details:\n" + "\n".join("- " + field for field in missing)
                    + "\nYou can reply in normal language. We accept locations across India and check each provider's declared coverage.")


def availability_choices(job, options, excluded, token):
    requested = appointment_label(job["slot"])
    lines = [f"No eligible provider is available for {requested} within INR {job['budget']/100:.2f}."]
    if not options:
        lines.append("No other eligible appointments are currently available within your budget. You can make a new request with a different time or budget.")
        if excluded:
            lines.append("Why not: " + "; ".join(f"{p['name']}: {p['reason']}" for p in excluded))
        return envelope("\n".join(lines))
    lines.extend(["These other appointments fit your service, location and budget:",
                  "Choose a card or reply 'option 1', 'option 2', and so on. Nothing has been reserved or paid."])
    items = []
    for index, option in enumerate(options, start=1):
        label = appointment_label(option["slot"])
        price = f"From INR {option['from_amount']/100:.2f}"
        lines.append(f"{index}. {label} — {price}")
        items.append({"id":str(index), "title":label, "secondary_text":price,
                      "primary_cta":{"label":"See providers", "selection":{"action":"choose_time", "option":index,"availability_token":token}}})
    lines.append("Availability will be checked again after you choose. A provider quote still needs review and approval.")
    return envelope("\n".join(lines), "carousel", {"title":"Choose another appointment", "items":items})


def acknowledge(reply, user_text):
    text=user_text.lower().replace("’", "'")
    if re.search(r"\b(?:i'm|i am|i feel|this is|it's)\s+(?:(?:really|so|very)\s+)?(?:frustrat\w*|stress\w*|worried|worrying|overwhelm\w*)\b",text):
        return dict(reply,text="That sounds difficult. I can help you check service options.\n\n"+reply["text"])
    return reply


def document_label(trust):
    return ("Checked against a fictional mock registry — demo only"
            if trust["status"]=="verified" else "Provider-supplied — not independently verified")


def shortlist(quotes, excluded, explanation="", recovery=False):
    lines = ["Recovery alternatives — your replacement needs approval." if recovery else "Provider-confirmed demo quotes:",
             "Fictional providers and test payments only."]
    if explanation and len(quotes)>1: lines.extend(["", explanation])
    items = []
    for number,q in enumerate(quotes,start=1):
        trust=q["trust"]
        label=document_label(trust)
        lines.extend(["",f"### {number}. {q['name']} — INR {q['amount']/100:.2f}",
                      f"**Appointment:** {appointment_label(q['slot'])}",f"**Documents:** {label}",
                      f"**Includes:** {q['scope']}",f"**Not included:** {q['exclusions']}"])
        if q.get('location'):lines.append('**Location:** '+location_label(q['location']))
        items.append({"id":q["id"],"title":q["name"],"subtitle":appointment_label(q["slot"]),"secondary_text":f"INR {q['amount']/100:.2f} · fixed visit price",
            "badges":[{"label":label,"variant":"success" if trust["status"]=="verified" else "warning"}],
            "primary_cta":{"label":"Review quote","selection":{"action":"select","quote_id":q["id"]}}})
    if excluded:
        lines.extend(["", "### Other providers"])
        lines.extend(f"- **{p['name']}:** {p['reason']}" for p in excluded)
    lines.extend(["", "**Next:** Choose a provider card or reply 'option 1', 'option 2', and so on.",
                  "This opens the quote review. Payment requires your separate approval."])
    return envelope("\n".join(lines),"carousel",{"title":"Choose a replacement" if recovery else "Choose a provider", "subtitle":"Seeded demo · INR · slot freshness checked again at approval", "items":items})


def address_form(q,nonce):
    return envelope('Where should the provider visit?\n\n**Service area:** '+location_label(q['location'])+
                    '\nEnter your house/flat number, building and street. A landmark is optional. Use a fictional address for this demo.\n\n'
                    "You can type the address directly. Nothing has been reserved or paid. You will review the address and price before approving. Send 'cancel address' to go back.",
                    'form',{'title':'Service address · test data','fields':[{'name':'address_line','kind':'text','label':'House/flat, building and street','required':True}],
                    'submit_cta':{'label':'Review booking','selection':{'action':'set_address','quote_id':q['id'],'address_token':nonce}}})


def review(q,b,nonce):
    selection={"booking_id":b["id"],"quote_id":q["id"],"approval_token":nonce}
    rows=[("Provider",q["name"]),("Appointment",appointment_label(q["slot"])),("Fixed total",f"INR {q['amount']/100:.2f}"),
          ("Scope",q["scope"]),("Excluded",q["exclusions"]),("Documents",document_label(q["trust"])),
          ("Checked",appointment_label(q["trust"]["checked_at"])),("Cancellation",q["cancellation"]),("Payment","Test mode only"),
          ("Quote version",str(q["version"])),("Hold expires",datetime.fromtimestamp(b["hold_until"],ZoneInfo("Asia/Kolkata")).strftime("%d %B %Y, %I:%M:%S %p IST"))]
    if q.get('location'):rows.insert(1,('Location',location_label(q['location'])))
    if b.get('service_address'):rows.insert(2,('Service address',b['service_address']['address_line']))
    text="Review before approving:\n"+"\n".join(f"{k}: {v}" for k,v in rows)
    text+=f"\nTo approve this exact test booking, click Approve or reply: approve {b['id']} {q['id']} {nonce}"
    if b.get('service_address'):text+="\nTo correct the address before approval, send 'change address'."
    return envelope(text,"review",{"title":"Approve this test booking", "summary_rows":[{"label":k,"value":v} for k,v in rows],
         "approve_cta":{"label":"Approve test payment","selection":dict(selection,action="approve"),"primary":True},
         "reject_cta":{"label":"Release slot","selection":dict(selection,action="reject")}})


def booking_status(b,q):
    text=(f"Booking status: {b['state']}.\n\n**Provider:** {q['name']}\n"
          f"**Appointment:** {appointment_label(q['slot'])}\n**Total:** INR {q['amount']/100:.2f}\n"
          f"**Test payment:** {b['payment_state'].replace('_',' ')}\n\n"
          f"Booking reference: {b['id']}\nSend 'show what happened' for the history.")
    if b.get('service_address'):text+='\n**Service address:** '+b['service_address']['address_line']+', '+location_label(b['service_address'])
    return envelope(text,"detail",{"title":f"Booking {b['state']} · test mode", "summary_rows":[
        {"label":"Booking","value":b["id"]},{"label":"Provider","value":q["name"]},{"label":"Appointment","value":appointment_label(q["slot"])},{"label":"Test payment","value":b["payment_state"].replace('_',' ')}],"ctas":[]},terminal=True)


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
        elif kind == 'service_address_recorded':
            text='Service address recorded for review: '+payload['address']['address_line']+', '+location_label(payload['address'])+'.'
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
