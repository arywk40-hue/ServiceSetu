"""One customer conversation, isolated by sender AND ACP session."""
import json
import re
import secrets
import os
from .core import Rejected
from . import cards
from .reasoning import Reasoner,rupees
from .locations import clean_context,resolve,location_only,mentions,canonical,bare_location_answer,LOCATION_FIELDS,suggestion,ALIASES
from .coverage import requires_pin,location_label
from .addresses import validate_address
from .appointments import appointment
from .catalogue import SERVICES,CATEGORIES,unavailable_message,package_from_text,detect_service
from .service_details import FIELDS,extract_details,validate_details,next_question
from .fet_payments import fet_amount as configured_fet_amount
from .places import search_places, parse_places_intent, PlacesError, safe_maps_url
from .external_conversation import ExternalConversation


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
        service=re.search(r"\bservice\s*(?:(?:is|=|:)\s*)?[\"']?(ac|plumbing|cleaning|electrical|kitchen_cleaning|sofa_cleaning|washing_machine|furniture|mattress_cleaning|carpet_cleaning|refrigerator|water_purifier)\b",low)
        area=re.search(r"\barea\s*(?:(?:is|=|:)\s*)?[\"']?(indiranagar)\b",low)
        slot=re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:[+-]\d{2}:\d{2}|Z)",text)
        budget=re.search(r"\bbudget_rupees\s*[\"']?\s*(?:(?:is|=|:)\s*)?(\d+(?:\.\d{1,2})?)",low)
        if service and area and slot and budget:
            return {"action":"search","service":service.group(1),"area":area.group(1),"slot":slot.group(),"budget_rupees":budget.group(1)}
    return {}


