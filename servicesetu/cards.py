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
    return envelope("ServiceSetu uses test payments only. Provider records identify fictional demos or a manually entered pilot business. Tell me the service, area, preferred day and time, and maximum budget in normal language, or use this form. Availability will be checked for your requested date.","form",{
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
    if trust['status']=='manually_reviewed':
        return 'Manual review only: '+ '; '.join(trust.get('checked_items',[]))+'; no independent credential verification'
    return ("Checked against a fictional mock registry — demo only"
            if trust["status"]=="verified" else "Provider-supplied — not independently verified")


def shortlist(quotes, excluded, explanation="", recovery=False):
    lines = ["Recovery alternatives — your replacement needs approval." if recovery else "Provider-confirmed demo quotes:",
             "Provider records are labelled below. Test payments only."]
    if explanation and len(quotes)>1: lines.extend(["", explanation])
    items = []
    for number,q in enumerate(quotes,start=1):
        trust=q["trust"]
        label=document_label(trust)
        lines.extend(["",f"### {number}. {q['name']} — INR {q['amount']/100:.2f}",
                      '**Record:** '+('Real pilot business · entered with permission' if q.get('record_kind')=='pilot' else 'Fictional demo provider'),
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
    return envelope("\n".join(lines),"carousel",{"title":"Choose a replacement" if recovery else "Choose a provider", "subtitle":"Test payments · INR · availability checked again at approval", "items":items})


def address_choice(q,nonce):
    selection={'quote_id':q['id'],'address_token':nonce}
    return envelope('Would you like to add a service address? You can skip this and add it after booking. Your service area is '+location_label(q['location'])+'. No appointment has been reserved or paid yet.',
                    'detail',{'title':'Service address · optional','summary_rows':[{'label':'Service area','value':location_label(q['location'])}],
                    'ctas':[{'label':'Add address','selection':dict(selection,action='open_quote_address')},{'label':'Skip for now','selection':dict(selection,action='skip_address')}]})


def address_form(q,nonce):
    return envelope('Enter your house/flat, building and street. A landmark is optional. Use fictional details for the demo. You can leave this blank and continue without an address.',
                    'form',{'title':'Service address · optional','fields':[{'name':'address_line','kind':'text','label':'House/flat, building and street (optional)','required':False}],
                    'submit_cta':{'label':'Continue to review','selection':{'action':'set_address','quote_id':q['id'],'address_token':nonce}}})


def booking_address_form(b,nonce):
    return envelope('You can add the service address now or leave it for later. Your booking and payment will stay unchanged. The assigned provider can view the address for this booking. Use fictional details for this demo.',
                    'form',{'title':'Add service address · optional','fields':[{'name':'address_line','kind':'text','label':'House/flat, building and street (optional)','required':False}],
                    'submit_cta':{'label':'Save or continue','selection':{'action':'set_booking_address','booking_id':b['id'],'address_token':nonce}}})


def review(q,b,nonce,payment_mode='mock',fet_amount=None):
    selection={"booking_id":b["id"],"quote_id":q["id"],"approval_token":nonce}
    rows=[("Provider",q["name"]),("Appointment",appointment_label(q["slot"])),("Fixed total",f"INR {q['amount']/100:.2f}"),
          ("Scope",q["scope"]),("Excluded",q["exclusions"]),("Documents",document_label(q["trust"])),
          ("Checked",appointment_label(q["trust"]["checked_at"])),("Cancellation",q["cancellation"]),
          ("Quote version",str(q["version"])),("Hold expires",datetime.fromtimestamp(b["hold_until"],ZoneInfo("Asia/Kolkata")).strftime("%d %B %Y, %I:%M:%S %p IST"))]
    if payment_mode=='fet_testnet':
        if fet_amount is None:
            from .fet_payments import fet_amount as configured_fet_amount
            fet_amount=configured_fet_amount()[0]
        rows.append(("Payment after approval",f"{fet_amount} FET on Dorado testnet (atestfet)"))
        rows.append(("Price relationship","Separate test-token amount; no INR-to-FET conversion"))
    else:rows.append(("Payment","Test mode only"))
    if q.get('location'):rows.insert(1,('Location',location_label(q['location'])))
    rows.insert(2,('Service address',b['service_address']['address_line'] if b.get('service_address') else 'Not provided — you can add it after booking'))
    text="Review before approving:\n"+"\n".join(f"{k}: {v}" for k,v in rows)
    text+="\nChoose Approve FET test payment to request the displayed amount." if payment_mode=='fet_testnet' else "\nChoose Approve test payment to confirm, or Release slot to cancel this review."
    text+=f"\nText approval fallback: approve {b['id']} {q['id']} {nonce}"
    text+='\nRecord: '+('Real pilot business; operator must accept this booking before payment.' if q.get('record_kind')=='pilot' else 'Fictional demo provider.')
    if b.get('service_address'):text+="\nTo correct the address before approval, send 'change address'."
    return envelope(text,"review",{"title":"Approve this test booking", "summary_rows":[{"label":k,"value":v} for k,v in rows],
         "approve_cta":{"label":"Approve FET test payment" if payment_mode=='fet_testnet' else "Approve test payment","selection":dict(selection,action="approve"),"primary":True},
         "reject_cta":{"label":"Release slot","selection":dict(selection,action="reject")}})


def booking_status(b,q):
    mode='Razorpay TEST transaction' if b.get('payment_mode')=='razorpay_test' else 'Stripe TEST transaction' if b.get('payment_mode')=='stripe_test' else 'Dorado FET testnet · native test tokens' if b.get('payment_mode')=='fet_testnet' else 'Simulated payment · no gateway charge' if b.get('payment_mode')=='mock' else 'No payment started'
    text=(f"Booking status: {b['state']}.\n\n**Provider:** {q['name']}\n"
          f"**Appointment:** {appointment_label(q['slot'])}\n**Total:** INR {q['amount']/100:.2f}\n"
          f"**Test payment:** {b['payment_state'].replace('_',' ')}\n\n"
          f"**Payment rail:** {mode}\n\n"
          "Send show what happened for history, report a problem for operator review, or status to refresh.")
    if b['state']=='confirmed':text+='\nSend message provider: YOUR MESSAGE to coordinate the visit, or complete service to confirm the work is finished.'
    if b['state']=='cancelled':text+='\nSend recover to review eligible replacements within the original constraints. Fresh approval is required.'
    if b['state']=='held' and b['approved']:text+='\nYour exact quote approval is saved. Send resume checkout to retry the same payment while the hold remains active.'
    if b.get('service_address'):text+='\n**Service address:** '+b['service_address']['address_line']+', '+location_label(b['service_address'])
    ctas=[{'label':'Booking history','selection':{'action':'booking_history','booking_id':b['id']}}]
    if b['state'] in ('confirmed','completed','cancelled'):ctas.append({'label':'Report a problem','selection':{'action':'problem_form','booking_id':b['id']}})
    if b['state']=='confirmed':
        ctas.extend([{'label':'Message provider','selection':{'action':'compose_message','booking_id':b['id']}},{'label':'View messages','selection':{'action':'open_messages','booking_id':b['id']}},{'label':'Confirm completion','selection':{'action':'completion_review','booking_id':b['id']}}])
        if not b.get('service_address'):ctas.insert(0,{'label':'Add address','selection':{'action':'add_address','booking_id':b['id']}})
    if b['state']=='cancelled':ctas.append({'label':'Find replacements','selection':{'action':'recover_booking','booking_id':b['id']}})
    if b['state']=='held' and b['approved']:ctas.append({'label':'Resume test checkout','selection':{'action':'resume_checkout','booking_id':b['id']}})
    if b.get('payment_mode')=='razorpay_test' and b['payment_state'] in ('pending','refund_required'):ctas.append({'label':'Check test payment','selection':{'action':'check_payment','booking_id':b['id']}})
    return dict(envelope(text,"detail",{"title":f"Booking {b['state']} · test mode", "summary_rows":[
        {"label":"Provider","value":q["name"]},{"label":"Appointment","value":appointment_label(q["slot"])},{"label":"Test payment","value":b["payment_state"].replace('_',' ')},{'label':'Payment rail','value':mode}],"ctas":ctas},terminal=True),notice_booking=b['id'],notice_kinds=(['booking_confirmed'] if b['state'] in ('confirmed','completed') else ['provider_cancelled','payment_compensated'] if b['state']=='cancelled' else [])+(['stripe_test_refunded','razorpay_test_refunded'] if b['payment_state']=='refunded' else []))


def razorpay_checkout(result):
    b=result['booking'];url=result['razorpay']['url']
    return envelope('Your exact quote approval is saved. Open [Razorpay TEST checkout]('+url+') to complete a test payment on Razorpay’s hosted page, then return to this ASI:One conversation and send check payment. This is a test gateway transaction, not a simulated payment. A late captured payment cannot confirm an expired hold and requires a test refund. Booking confirmation appears only after server verification.',
                    'detail',{'title':'Razorpay TEST checkout','summary_rows':[{'label':'Checkout','value':'Hosted Razorpay page; return here after payment'},{'label':'Payment status','value':'Pending server verification'}],
                              'ctas':[{'label':'Check test payment','selection':{'action':'check_payment','booking_id':b['id']}}]})


def message_notice(bid):
    return envelope('Your provider has replied. Open the conversation to read their message.', 'detail',
                    {'title':'New provider message','summary_rows':[], 'ctas':[{'label':'View conversation','selection':{'action':'open_messages','booking_id':bid}}]})


def message_saved(bid):
    return envelope('Message saved for your assigned provider. It may not have been read yet. Messaging is optional and does not change your booking or payment.', 'detail',
                    {'title':'Message saved','summary_rows':[], 'ctas':[{'label':'View conversation','selection':{'action':'open_messages','booking_id':bid}}]})


def message_thread(bid,result,can_reply=True):
    lines=['Booking messages · test data','']
    for item in result['messages']:
        label='You' if item['side']=='customer' else 'Provider'
        at=datetime.fromtimestamp(item['at'],ZoneInfo('Asia/Kolkata')).strftime('%d %b, %I:%M %p IST')
        lines.extend([label+' · '+at,item['text'],''])
    if not result['messages']:lines.append('No messages in this part of the conversation yet.')
    lines.append('Messaging is optional. Messages do not change booking terms.')
    ctas=[{'label':'Reply to provider','selection':{'action':'compose_message','booking_id':bid}}] if can_reply else []
    if result['has_more']:ctas.append({'label':'More messages','selection':{'action':'open_messages','booking_id':bid,'after':result['next_after']}})
    ctas.append({'label':'Refresh conversation','selection':{'action':'open_messages','booking_id':bid}})
    return envelope('\n'.join(lines),'detail',{'title':'Booking conversation','summary_rows':[],'ctas':ctas})


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

    lines = ["Booking history (test payments)", "Provider records identify demo or pilot origin; all payments are test only."]
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
        lines.append('**Payment rail:** '+('Razorpay TEST' if booking.get('payment_mode')=='razorpay_test' else 'Stripe TEST' if booking.get('payment_mode')=='stripe_test' else 'Dorado FET testnet transfer · no INR conversion' if booking.get('payment_mode')=='fet_testnet' else 'Simulated · no gateway charge' if booking.get('payment_mode')=='mock' else 'No payment started'))
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
        elif kind == 'service_address_deferred':
            text='Service address skipped for now; it can be provided after booking.'
        elif kind == 'service_address_recorded':
            text='Service address recorded for review: '+payload['address']['address_line']+', '+location_label(payload['address'])+'.'
        elif kind == 'booking_message_saved':
            text=('Customer' if payload['side']=='customer' else 'Provider')+' message saved to the booking inbox. Message text is kept out of the audit record.'
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
        elif kind == 'fet_testnet_invoice_created':
            text=f"Dorado testnet invoice requested: {payload.get('token_amount')} FET ({payload.get('denom')}); no INR conversion."
            if payload.get('deadline'):
                deadline=datetime.fromtimestamp(payload['deadline'],ZoneInfo('Asia/Kolkata'))
                text+=' Payment deadline: '+deadline.strftime('%d %b, %I:%M:%S %p IST')+'.'
        elif kind == "booking_confirmed":
            label = "Replacement booking" if event["entity"] in replacements else "Booking"
            text = f"{label} confirmed with {name}: {money(payload['amount'])}."
            if quote.get("slot"):
                text += f" Appointment: {appointment(quote['slot'])}."
            if payload.get('payment_network')=='dorado-1' and payload.get('payment_transaction'):
                text+=f" Dorado testnet transfer: {payload['payment_transaction']}."
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
        elif kind in ("stripe_test_refunded","razorpay_test_refunded"):
            text = "Test refund confirmed."
        elif kind == 'fet_testnet_refunded':
            text='Dorado testnet refund transfer verified: '+str(payload.get('refund','unknown'))+'.'
        elif kind == "action_rejected":
            text = "Request could not proceed: " + payload.get("reason", "Please review the booking status.")
        elif kind == "service_completed":
            text = f"Service with {name} marked completed."
        elif kind=='problem_reported':text='Problem report recorded for operator review. No refund or resolution has been promised.'
        elif kind=='problem_acknowledged':text='Operator acknowledged the problem report; this does not mean it is resolved.'
        elif kind=='pilot_booking_accepted':text='Operator recorded provider acceptance of this exact booking and quote.'
        elif kind == "slot_released":
            text = "Reserved appointment released."
        elif kind == "stripe_test_checkout_created":
            text = "Stripe test checkout created; payment is not yet confirmed."
        elif kind=='razorpay_test_checkout_created':text='Razorpay test checkout link created; payment is not yet confirmed.'
        elif kind=='razorpay_test_capture_verified':text='Razorpay test capture verified server-side against the booking, order and approved total.'
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
