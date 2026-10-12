"""Documented ACP card payloads with usable text fallbacks."""
import json
from datetime import datetime, timezone
from uuid import uuid4


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
