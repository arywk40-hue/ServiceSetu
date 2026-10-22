"""Customer-entered service addresses; no geocoding or postal verification."""
import re
import unicodedata


def validate_address(value, location):
    if not isinstance(value,str) or any(unicodedata.category(c)=='Cc' and c not in '\r\n\t' for c in value):
        raise ValueError('Please enter the house/flat, building and street as text.')
    text=' '.join(value.split())
    if not 10<=len(text)<=500 or len(text.split())<3 or not any(c.isalpha() for c in text):
        raise ValueError('Please include your house/flat, building and street (10–500 characters).')
    if text.casefold() in ('use my previous address','same as before','i approve this booking') or re.match(r'^(approve|select|option|cancel|recover)\b',text,re.I):
        raise ValueError('Please provide the service address, not a booking command.')
    return dict(location,address_line=text)
