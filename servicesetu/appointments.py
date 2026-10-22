"""Deterministic appointment extraction for common Indian-English date formats."""
import re
import unicodedata
from datetime import datetime,timedelta,date
from zoneinfo import ZoneInfo

ZONE=ZoneInfo('Asia/Kolkata')
MONTHS={name:i for i,names in enumerate(('january jan','february feb','march mar','april apr','may','june jun','july jul','august aug','september sep sept','october oct','november nov','december dec'),1) for name in names.split()}
MONTH_PATTERN='(?:'+'|'.join(sorted(MONTHS,key=len,reverse=True))+')'


def appointment(text,now,context=None):
    context=context or {};low=unicodedata.normalize('NFKC',text).casefold()
    low=re.sub(r'(?<=\d)(st|nd|rd|th)\b','',low)
    today=datetime.fromtimestamp(now,ZONE).date();day=None;time=None;explicit=False
    iso=re.search(r'\b\d{4}-\d{2}-\d{2}t\d{2}:\d{2}(?::\d{2})?(?:[+-]\d{2}:\d{2}|z)\b',low)
    if iso:
        try:
            dt=datetime.fromisoformat(iso[0].upper()).astimezone(ZONE)
            return dict(slot=dt.isoformat(timespec='seconds'),requested_day=dt.date().isoformat(),requested_time=dt.strftime('%H:%M'))
        except ValueError:return dict(slot=None,_appointment_error='That date or time is not valid. Please give a valid appointment day and time.')
    try:
        if re.search(r'\bday after tomorrow\b',low):day=today+timedelta(days=2);explicit=True
        elif re.search(r'\btomorrow\b',low):day=today+timedelta(days=1);explicit=True
        elif re.search(r'\btoday\b',low):day=today;explicit=True
        else:
            match=re.search(r'\b(\d{4})-(\d{2})-(\d{2})\b',low)
            numeric=re.search(r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b',low)
            first=re.search(r'\b(\d{1,2})\s+('+MONTH_PATTERN+r')\.?\s*,?\s*(\d{4})?\b',low)
            second=re.search(r'\b('+MONTH_PATTERN+r')\.?\s+(\d{1,2})(?:\s*,?\s+(\d{4}))?\b',low)
            if match:day=date(*map(int,match.groups()));explicit=True
            elif numeric:day=date(int(numeric[3]),int(numeric[2]),int(numeric[1]));explicit=True
            elif first:day=date(int(first[3] or today.year),MONTHS[first[2]],int(first[1]));explicit=True
            elif second:day=date(int(second[3] or today.year),MONTHS[second[1]],int(second[2]));explicit=True
        if day is not None:day=day.isoformat()
    except ValueError:
        return dict(slot=None,_appointment_error='That calendar date is not valid. Please give a valid day and time; for example, 25 October 2026 at 2 pm.')
    # Accept am/pm in any case, with periods and spaces. Validate before 24-hour fallback.
    meridiem=re.search(r'(?<![\d:])(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?(?!\w)',low)
    clock=re.search(r'(?<![\d:])(\d{1,2}):(\d{2})(?![\d:])',low)
    if meridiem:
        h=int(meridiem[1]);m=int(meridiem[2] or 0)
        if not 1<=h<=12 or m>59:return dict(slot=None,_appointment_error='That time is not valid. Use a time such as 2 pm or 14:00.')
        time=f'{h%12+(12 if meridiem[3]=="p" else 0):02d}:{m:02d}'
    elif clock:
        h,m=map(int,clock.groups())
        if h>23 or m>59:return dict(slot=None,_appointment_error='That time is not valid. Use a time such as 2 pm or 14:00.')
        time=f'{h:02d}:{m:02d}'
    if not explicit and time is None:return {}
    prior=context.get('slot') or ''
    day=day or context.get('requested_day') or (prior[:10] if prior else None)
    vague=bool(re.search(r'\b(morning|afternoon|evening|night|sometime|anytime)\b',low))
    time=time or (None if vague else context.get('requested_time') or (prior[11:16] if prior else None))
    return dict(requested_day=day,requested_time=time,slot=f'{day}T{time}:00+05:30' if day and time else None)
