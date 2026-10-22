"""One customer conversation, isolated by sender AND ACP session."""
import json
import re
import secrets
from .core import Rejected
from . import cards
from .reasoning import Reasoner,rupees
from .locations import clean_context,resolve,location_only
from .catalogue import SERVICES,catalogue_text,unavailable_message,package_from_text


def strip_recipient(text, address=None):
    """Remove only this Concierge's routing mention, never arbitrary prose."""
    text=text.strip()
    match=re.match(r"@([^\s]+)\s+",text)
    if match and match.group(1) in {"servicesetu",address}:
        return text[match.end():].strip()
    return text


def selection(text):
    text=strip_recipient(text)
    try:
        obj=json.loads(text)
        if isinstance(obj,dict):
            if "action" in obj: return obj
            if isinstance(obj.get("selection"),dict): return obj["selection"]
            return obj
    except (ValueError,TypeError): pass
    # Consequential prose is narrow and requires all review-card identifiers.
    # Reject negations, conditionals and hypothetical instructions.
    low=text.lower().strip()
    if re.search(r"\b(not|don't|do not|never|if|unless|would|could|should|maybe)\b",low): return {}
    q=re.search(r"\bq_[a-f0-9]{16}\b",text)
    b=re.search(r"\bb_[a-f0-9]{16}\b",text)
    token=re.search(r"\bat_[a-f0-9]{32}\b",text)
    if q and b and token and (low.startswith("approve ") or re.search(r"\buser (?:has )?(?:approved|confirmed)\b",low)):
        return {"action":"approve","quote_id":q.group(),"booking_id":b.group(),"approval_token":token.group()}
    if q and b and token and (low.startswith("reject ") or re.search(r"\buser (?:has )?rejected\b",low)):
        return {"action":"reject","quote_id":q.group(),"booking_id":b.group(),"approval_token":token.group()}
    if q and (low.startswith("select ") or re.search(r"\buser (?:picked|selected)\b",low)):
        return {"action":"select","quote_id":q.group()}
    if low=="reject": return {"action":"reject"}
    if re.search(r"\bsearch\b",low) and "budget_rupees" in low:
        service=re.search(r"\bservice\s*(?:(?:is|=|:)\s*)?[\"']?(ac|plumbing|cleaning|electrical)\b",low)
        area=re.search(r"\barea\s*(?:(?:is|=|:)\s*)?[\"']?(indiranagar)\b",low)
        slot=re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:[+-]\d{2}:\d{2}|Z)",text)
        budget=re.search(r"\bbudget_rupees\s*[\"']?\s*(?:(?:is|=|:)\s*)?(\d+(?:\.\d{1,2})?)",low)
        if service and area and slot and budget:
            return {"action":"search","service":service.group(1),"area":area.group(1),"slot":slot.group(),"budget_rupees":budget.group(1)}
    return {}


