"""Nationwide location intake; provider coverage is checked separately."""
import re
import unicodedata
from difflib import SequenceMatcher

ALIASES = {
    'city': {'bengaluru':'bengaluru','bangalore':'bengaluru','mumbai':'mumbai','bombay':'mumbai',
             'delhi':'delhi','newdelhi':'new delhi','pune':'pune','hyderabad':'hyderabad',
             'chennai':'chennai','madras':'chennai','kolkata':'kolkata','calcutta':'kolkata',
             'jaipur':'jaipur','ahmedabad':'ahmedabad','gandhinagar':'gandhinagar',
             'gurgaon':'gurugram','gurugram':'gurugram','noida':'noida','lucknow':'lucknow',
             'kochi':'kochi','cochin':'kochi','mangaluru':'mangaluru','mangalore':'mangaluru',
             'chandigarh':'chandigarh','bhopal':'bhopal','indore':'indore','patna':'patna',
             'surat':'surat','nagpur':'nagpur','bhubaneswar':'bhubaneswar'},
    'area': {'indiranagar':'indiranagar','powai':'powai'},
}
LOCATION_FIELDS=('city','area','pincode','country')


def compact(value):
    if not isinstance(value,str): return ''
    return re.sub(r'[\W_]+','',unicodedata.normalize('NFKC',value).casefold())


def canonical(value,field):
    if not isinstance(value,str): return None
    text=' '.join(unicodedata.normalize('NFKC',value).strip().casefold().split())
    if not 2<=len(text)<=100 or not any(unicodedata.category(c).startswith('L') for c in text): return None
    if any(not (unicodedata.category(c)[0] in 'LMN' or c in " .'-/&()") for c in text): return None
    return ALIASES[field].get(compact(text),text)


def country_code(value):
    if value is None or value=='':return 'IN'
    text=''.join(unicodedata.normalize('NFKC',value).casefold().split()) if isinstance(value,str) else ''
    return 'IN' if text in ('in','india','bharat','भारत','इंडिया') else None


def pin_code(value):
    if type(value) is int:value=str(value)
    if not isinstance(value,str):return None
    text=re.sub(r'\s+','',unicodedata.normalize('NFKC',value))
    return text if re.fullmatch(r'[1-9][0-9]{5}',text) else None


def suggestion(value,field):
    word=compact(value)
    if len(word)<5 or word in ALIASES[field]:return None
    threshold=.8 if len(word)<=6 else .86
    matches={target for alias,target in ALIASES[field].items()
             if abs(len(word)-len(alias))<=2 and SequenceMatcher(None,word,alias).ratio()>=threshold}
    return next(iter(matches)) if len(matches)==1 else None


def mentions(text):
    words=re.findall(r'[^\W\d_]+',text.casefold(),re.UNICODE)
    found={}
    for field in ALIASES:
        exact,possible=None,None
        for size in (1,2,3):
            for index in range(len(words)-size+1):
                if any(w in ('not','no','outside','except') for w in words[max(0,index-2):index]):continue
                phrase=' '.join(words[index:index+size])
                if compact(phrase) in ALIASES[field]:exact=phrase
                elif size==1 and suggestion(phrase,field):possible=phrase
        if exact or possible:found[field]=exact or possible
    # Explicit labels work for any city/locality, including names outside the aliases.
    label=r'(?:city|town|area|locality|neighbou?rhood|country|pin(?:\s*code)?|postal\s*code)'
    for field,tag in (('city',r'city|town'),('area',r'area|locality|neighbou?rhood'),('country','country')):
        match=re.search(r'\b(?:'+tag+r')\s*(?:is\s+|[:=]\s*)(.+?)(?=[,;\n]|\s+'+label+r'\s*(?:is|[:=])|\s+\b(?:today|tomorrow|under|budget)\b|$)',text,re.I)
        if match:found[field]=match[1].strip()
    match=re.search(r'\b(?:pin(?:\s*code)?|postal\s*code)\s*(?:is\s*|[:=]\s*)?([0-9]{6}(?![0-9])|[0-9][0-9 ]{0,9})',text,re.I)
    if match:found['pincode']=match[1].strip()
    else:
        for match in re.finditer(r'\b[1-9][0-9]{5}\b',text):
            if re.search(r'(?:under|budget|inr|rs\.?|₹|max)\s*$',text[max(0,match.start()-20):match.start()],re.I):continue
            found['pincode']=match[0]
    if 'city' in found and 'area' not in found:
        city=re.search(re.escape(found['city']),text,re.I)
        if city:
            prefix=text[:city.start()].rstrip(' ,')
            area=re.search(r'\bin\s+([^,;\n]+)$',prefix,re.I)
            if area and canonical(area[1],'area'):found['area']=area[1].strip()
    elif 'city' not in found and 'area' not in found:
        in_match = re.search(r'\bin\s+([A-Za-zÀ-ž\s\'-]+?)(?:,\s*([A-Za-zÀ-ž\s\'-]+?))?(?=\s+(?:today|tomorrow|under|budget|at\b|\d{1,2}(?::\d{2})?\s*(?:am|pm)|\d{4}-)|[;.]|$)', text, re.I)
        if in_match:
            loc1 = in_match.group(1).strip()
            loc2 = in_match.group(2).strip() if in_match.group(2) else None
            non_loc = {'today', 'tomorrow', 'cash', 'advance', 'emergency', 'minutes', 'hours', 'service', 'services', 'cleaning', 'plumbing', 'ac', 'repair'}
            if loc1.lower() not in non_loc and loc2 and loc2.lower() not in non_loc:
                if canonical(loc1, 'area'): found['area'] = loc1
                if canonical(loc2, 'city'): found['city'] = loc2
    return found


