"""One customer conversation, isolated by sender AND ACP session."""
import json
import re
import secrets
from .core import Rejected
from . import cards
from .reasoning import Reasoner,rupees


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
        service=re.search(r"\bservice\s*(?:(?:is|=|:)\s*)?[\"']?(ac|plumbing)\b",low)
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
        state.pop("approval_token",None)
        state.pop("partial_job",None)
        self.store.save_session(owner,state)
        if not quotes: return cards.envelope("No eligible provider fits your slot and budget. "+"; ".join(f"{e['name']}: {e['reason']}" for e in excluded)+". Try tomorrow 10am/2pm or raise the budget.")
        explanation=await self.reasoner.explain(quotes,excluded)
        return cards.shortlist(quotes,excluded,explanation,recovery=bool(recovery_of))

    async def handle(self,owner,text,bus):
        text=strip_recipient(text)
        state=self.store.session(owner)
        picked=selection(text)
        action=picked.get("action")
        low=text.lower()
        try:
            if action=="search":
                if state.get("booking") and self.store.booking(state["booking"],owner)["state"]=="held":
                    await bus.call("payment","cancel",owner,booking=state["booking"])
                job={"service":picked.get("service"),"area":str(picked.get("area","")).lower(),"city":"bengaluru",
                     "slot":picked.get("slot"),"budget":rupees(picked.get("budget_rupees"))}
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
            job=await self.reasoner.parse(text,self.store.clock())
            partial=state.get("partial_job",{})
            partial.update({k:v for k,v in job.items() if v is not None})
            if partial.get("service") and partial["service"] not in ("ac","plumbing"):
                raise Rejected("Demo supports AC servicing and plumbing only")
            state["partial_job"]=partial
            self.store.save_session(owner,state)
            if not all(partial.get(k) is not None for k in ("service","city","area","slot","budget")):
                return cards.job_form(self.store.providers()[0]["slots"][0])
            if state.get("booking") and self.store.booking(state["booking"],owner)["state"]=="held":
                await bus.call("payment","cancel",owner,booking=state["booking"])
            return await self.quotes(bus,owner,partial)
        except (Rejected,TimeoutError) as exc:
            self.store.denied(state.get("booking",owner),str(exc),owner)
            return cards.envelope(str(exc)+". No new booking was confirmed. Ask for fresh providers or human review.")