class Conversation:
    def __init__(self,store,reasoner=None):
        self.store=store
        self.reasoner=reasoner or Reasoner()

    def location_check(self, owner, state, partial, text=""):
        partial, proposal, unsupported = resolve(partial,text)
        state["partial_job"]=partial
        state.pop("availability_options",None)
        state.pop("availability_token",None)
        state.pop("pending_location",None)
        if proposal: state["pending_location"]=proposal
        self.store.save_session(owner,state)
        if proposal:
            labels={"area":"Indiranagar","city":"Bengaluru"}
            place=", ".join(labels[field] for field in ("area","city") if field in proposal)
            return partial,cards.envelope(f"Did you mean {place}? Reply yes to confirm the location, or tell me the correct area and city. This confirms only your location, not a booking or payment.")
        if unsupported:
            return partial,cards.envelope("This demo serves Indiranagar in Bengaluru only. Please tell me your area and city again. I have kept the other request details; no new booking was made.")
        return partial,None

    async def quotes(self,bus,owner,job,recovery_of=None):
        job=self.store.normalize_job(job)
        state=self.store.session(owner)
        if state.get("intent"):
            prior=self.store.booking(state["intent"],owner)
            if prior["state"]=="requested":
                await bus.call("payment","cancel",owner,booking=prior["id"])
        intent=await bus.call("booking","request",owner,job=job)
        result=await bus.call("recovery" if recovery_of else "matching","alternatives" if recovery_of else "match",owner,
                              job=job,**({"booking":recovery_of} if recovery_of else {}))
        quotes=[]
        excluded=result["excluded"]
        for pid in result["providers"]:
            try:
                trust=await bus.call("verification","check",owner,provider=pid,slot=job["slot"])
                if not trust["eligible"]: continue
                q=await bus.call("provider:"+pid,"quote",owner,slot=job["slot"])
                # Validate worker evidence against deterministic requirements.
                canonical=self.store.get_quote(q["id"],owner)
                if canonical["provider"]!=pid or canonical["slot"]!=job["slot"] or canonical["amount"]>job["budget"]:
                    raise Rejected("Provider quote violates request limits")
                quotes.append(canonical)
            except (Rejected,TimeoutError):
                excluded.append({"name":self.store.provider(pid)["name"],"reason":"Provider timed out or could not confirm a fresh quote"})
        quotes.sort(key=lambda q:(q["trust"]["status"]!="verified",q["amount"]))
        state=self.store.session(owner)
        state.update(job=job,quotes=[q["id"] for q in quotes],recovery_of=recovery_of,intent=intent["id"])
        state.pop("availability_options",None)
        state.pop("availability_token",None)
        state.pop("approval_token",None)
        state.pop("partial_job",None)
        self.store.save_session(owner,state)
        if not quotes:
            if recovery_of:
                return cards.envelope("No eligible replacement fits the original appointment and budget. Nothing has been booked. To change the appointment or budget, start a new service request.")
            available=await bus.call("matching","availability",owner,job=job)
            state["availability_options"]=available["options"]
            state["availability_token"]="av_"+secrets.token_hex(16)
            self.store.save_session(owner,state)
            return cards.availability_choices(job,available["options"],excluded,state["availability_token"])
        explanation=await self.reasoner.explain(quotes,excluded)
        return cards.shortlist(quotes,excluded,explanation,recovery=bool(recovery_of))

    async def handle(self,owner,text,bus):
        text=strip_recipient(text)
        state=self.store.session(owner)
        picked=selection(text)
        action=picked.get("action")
        low=text.lower()
        try:
            if low.strip(" ?.! ") in ("services","what services do you offer","available services","show services"):
                return cards.envelope(catalogue_text(self.store.providers()))
            option_match=re.fullmatch(r"(?:option\s+)?([1-4])",low)
            if not action and option_match and state.get("availability_options"):
                picked={"action":"choose_time","option":int(option_match.group(1)),"availability_token":state.get("availability_token")}
                action="choose_time"
            elif not action and option_match and state.get("quotes"):
                index=int(option_match.group(1))-1
                if index>=len(state["quotes"]): raise Rejected("Choose a provider from the current shortlist")
                picked={"action":"select","quote_id":state["quotes"][index]}
                action="select"
            if action=="choose_time":
                index=picked.get("option")
                options=state.get("availability_options",[])
                if not state.get("availability_token") or picked.get("availability_token")!=state["availability_token"]:
                    raise Rejected("This appointment card is no longer current; use the latest options")
                if not isinstance(index,int) or isinstance(index,bool) or not 1<=index<=len(options):
                    raise Rejected("Choose an appointment from the current options")
                job=dict(state["job"],slot=options[index-1]["slot"])
                return await self.quotes(bus,owner,job)
            if action=="search":
                job={"service":str(picked.get("service","")).strip().casefold(),"area":picked.get("area",""),"city":picked.get("city","bengaluru"),
                     "slot":picked.get("slot"),"budget":rupees(picked.get("budget_rupees"))}
                # The form labels explicitly name each bounded service package.
                package=SERVICES.get(job["service"],{}).get("package")
                if package: job["package"]=package
                if isinstance(job["slot"],str) and not re.match(r"^\d{4}-\d{2}-\d{2}T",job["slot"]):
                    parsed=await self.reasoner.parse(job["slot"],self.store.clock())
                    job["slot"]=parsed.get("slot")
                    if parsed.get("requested_day"): job["requested_day"]=parsed["requested_day"]
                job,location_reply=self.location_check(owner,state,job)
                if location_reply: return location_reply
                if not job.get("slot"): return cards.clarification(job)
                job=self.store.normalize_job(job)
                if state.get("booking") and self.store.booking(state["booking"],owner)["state"]=="held":
                    await bus.call("payment","cancel",owner,booking=state["booking"])
                return await self.quotes(bus,owner,job)
            if action=="select":
                qid=picked.get("quote_id")
                if qid not in state.get("quotes",[]): raise Rejected("Select a quote from this conversation's current shortlist")
                if state.get("booking"):
                    old=self.store.booking(state["booking"],owner)
                    if old["state"]=="held" and old["quote"]!=qid:
                        await bus.call("payment","cancel",owner,booking=old["id"])
                q=self.store.get_quote(qid,owner)
                request_id=state.get("intent")
                if request_id and self.store.booking(request_id,owner)["state"]!="requested": request_id=None
                b=await bus.call("booking","hold",owner,quote=qid,recovery_of=state.get("recovery_of"),request_id=request_id)
                nonce="at_"+secrets.token_hex(16)
                state.update(booking=b["id"],quote=qid,approval_token=nonce)
                self.store.save_session(owner,state)
                return cards.review(q,b,nonce)
            if action=="approve":
                required={"booking_id":state.get("booking"),"quote_id":state.get("quote"),"approval_token":state.get("approval_token")}
                if not all(required.values()) or any(picked.get(k)!=v for k,v in required.items()):
                    raise Rejected("Approval must match the current review card, quote and token")
                bid=state["booking"]
                b=self.store.booking(bid,owner)
                if b["state"]=="confirmed": return cards.booking_status(b,self.store.get_quote(state["quote"],owner))
                await bus.call("booking","approve",owner,booking=bid,quote=state["quote"])
                result=await bus.call("payment","start",owner,booking=bid)
                if result.get("stripe"):
                    return dict(cards.envelope("Approved. Complete the embedded Stripe TEST checkout. The slot hold lasts two minutes; a late successful payment is refunded rather than confirming an expired slot."),payment=result)
                return cards.booking_status(result["booking"],self.store.get_quote(state["quote"],owner))
            if action=="reject" or low=="cancel booking":
                if not state.get("booking"): raise Rejected("No held or confirmed booking to cancel")
                if action=="reject" and self.store.booking(state["booking"],owner)["state"]!="held":
                    raise Rejected("Reject only releases the current review hold; use 'cancel booking' to cancel a confirmed booking")
                if action=="reject" and picked.get("booking_id"):
                    required={"booking_id":state.get("booking"),"quote_id":state.get("quote"),"approval_token":state.get("approval_token")}
                    if any(picked.get(k)!=v for k,v in required.items()):
                        raise Rejected("Reject must match the current review card; an old card cannot cancel another booking")
                b=await bus.call("payment","cancel",owner,booking=state["booking"])
                state.pop("approval_token",None)
                self.store.save_session(owner,state)
                return cards.booking_status(b,self.store.get_quote(b["quote"],owner))
            if low in ("show what happened","audit","timeline","audit details"):
                if not state.get("booking"): raise Rejected("No booking yet; choose a provider first")
                result=await bus.call("booking","timeline",owner,booking=state["booking"])
                if low == "audit details":
                    return cards.envelope("Immutable timeline (test data):\n"+"\n".join(f"#{e['seq']} {e['kind']} · {json.dumps(e['payload'],sort_keys=True)}" for e in result["events"]))
                return cards.booking_history(result["events"], self.store.booking(state["booking"],owner))
            if low in ("status","booking status"):
                if not state.get("booking"): raise Rejected("No booking yet")
                b=await bus.call("booking","status",owner,booking=state["booking"])
                return cards.booking_status(b,self.store.get_quote(b["quote"],owner))
            if low in ("recover","find a replacement","provider cancelled"):
                if not state.get("booking"): raise Rejected("No cancelled booking to recover")
                return await self.quotes(bus,owner,state["job"],state["booking"])
            if low=="complete service":
                if not state.get("booking"): raise Rejected("No confirmed booking yet")
                b=await bus.call("booking","complete",owner,booking=state["booking"])
                return cards.booking_status(b,self.store.get_quote(b["quote"],owner))
            if re.search(r"\b(refund|payout|override|waive|reject provider)\b",low):
                raise Rejected("Discretionary refunds, payout changes and verification overrides require human review")
            if low in ("help","hi","hello","what can you do",""):
                return cards.job_form(self.store.providers()[0]["slots"][0])
            # Parsing is permitted only for intake. Model output cannot authorize payment.
            partial=clean_context(state.get("partial_job",{}))
            confirmation=re.sub(r"[,.!]+"," ",low).strip()
            confirmation=" ".join(confirmation.split())
            if state.get("pending_location") and confirmation in ("yes","yes please","correct","that's right","yes that's right","yes correct","yes that's correct"):
                job=dict(state["pending_location"])
            elif state.get("pending_location") and confirmation in ("no","no thanks","incorrect"):
                state.pop("pending_location",None)
                state["partial_job"]=partial
                self.store.save_session(owner,state)
                return cards.envelope("Please tell me the correct area and city. This demo currently serves Indiranagar in Bengaluru only. Your other request details are retained.")
            else:
                job=await self.reasoner.parse(text,self.store.clock(),partial)
                if location_only(text):
                    job={field:job.get(field) for field in ("city","area")}
            if job.get("requested_day") and not job.get("slot") and partial.get("slot") and partial["slot"][:10]!=job["requested_day"]:
                partial.pop("slot",None)
            partial.update({k:v for k,v in job.items() if v is not None})
            if isinstance(partial.get("service"),str): partial["service"]=partial["service"].strip().casefold()
            if partial.get("service") and (not isinstance(partial["service"],str) or not SERVICES.get(partial["service"],{}).get("bookable")):
                raise Rejected(unavailable_message(partial["service"]))
            definition=SERVICES.get(partial.get("service"),{})
            package=definition.get("package")
            if package:
                # Only explicit customer package wording is sufficient, never a model guess.
                chosen=package_from_text(partial["service"],text)
                previous=state.get("partial_job",{})
                partial["package"]=chosen or (previous.get("package") if previous.get("service")==partial["service"] else None)
                if partial["package"]!=package:
                    state["partial_job"]=partial
                    self.store.save_session(owner,state)
                    return cards.envelope(f"The available demo package is **{package}**.\n\nIncludes: {definition['scope']}.\n\nExcluded: {definition['exclusions']}.\n\nIf this fits your request, reply '{package}'. This chooses the package only; provider selection and payment approval come later.")
            partial,location_reply=self.location_check(owner,state,partial,text)
            if location_reply: return location_reply
            if not all(partial.get(k) is not None for k in ("service","city","area","slot","budget")):
                return cards.acknowledge(cards.clarification(partial),text)
            if state.get("booking") and self.store.booking(state["booking"],owner)["state"]=="held":
                await bus.call("payment","cancel",owner,booking=state["booking"])
            return cards.acknowledge(await self.quotes(bus,owner,partial),text)
        except (Rejected,TimeoutError) as exc:
            self.store.denied(state.get("booking",owner),str(exc),owner)
            return cards.envelope(str(exc)+". No new booking was confirmed. Ask for fresh providers or human review.")