def clean_context(partial):
    result=dict(partial)
    for field in ALIASES:result[field]=canonical(result.get(field),field)
    return result


def location_only(text):
    if pin_code(text):return True
    if re.fullmatch(r'\s*(?:my\s+)?(?:pin(?:\s*code)?|postal\s*code)\s*(?:is\s*|[:=]\s*)?[0-9][0-9 ]{4,9}\s*',text,re.I):return True
    if re.match(r'^\s*(?:(?:actually|my)\s+)?(?:city|town|area|locality|country|pin(?:\s*code)?|postal\s*code)\s*(?:is\b|[:=])',text,re.I):
        return not re.search(r'\b(today|tomorrow|under|budget|book|service)\b',text,re.I)
    if re.search(r'\d|[₹$]',text):return False
    words=re.findall(r'[^\W\d_]+',text.casefold(),re.UNICODE)
    covered=set()
    for index in range(len(words)):
        for size in (1,2,3):
            phrase=' '.join(words[index:index+size])
            if any(compact(phrase) in ALIASES[field] or suggestion(phrase,field) for field in ALIASES):
                covered.update(range(index,min(index+size,len(words))))
    fillers={'actually','i','mean','meant','my','location','area','city','is','in','at','it','its','the','correct','sorry','please','change','to','and'}
    return bool(covered) and all(index in covered or word in fillers for index,word in enumerate(words))


def bare_location_answer(text,field):
    if field not in ('city','area') or len(text.split())>5:return False
    low=text.casefold().strip()
    if low in ('yes','no','okay','ok','correct','india','in','bharat'):return False
    if re.search(r'\b(today|tomorrow|under|budget|book|need|service|please|at)\b|[₹$:=,;]',low):return False
    return canonical(text,field) is not None


def resolve(partial,text=''):
    result=dict(partial);result.update(mentions(text))
    pending={};error=None
    for field in ALIASES:
        value=result.get(field)
        if value is None or value=='':result[field]=None;continue
        exact=canonical(value,field)
        if exact is None:error='Please provide a city and locality as text.'
        elif compact(value) not in ALIASES[field] and suggestion(value,field):
            pending[field]=suggestion(value,field);exact=None
        result[field]=exact
    if result.get('pincode') is not None:
        value=pin_code(result['pincode'])
        if value is None:error='Please provide a six-digit Indian PIN code, for example 560038.'
        result['pincode']=value
    if result.get('country') is not None:
        result['country']=country_code(result['country'])
        if result['country'] is None:error='ServiceSetu currently accepts service locations in India. Please provide an Indian city and locality (PIN optional).'
    # Preserve the old area-only demo correction as a confirmation, never an assumption.
    if (result.get('area') or pending.get('area'))=='indiranagar' and not (result.get('city') or pending.get('city')) and not error:
        pending.setdefault('city','bengaluru')
    if error:result['_location_error']=error
    if pending:
        proposal={field:result[field] for field in LOCATION_FIELDS if result.get(field)}
        proposal.update(pending)
        return result,proposal,bool(error)
    return result,None,bool(error)