class Conversation:
    def __init__(self,store,reasoner=None,payment_mode=None,external=None):
        self.store=store
        self.reasoner=reasoner or Reasoner()
        self.payment_mode=payment_mode or os.getenv('PAYMENT_MODE','mock')
        self.external=external or ExternalConversation(store)

    def review_card(self,q,b,nonce,state=None):
        offer=(state or {}).get('fet_offer') or {}
        amount=offer.get('token_amount') if offer.get('quote_id')==q['id'] else None
        return cards.review(q,b,nonce,payment_mode=self.payment_mode,fet_amount=amount)

    def ask_address(self,owner,state,q):
        if q['expires']<=self.store.clock():raise Rejected('Quote expired; request fresh providers before adding an address')
        nonce='ad_'+secrets.token_hex(16)
        state.update(pending_address_quote=q['id'],address_token=nonce)
        state.pop('pending_booking_address',None)
        state.pop('approval_token',None)
        self.store.save_session(owner,state)
        return cards.address_choice(q,nonce)

    async def review_address(self,owner,state,q,address,bus):
        if address is not None:
            try:validate_address(address,q['location'])
            except ValueError as exc:raise Rejected(str(exc)) from None
        request_id=state.get('intent')
        if request_id and self.store.booking(request_id,owner)['state']!='requested':request_id=None
        b=await bus.call('booking','hold',owner,quote=q['id'],recovery_of=state.get('recovery_of'),request_id=request_id,address=address,defer_address=address is None)
        nonce='at_'+secrets.token_hex(16)
        state.update(booking=b['id'],quote=q['id'],approval_token=nonce)
        if self.payment_mode=='fet_testnet':
            amount,atomic=configured_fet_amount()
            state['fet_offer']={'quote_id':q['id'],'network':'dorado-1','denom':'atestfet',
                                'token_amount':amount,'atomic_amount':str(atomic)}
        else:state.pop('fet_offer',None)
        for field in ('pending_address_quote','pending_booking_address','address_token'):state.pop(field,None)
        self.store.save_session(owner,state)
        return self.review_card(q,b,nonce,state)

    def details_check(self,owner,state,partial):
        service=partial.get("service")
        details=partial.get("details",{})
        question=None
        pending=None
        for key in FIELDS.get(service,{}):
            if key in details:
                try: validate_details(service,{key:details[key]},complete=False)
                except ValueError as exc:
                    pending,question=key,str(exc)
                    break
        if not question:
            try:validate_details(service,details,complete=False)
            except ValueError as exc:
                pending=next(iter(FIELDS.get(service,{})),None)
                question=str(exc)
        if not question: pending,question=next_question(service,details)
        if question:
            state["partial_job"]=partial
            state["pending_service_field"]=pending
            state.pop("availability_options",None)
            state.pop("availability_token",None)
            for field in ("quotes","quote","approval_token"):state.pop(field,None)
            self.store.save_session(owner,state)
            return cards.envelope(question+"\n\nYour other request details are retained. No provider has been reserved or paid.")
        state.pop("pending_service_field",None)
        return None

    def location_check(self, owner, state, partial, text=""):
        partial, proposal, unsupported = resolve(partial,text)
        location_error=partial.pop('_location_error',None)
        state["partial_job"]=partial
        state.pop("availability_options",None)
        state.pop("availability_token",None)
        state.pop("pending_location",None)
        if proposal: state["pending_location"]=proposal
        self.store.save_session(owner,state)
        if proposal:
            place=location_label(proposal)
            return partial,cards.envelope(f"Did you mean {place}? Reply yes to confirm the location, or tell me the correct area and city. This confirms only your location, not a booking or payment.")
        if unsupported:
            return partial,cards.envelope((location_error or 'Please provide your Indian city and locality (PIN optional).')+' Your other request details are retained. No booking or payment was made.')
        if requires_pin(partial,self.store.providers()):
            state['pending_pin']=True
            state['pending_location_field']='pincode'
            self.store.save_session(owner,state)
            return partial,cards.envelope('Please give the six-digit PIN code for '+location_label(partial)+'. I will check provider coverage there. Your service, appointment and budget are retained; nothing has been reserved or paid.')
        state.pop('pending_pin',None)
        missing=next((field for field in ('city','area') if not partial.get(field)),None)
        if missing:state['pending_location_field']=missing
        else:state.pop('pending_location_field',None)
        self.store.save_session(owner,state)
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
        if result.get('coverage_count',1)==0:
            state.update(job=job,partial_job=job,quotes=[],intent=intent['id'],recovery_of=recovery_of)
            for field in ('pending_address_quote','pending_booking_address','address_token','approval_token','availability_options','availability_token'):state.pop(field,None)
            self.store.save_session(owner,state)
            prefix='No available pilot business currently covers ' if any(p.get('record_kind')=='pilot' for p in self.store.providers()) else 'No onboarded demo provider currently covers '
            place_lbl=location_label(job)
            svc_lbl=SERVICES[job['service']]['label']
            msg=prefix+place_lbl+' for '+svc_lbl+'. Your location was accepted. No appointment was reserved or payment taken. You can provide a different locality, or request human review.'
            msg+=f"\n\nTo discover real local businesses on Google Maps, send: 'Find real {svc_lbl.lower()} in {place_lbl}'."
            cta={'label':'Search Google Maps','selection':{'action':'places_search','service':job['service'],'location':place_lbl}}
            return cards.envelope(msg,'detail',{'title':f'No onboarded coverage in {place_lbl}','summary_rows':[{'label':'Location','value':place_lbl},{'label':'Service','value':svc_lbl},{'label':'Onboarded status','value':'No onboarded providers'}],'ctas':[cta]})
        quotes=[]
        excluded=result["excluded"]
        for pid in result["providers"]:
            try:
                trust=await bus.call("verification","check",owner,provider=pid,slot=job["slot"])
                if not trust["eligible"]: continue
                q=await bus.call("provider:"+pid,"quote",owner,slot=job["slot"],job=job)
                # Validate worker evidence against deterministic requirements.
                canonical=self.store.get_quote(q["id"],owner)
                expected_location={field:job[field] for field in LOCATION_FIELDS if field in job}
                if canonical["provider"]!=pid or canonical["slot"]!=job["slot"] or canonical["amount"]>job["budget"] or canonical.get("service")!=job["service"] or canonical.get("details",{})!=job.get("details",{}) or canonical.get('location')!=expected_location:
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
        for field in ('pending_address_quote','pending_booking_address','address_token'):state.pop(field,None)
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

    async def handle(self,owner,text,bus,request_id=None):
        text=strip_recipient(text)
        state=self.store.session(owner)
        picked=selection(text)
        action=picked.get("action")
        low=text.lower()
        skip_address=low.strip() in ('skip','skip for now','skip address','not now','later','add it later','provide later',"i'll provide it later",'i will provide it later',"i don't know my address",'i do not know my address','i will share it later')
        try:
            external_reply=await self.external.handle(owner,text,picked,state)
            if external_reply is not None:return external_reply
            if action=='view_maps':
                name=picked.get('name','the business')
                url=safe_maps_url(picked.get('url','https://maps.google.com'))
                if not url:raise Rejected('Only an HTTPS Google Maps listing link can be opened.')
                return cards.envelope(f"Google Maps listing for **{name}**:\n{url}\n\nFound on Google Maps; not onboarded to ServiceSetu.\nThis business is not an onboarded ServiceSetu provider. Appointments, pricing, and payments cannot be processed through ServiceSetu. Please contact them directly via Google Maps.")
            if action=='places_search':
                query=picked.get('query')
                if not query:
                    svc=picked.get('service')
                    loc=picked.get('location') or picked.get('location_label') or picked.get('area') or picked.get('city')
                    svc_label=SERVICES.get(svc,{}).get('label',svc) if svc else 'services'
                    query=f"{svc_label} in {loc}" if loc else svc_label
                try:
                    places=await search_places(query)
                    state['discovered_places']=[p['id'] for p in places if p.get('id')]
                    self.store.save_session(owner,state)
                    return cards.places_results(places,query,picked.get('location_label') or picked.get('location'))
                except PlacesError as exc:
                    return cards.places_error(str(exc))
            if action=='check_payment' or low.strip() in ('check payment','check payment status'):
                bid=picked.get('booking_id') if action else state.get('booking')
                if not bid or bid!=state.get('booking'):raise Rejected('Check payment for your current booking')
                b=await bus.call('payment','refresh',owner,booking=bid)
                return cards.booking_status(b,self.store.get_quote(b['quote'],owner))
            if action=='resume_checkout' or low.strip()=='resume checkout':
                bid=picked.get('booking_id') if action else state.get('booking')
                if bid!=state.get('booking') or not bid:raise Rejected('Resume the current booking checkout')
                b=self.store.booking(bid,owner)
                if not b['approved']:raise Rejected('Review and explicitly approve the exact quote before checkout')
                result=await bus.call('payment','start',owner,booking=bid)
                if result.get('razorpay'):return cards.razorpay_checkout(result)
                if result.get('stripe'):return dict(cards.envelope('Resume the same Stripe TEST checkout. No new payment or booking is created by retrying.'),payment=result)
                if result.get('fet_invoice'):
                    invoice=result['fet_invoice']
                    return dict(cards.envelope(f"Resume the same Dorado FET testnet invoice for {invoice['token_amount']} FET. No new invoice or booking is created by retrying."),payment=result)
                return cards.booking_status(result['booking'],self.store.get_quote(b['quote'],owner))
            problem=re.fullmatch(r'\s*report (?:a )?problem\s*:\s*(.+)',text,re.I|re.S)
            if action=='problem_form' or low.strip() in ('report a problem','report problem'):
                bid=picked.get('booking_id') if action else state.get('booking')
                b=self.store.booking(bid,owner)
                if b['state'] not in ('confirmed','completed','cancelled') or not b['quote']:raise Rejected('Choose a confirmed, completed or cancelled booking')
                nonce='rp_'+secrets.token_hex(16);state.update(problem_booking=bid,problem_token=nonce);self.store.save_session(owner,state)
                return cards.envelope('Describe the problem for the trusted operator. This records a report; it does not promise a refund or resolution. Do not include payment credentials.', 'form',{'title':'Report a booking problem','fields':[{'name':'problem','kind':'text','label':'What happened?','required':True}],'submit_cta':{'label':'Record report','selection':{'action':'report_problem','booking_id':bid,'problem_token':nonce}}})
            if problem or action=='report_problem':
                bid=state.get('problem_booking') if action else state.get('booking')
                if action and (not state.get('problem_token') or picked.get('booking_id')!=bid or picked.get('problem_token')!=state.get('problem_token')):raise Rejected('Use the latest problem form for your booking')
                result=await bus.call('booking','report_problem',owner,booking=bid,text=picked.get('problem') if action else problem[1],client_id=request_id or (state.get('problem_token') if action else None))
                return cards.envelope('Problem report recorded for operator review. Reference: '+result['id']+'. This is an acknowledgement of receipt, not a resolution or refund. Send show what happened to see the report in your booking history.')
            if action=='completion_review':
                bid=picked.get('booking_id');b=self.store.booking(bid,owner)
                if b['state']!='confirmed':raise Rejected('Only a confirmed booking can complete')
                nonce='done_'+secrets.token_hex(16);state.update(completion_booking=bid,completion_token=nonce);self.store.save_session(owner,state)
                return cards.envelope('Confirm only after the service is finished. You can still report a problem after completion.','review',{'title':'Confirm service completion','summary_rows':[{'label':'Provider','value':self.store.get_quote(b['quote'],owner)['name']}],'approve_cta':{'label':'Work is finished','selection':{'action':'confirm_completion','booking_id':bid,'completion_token':nonce}},'reject_cta':{'label':'Keep booking open','selection':{'action':'keep_booking_open','booking_id':bid}}})
            if action=='keep_booking_open':
                b=self.store.booking(picked.get('booking_id'),owner)
                return cards.booking_status(b,self.store.get_quote(b['quote'],owner))
            if action=='confirm_completion':
                if not state.get('completion_token') or picked.get('completion_token')!=state['completion_token'] or picked.get('booking_id')!=state.get('completion_booking'):raise Rejected('Use the latest completion review')
                b=await bus.call('booking','complete',owner,booking=picked['booking_id'])
                return cards.booking_status(b,self.store.get_quote(b['quote'],owner))
            message=re.match(r'^\s*(?:message|tell)\s+(?:the\s+)?provider\s*:\s*(.*)$',text,re.I|re.S)
            if message or action=='message_provider':
                bid=state.get('message_form_booking') if action else state.get('booking')
                if not bid:raise Rejected('Confirm a booking before messaging a provider')
                if action and (picked.get('booking_id')!=bid or picked.get('message_token')!=state.get('message_token')):
                    raise Rejected('Use the message form for the current booking')
                body=picked.get('message') if action else message[1]
                await bus.call('booking','message',owner,booking=bid,text=body,client_id=request_id)
                return cards.message_saved(bid)
            if low.strip() in ('message provider','tell provider') or action=='compose_message':
                bid=picked.get('booking_id') if action else state.get('booking')
                if not bid:raise Rejected('Choose your confirmed booking')
                b=self.store.booking(bid,owner)
                if b['state']!='confirmed':raise Rejected('Messaging is available only for confirmed bookings')
                nonce='mt_'+secrets.token_hex(16);state.update(message_token=nonce,message_form_booking=bid);self.store.save_session(owner,state)
                return cards.envelope("Write a message to your assigned provider. Do not include payment credentials. Messages coordinate the visit; changes to price, appointment or scope require separate approval.",'form',{'title':'Message provider','fields':[{'name':'message','kind':'text','label':'Your message','required':True}],'submit_cta':{'label':'Send message','selection':{'action':'message_provider','booking_id':bid,'message_token':nonce}}})
            thread_match=re.fullmatch(r'(?:show |view )?messages(?: (b_[a-f0-9]{16}))?',low.strip())
            if thread_match or low.strip()=='show more messages' or action=='open_messages':
                bid=(picked.get('booking_id') if action else thread_match[1] if thread_match else None) or state.get('booking')
                if not bid:raise Rejected('No booking messages yet')
                cursor=state.get('message_cursor',{})
                after=picked.get('after',0) if action else cursor.get('after',0) if low.strip()=='show more messages' and cursor.get('booking')==bid else 0
                result=await bus.call('booking','messages',owner,booking=bid,after=after)
                state['message_cursor']={'booking':bid,'after':result['next_after']};self.store.save_session(owner,state)
                return cards.message_thread(bid,result,self.store.booking(bid,owner)['state']=='confirmed')
            if action=='booking_history':
                bid=picked.get('booking_id')
                result=await bus.call('booking','timeline',owner,booking=bid)
                return cards.booking_history(result['events'],self.store.booking(bid,owner))
            if low.strip(" ?.! ") in ("services","what services do you offer","available services","show services"):
                return cards.service_menu(self.store.providers())
            groups={"show cleaning services":"cleaning","show appliance services":"appliances","show repair services":"repairs","show assembly services":"assembly"}
            if low.strip(" ?.! ") in groups:
                return cards.service_menu(self.store.providers(),groups[low.strip(" ?.! ")])
            if action=="choose_category":
                category=picked.get("category")
                if not isinstance(category,str) or category not in CATEGORIES:raise Rejected("Choose a listed service group")
                return cards.service_menu(self.store.providers(),category)
            if action=="choose_service":
                service=picked.get("service")
                if not isinstance(service,str) or service not in SERVICES: raise Rejected("Choose a listed service")
                partial={"service":service,"details":{}}
                if SERVICES[service].get("package"): partial["package"]=SERVICES[service]["package"]
                state["partial_job"]=partial
                for field in ("pending_address_quote","pending_booking_address","address_token","pending_location","pending_location_field","pending_pin","pending_service_field","availability_options","availability_token","quotes","quote","approval_token"):
                    state.pop(field,None)
                self.store.save_session(owner,state)
                return self.details_check(owner,state,partial) or cards.clarification(partial)
            option_match=re.fullmatch(r"(?:option\s+)?([1-4])",low)
            partial=state.get("partial_job")
            if not action and option_match and partial and low.startswith("option"):
                return self.details_check(owner,state,partial) or cards.clarification(partial)
            if not action and option_match and not partial and state.get("availability_options"):
                picked={"action":"choose_time","option":int(option_match.group(1)),"availability_token":state.get("availability_token")}
                action="choose_time"
            elif not action and option_match and not partial and state.get("quotes"):
                index=int(option_match.group(1))-1
                if index>=len(state["quotes"]):
                    quotes=[self.store.get_quote(qid,owner) for qid in state["quotes"]]
                    fresh=[quote for quote in quotes if quote["expires"]>self.store.clock()]
                    if len(fresh)!=len(quotes): return cards.envelope("The previous provider quotes have expired. Send a fresh service request to see current options. No booking or payment was made.")
                    reply=cards.shortlist(quotes,[])
                    reply["text"]=f"Only {len(quotes)} provider option(s) are available in this shortlist. Choose one below.\n\n"+reply["text"]
                    return reply
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
                for field in ('pending_address_quote','pending_booking_address','address_token','approval_token'):state.pop(field,None)
                self.store.save_session(owner,state)
                job={"service":str(picked.get("service","")).strip().casefold(),"area":picked.get("area",""),"city":picked.get("city"),
                     "slot":picked.get("slot"),"budget":rupees(picked.get("budget_rupees"))}
                job.update({field:picked[field] for field in ('pincode','country') if picked.get(field) not in (None,'')})
                # The form labels explicitly name each bounded service package.
                package=SERVICES.get(job["service"],{}).get("package")
                if package: job["package"]=package
                job["details"]={key:picked[key] for key in FIELDS.get(job["service"],{}) if key in picked}
                detail_reply=self.details_check(owner,state,job)
                if detail_reply: return detail_reply
                if isinstance(job["slot"],str) and not re.match(r"^\d{4}-\d{2}-\d{2}T",job["slot"]):
                    parsed=await self.reasoner.parse(job["slot"],self.store.clock())
                    job["slot"]=parsed.get("slot")
                    if parsed.get('_appointment_error'):return cards.envelope(parsed['_appointment_error'])
                    if parsed.get('requested_time'):job['requested_time']=parsed['requested_time']
                    if parsed.get("requested_day"): job["requested_day"]=parsed["requested_day"]
                job,location_reply=self.location_check(owner,state,job)
                if location_reply: return location_reply
                if not job.get("slot"): return cards.clarification(job)
                job=self.store.normalize_job(job)
                if state.get("booking") and self.store.booking(state["booking"],owner)["state"]=="held":
                    await bus.call("payment","cancel",owner,booking=state["booking"])
                return await self.quotes(bus,owner,job)
            if low.strip()=='cancel address':
                for field in ('pending_address_quote','pending_booking_address','address_token','approval_token'):state.pop(field,None)
                self.store.save_session(owner,state)
                return cards.envelope('Address entry cancelled. No new booking was reserved or paid. Choose a provider again when ready.')
            if action=='add_address' or low.strip()=='add address':
                bid=picked.get('booking_id') if action else state.get('booking')
                b=self.store.booking(bid,owner)
                if b['state'] not in ('held','confirmed'):raise Rejected('Add an address only to your active booking')
                if b.get('service_address'):return cards.booking_status(b,self.store.get_quote(b['quote'],owner))
                nonce='ad_'+secrets.token_hex(16)
                state.update(pending_booking_address=bid,address_token=nonce)
                state.pop('pending_address_quote',None)
                self.store.save_session(owner,state)
                return cards.booking_address_form(b,nonce)
            if action=='set_booking_address' or (state.get('pending_booking_address') and not action and not skip_address and low.strip() not in ('status','booking status','help','show messages','cancel booking')):
                bid=state.get('pending_booking_address')
                if not bid or (action and (picked.get('booking_id')!=bid or picked.get('address_token')!=state.get('address_token'))):raise Rejected('Use the latest address form')
                address=picked.get('address_line') if action else text
                if isinstance(address,str) and address.strip():
                    b=await bus.call('booking','provide_address',owner,booking=bid,address=address)
                    if b['state']=='held':
                        nonce='at_'+secrets.token_hex(16);state['approval_token']=nonce
                    else:nonce=None
                else:b=self.store.booking(bid,owner);nonce=state.get('approval_token')
                for field in ('pending_booking_address','address_token'):state.pop(field,None)
                self.store.save_session(owner,state)
                q=self.store.get_quote(b['quote'],owner)
                return self.review_card(q,b,nonce,state) if b['state']=='held' else cards.booking_status(b,q)
            if state.get('pending_booking_address') and not action and skip_address:
                bid=state.pop('pending_booking_address');state.pop('address_token',None);self.store.save_session(owner,state)
                b=self.store.booking(bid,owner)
                q=self.store.get_quote(b['quote'],owner)
                return self.review_card(q,b,state.get('approval_token'),state) if b['state']=='held' else cards.booking_status(b,q)
            if action in ('open_quote_address','skip_address') or (state.get('pending_address_quote') and not action and skip_address):
                qid=state.get('pending_address_quote')
                if not qid or (action and (picked.get('quote_id')!=qid or picked.get('address_token')!=state.get('address_token'))):raise Rejected('Use the latest address choice')
                q=self.store.get_quote(qid,owner)
                if action=='open_quote_address':return cards.address_form(q,state['address_token'])
                return await self.review_address(owner,state,q,None,bus)
            if low.strip()=='change address':
                if not state.get('quote') or not state.get('booking'):raise Rejected('Choose a provider first')
                b=self.store.booking(state['booking'],owner)
                if b['state']!='held':raise Rejected('Start a new request to change the address of a confirmed or cancelled booking')
                if state.get('recovery_of'):raise Rejected('A replacement keeps the original address; start a new request to change it')
                await bus.call('payment','cancel',owner,booking=b['id'])
                return self.ask_address(owner,state,self.store.get_quote(state['quote'],owner))
            if action=='set_address' or (state.get('pending_address_quote') and not action and low.strip() not in ('status','booking status','show what happened','audit','timeline','audit details','help','cancel booking','recover','find a replacement','provider cancelled')):
                qid=state.get('pending_address_quote')
                if not qid or (action and (picked.get('quote_id')!=qid or picked.get('address_token')!=state.get('address_token'))):
                    raise Rejected('This address form is no longer current; select a provider again')
                q=self.store.get_quote(qid,owner)
                address=picked.get('address_line') if action else text
                if action and (address is None or isinstance(address,str) and not address.strip()):address=None
                if not action and (detect_service(text) or re.search(r'\b(change|budget|tomorrow|under)\b',low)):
                    return cards.envelope("Please finish the service address, or send 'cancel address' before changing the request. Nothing has been reserved or paid.")
                return await self.review_address(owner,state,q,address,bus)
            if action=="select":
                target_id=str(picked.get("quote_id") or picked.get("place_id") or "")
                if target_id.startswith(("ChIJ","place_","places/")) or target_id in state.get("discovered_places",[]):
                    raise Rejected("Businesses found on Google Maps are not onboarded to ServiceSetu. They cannot be booked, scheduled, or paid through ServiceSetu. Only onboarded providers with verified booking arrangements may be booked.")
                if state.get("partial_job"):
                    return self.details_check(owner,state,state["partial_job"]) or cards.clarification(state["partial_job"])
                qid=picked.get("quote_id")
                if qid not in state.get("quotes",[]): raise Rejected("Select a quote from this conversation's current shortlist")
                if state.get("booking"):
                    old=self.store.booking(state["booking"],owner)
                    if old["state"]=="held" and old["quote"]!=qid:
                        await bus.call("payment","cancel",owner,booking=old["id"])
                q=self.store.get_quote(qid,owner)
                if state.get('recovery_of'):
                    address=self.store.booking(state['recovery_of'],owner).get('service_address')
                    if address:return await self.review_address(owner,state,q,address['address_line'],bus)
                return self.ask_address(owner,state,q)
            if action=="approve":
                target_q=str(picked.get("quote_id") or "")
                if target_q.startswith(("ChIJ","place_","places/")) or target_q in state.get("discovered_places",[]):
                    raise Rejected("Businesses found on Google Maps are not onboarded to ServiceSetu and cannot be approved or paid.")
                required={"booking_id":state.get("booking"),"quote_id":state.get("quote"),"approval_token":state.get("approval_token")}
                if not all(required.values()) or any(picked.get(k)!=v for k,v in required.items()):
                    raise Rejected("Approval must match the current review card, quote and token")
                bid=state["booking"]
                b=self.store.booking(bid,owner)
                if b["state"]=="confirmed": return cards.booking_status(b,self.store.get_quote(state["quote"],owner))
                payment_terms=state.get('fet_offer') if self.payment_mode=='fet_testnet' else None
                if self.payment_mode=='fet_testnet' and (not payment_terms or payment_terms.get('quote_id')!=state['quote']):
                    raise Rejected('The displayed FET amount is missing; reopen the exact quote review')
                await bus.call("booking","approve",owner,booking=bid,quote=state["quote"],payment_terms=payment_terms)
                result=await bus.call("payment","start",owner,booking=bid)
                if result.get('razorpay'):return cards.razorpay_checkout(result)
                if result.get("stripe"):
                    return dict(cards.envelope("Approved. Complete the embedded Stripe TEST checkout. The slot hold lasts two minutes; a late successful payment is refunded rather than confirming an expired slot."),payment=result)
                if result.get('fet_invoice'):
                    invoice=result['fet_invoice']
                    return dict(cards.envelope(f"Exact quote approval recorded. ASI:One will now request {invoice['token_amount']} FET on Dorado testnet. This separate test-token amount is not an INR conversion. Approve the payment in the wallet card before the booking hold expires."),payment=result)
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
                if not state.get("booking"):
                    if state.get('quotes'):
                        quotes=[self.store.get_quote(qid,owner) for qid in state['quotes']]
                        if all(q['expires']>self.store.clock() for q in quotes):return cards.shortlist(quotes,[])
                        return await self.quotes(bus,owner,state['job'],state.get('recovery_of'))
                    raise Rejected("No booking yet")
                b=await bus.call("booking","status",owner,booking=state["booking"])
                return cards.booking_status(b,self.store.get_quote(b["quote"],owner))
            if low in ("recover","find a replacement","provider cancelled") or action=='recover_booking':
                if not state.get("booking"): raise Rejected("No cancelled booking to recover")
                if action and picked.get('booking_id')!=state['booking']:raise Rejected('Recover the current cancelled booking; use a new request for another booking')
                return await self.quotes(bus,owner,state["job"],state["booking"])
            if low=="complete service":
                if not state.get("booking"): raise Rejected("No confirmed booking yet")
                b=await bus.call("booking","complete",owner,booking=state["booking"])
                return cards.booking_status(b,self.store.get_quote(b["quote"],owner))
            if re.search(r"\b(refund|payout|override|waive|reject provider)\b",low):
                raise Rejected("Discretionary refunds, payout changes and verification overrides require human review")
            if low in ("help","hi","hello","what can you do",""):
                return cards.job_form(self.store.providers()[0]["slots"][0])
            confirmation=re.sub(r"[,.!]+"," ",low).strip()
            confirmation=" ".join(confirmation.split())
            if state.get("pending_places_query") and confirmation in ("yes","yes please","correct","that's right","yes that's right","yes correct","yes that's correct"):
                pq=state.pop("pending_places_query")
                self.store.save_session(owner,state)
                try:
                    places=await search_places(pq)
                    state['discovered_places']=[p['id'] for p in places if p.get('id')]
                    self.store.save_session(owner,state)
                    return cards.places_results(places,pq)
                except PlacesError as exc:
                    return cards.places_error(str(exc))
            places_intent=parse_places_intent(text)
            if places_intent:
                loc=places_intent.get("location")
                if not loc:
                    return cards.envelope("Please specify your city and locality in India to search for local businesses on Google Maps (for example, 'Find real plumbers in Mandi, Himachal Pradesh').")
                proposal=None
                compact_loc=loc.replace(" ","").lower()
                for field in ('area','city'):
                    sug=suggestion(loc,field)
                    if sug and compact_loc not in ALIASES[field]:
                        proposal=sug
                        break
                if proposal:
                    state["pending_places_query"]=places_intent["query"].replace(loc,proposal)
                    self.store.save_session(owner,state)
                    return cards.envelope(f"Did you mean {proposal.title()}? Reply yes to search Google Maps there, or tell me the correct area and city. This searches local businesses, not a ServiceSetu booking.")
                try:
                    places=await search_places(places_intent["query"])
                    state['discovered_places']=[p['id'] for p in places if p.get('id')]
                    self.store.save_session(owner,state)
                    return cards.places_results(places,places_intent["query"],loc)
                except PlacesError as exc:
                    return cards.places_error(str(exc))
            # Parsing is permitted only for intake. Model output cannot authorize payment.
            partial=clean_context(state.get("partial_job",{}))
            typed_location={}
            for field in ("quotes","quote","approval_token","availability_options","availability_token"):
                state.pop(field,None)
            self.store.save_session(owner,state)
            if state.get("pending_location") and confirmation in ("yes","yes please","correct","that's right","yes that's right","yes correct","yes that's correct"):
                job=dict(state["pending_location"])
            elif state.get("pending_location") and confirmation in ("no","no thanks","incorrect"):
                state.pop("pending_location",None)
                state["partial_job"]=partial
                self.store.save_session(owner,state)
                return cards.envelope("Please tell me the correct locality and city in India (PIN optional). Your other request details are retained.")
            else:
                pending=state.get("pending_service_field")
                detail_answer=extract_details(partial.get("service"),text,pending) if pending else {}
                if location_only(text):
                    job=mentions(text)
                elif not pending and not detect_service(text) and bare_location_answer(text,state.get('pending_location_field')):
                    typed_location={state['pending_location_field']:text.strip()}
                    job=dict(typed_location)
                elif detail_answer and len(text.split())<=5 and detect_service(text) is None and not re.search(r"\d{4}-|\b(today|tomorrow|budget|under|inr|bangalore|bengaluru|indiranagar)\b",low):
                    # A short answer to a typed question must not reinterpret the budget or date.
                    job={}
                else:
                    job=await self.reasoner.parse(text,self.store.clock(),partial)
                if location_only(text):
                    job={field:job.get(field) for field in LOCATION_FIELDS}
            timing=appointment(text,self.store.clock(),partial)
            if timing.get('_appointment_error'):
                partial.pop('slot',None)
                partial.pop('requested_day',None)
                partial.pop('requested_time',None)
                state['partial_job']=partial
                self.store.save_session(owner,state)
                return cards.envelope(timing['_appointment_error']+' Your service, location and budget are retained. No booking or payment was made.')
            if timing:
                job.update(timing)
                for field in ('slot','requested_day','requested_time'):
                    if field in timing and timing[field] is None:partial.pop(field,None)
            explicit_location=mentions(text)
            explicit_location.update(typed_location)
            old_city=canonical(partial.get('city'),'city')
            new_city=canonical(explicit_location.get('city'),'city')
            if old_city and new_city and old_city!=new_city:
                for field in ('area','pincode'):
                    partial.pop(field,None)
                    job[field]=explicit_location.get(field)
            elif explicit_location.get('area') and partial.get('area') and canonical(explicit_location['area'],'area')!=canonical(partial['area'],'area'):
                partial.pop('pincode',None);job['pincode']=explicit_location.get('pincode')
            job.update({field:value for field,value in explicit_location.items() if field in LOCATION_FIELDS})
            if job.get("requested_day") and not job.get("slot") and partial.get("slot") and partial["slot"][:10]!=job["requested_day"]:
                partial.pop("slot",None)
            explicit_service=detect_service(text)
            if explicit_service:job["service"]=explicit_service
            partial.update({k:v for k,v in job.items() if v is not None})
            if isinstance(partial.get("service"),str): partial["service"]=partial["service"].strip().casefold()
            if partial.get("service") and (not isinstance(partial["service"],str) or not SERVICES.get(partial["service"],{}).get("bookable")):
                raise Rejected(unavailable_message(partial["service"]))
            definition=SERVICES.get(partial.get("service"),{})
            previous=state.get("partial_job",{})
            same_service=previous.get("service")==partial.get("service")
            partial["details"]=dict(previous.get("details",{})) if same_service else {}
            partial["details"].update(extract_details(partial.get("service"),text,state.get("pending_service_field") if same_service else None))
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
            detail_reply=self.details_check(owner,state,partial)
            if detail_reply: return detail_reply
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
