"""Explicit package details; deterministic validation owns quantities and scope."""
import re
from decimal import Decimal


FIELDS={
    "sofa_cleaning": {"seats":"How many sofa seats need cleaning (1 to 6)?", "material":"Is the sofa fabric, leather or suede? This demo supports fabric only."},
    "washing_machine": {"machine_type":"Is the washing machine front-loading or top-loading?", "issue":"What problem are you having with the washing machine?"},
    "furniture": {"item":"Which flat-pack item needs assembly: chair, table or bookshelf?", "quantity":"How many items need assembly (1 to 3)?", "instructions":"Do you have the manufacturer's assembly instructions? Reply 'instructions available' or 'no instructions'."},
    "mattress_cleaning":{"size":"What mattress size: single, double, queen or king?", "quantity":"How many mattresses of that size need cleaning (1 to 3)?"},
    "carpet_cleaning":{"length_ft":"What is the carpet length in feet?", "width_ft":"What is its width in feet?", "material":"What carpet material? This demo supports synthetic carpets only; wool and silk require a specialist."},
    "refrigerator":{"refrigerator_type":"Is it a single-door, double-door or side-by-side household refrigerator?", "issue":"What problem are you having with the refrigerator?"},
    "water_purifier":{"purifier_type":"Which purifier type: RO, UV, UF or a combination such as RO+UV?", "issue":"Is this routine servicing, or is there a problem? Describe the purpose, such as 'routine maintenance' or 'water flow is slow'."},
}
NUMBERS={"one":1,"two":2,"three":3,"four":4,"five":5,"six":6}
NUMBER=r"(-?\d+(?:\.\d+)?|one|two|three|four|five|six)"


def number(value):
    if value in NUMBERS:return NUMBERS[value]
    if len(value)>10:return None
    return float(value) if "." in value else int(value)


def extract_details(service,text,pending=None):
    low=text.casefold().strip()
    result={}
    if service=="sofa_cleaning":
        match=re.search(r"(?<![\w.-])"+NUMBER+r"[ -]*(?:(?:fabric|leather|suede)\s+)?(?:seats?|seaters?)\b",low)
        if not match and pending=="seats": match=re.fullmatch(NUMBER,low)
        if match: result["seats"]=number(match[1])
        for material in ("fabric","leather","suede"):
            if re.search(r"\b"+material+r"\b",low): result["material"]=material
    elif service=="washing_machine":
        types=[kind for kind in ("front","top") if re.search(r"\b"+kind+r"[ -]?(?:load\w*)?\b",low)]
        if len(types)==1: result["machine_type"]=types[0]+"-loading"
        if re.search(r"\b(not\s+(?:drain\w*|spin\w*|start\w*|work\w*)|leak\w*|nois\w*|vibrat\w*|won.t\s+\w+|broken)\b",low):
            result["issue"]=text.strip()[:300]
        elif pending=="issue" and len(low)>=8 and low not in ("i don't know","no problem"):
            result["issue"]=text.strip()[:300]
    elif service=="furniture":
        items=[item for item,pattern in (("chair",r"\bchairs?\b"),("table",r"\btables?\b"),("bookshelf",r"\bbookshel(?:f|ves)\b")) if re.search(pattern,low)]
        if len(items)==1: result["item"]=items[0]
        if re.search(r"\bwardrobes?\b",low): result["item"]="wardrobe"
        if len(items)>1: result["item"]="mixed items"
        match=re.search(r"(?<![\w.-])"+NUMBER+r"\s+(?:flat[ -]?pack\s+)?(?:chairs?|tables?|bookshel(?:f|ves)|items?)\b",low)
        if not match and pending=="quantity": match=re.fullmatch(NUMBER,low)
        if match: result["quantity"]=number(match[1])
        if re.search(r"\b(?:no|without|missing)\s+(?:assembly\s+)?instructions\b|\b(?:don't|do not)\s+have\s+(?:the\s+)?instructions\b",low): result["instructions"]=False
        elif re.search(r"\binstructions\s+(?:are\s+)?(?:available|included|provided)\b|\b(?:have|with)\s+(?:the\s+)?(?:assembly\s+)?instructions\b",low): result["instructions"]=True
        elif pending=="instructions" and low in ("yes","no"): result["instructions"]=low=="yes"
    elif service=="mattress_cleaning":
        sizes=[size for size in ("single","double","queen","king") if re.search(r"\b"+size+r"\b",low)]
        if sizes: result["size"]=sizes[0] if len(sizes)==1 else "mixed sizes"
        match=re.search(r"(?<![\w.-])"+NUMBER+r"\s+(?:(?:single|double|queen|king)(?:[ -]size)?\s+)?mat{1,2}ress(?:es)?\b",low)
        if not match and pending=="quantity":match=re.fullmatch(NUMBER,low)
        if match:result["quantity"]=number(match[1])
    elif service=="carpet_cleaning":
        dimension=r"(-?\d+(?:\.\d+)?)"
        pair=re.search(r"(?<![\w.-])"+dimension+r"\s*(?:ft|feet|foot)?\s*(?:by|x|×)\s*"+dimension+r"\s*(?:ft|feet|foot)?\b",low)
        units=bool(re.search(r"\b(?:ft|feet|foot)\b",low))
        if pair and (units or pending in ("length_ft","width_ft")):
            result.update(length_ft=number(pair[1]),width_ft=number(pair[2]))
        for field,label in (("length_ft","length"),("width_ft","width")):
            match=re.search(r"\b"+label+r"\s*(?:is\s*)?"+dimension+r"\s*(?:ft|feet|foot)\b",low)
            if not match and pending==field:match=re.fullmatch(dimension+r"\s*(?:ft|feet|foot)?",low)
            if match:result[field]=number(match[1])
        for material in ("synthetic","wool","silk","cotton"):
            if re.search(r"\b"+material+r"\b",low):result["material"]=material
    elif service=="refrigerator":
        kinds=[kind for kind,pattern in (("single-door",r"\bsingle[ -]door\b"),("double-door",r"\bdouble[ -]door\b"),("side-by-side",r"\bside[ -]by[ -]side\b")) if re.search(pattern,low)]
        if kinds:result["refrigerator_type"]=kinds[0] if len(kinds)==1 else "multiple types"
        if re.search(r"\bcommercial\b",low):result["refrigerator_type"]="commercial"
    elif service=="water_purifier":
        kinds=[kind for kind in ("ro","uv","uf") if re.search(r"\b"+kind+r"\b",low)]
        if kinds:result["purifier_type"]="+".join(kinds).upper()
        if re.search(r"\bgravity\b",low):result["purifier_type"]="gravity"
        if re.search(r"\broutine\b|\bregular maintenance\b",low):result["issue"]="Routine servicing"
    if service in ("refrigerator","water_purifier") and "issue" not in result:
        if re.search(r"\b(not\s+(?:cool\w*|freez\w*|work\w*)|leak\w*|nois\w*|slow|broken|won.t\s+\w+)\b",low) or (pending=="issue" and len(low)>=8):
            result["issue"]=text.strip()[:300]
    return result


def validate_details(service,details,complete=True):
    if not isinstance(details,dict): raise ValueError("Service details must be structured fields")
    fields=FIELDS.get(service,{})
    clean={key:details[key] for key in fields if key in details}
    if service=="sofa_cleaning":
        seats=clean.get("seats")
        if "seats" in clean and (type(seats) is not int or not 1<=seats<=6):
            raise ValueError("This package supports 1 to 6 sofa seats. Please give a number in that range.")
        if "material" in clean and clean["material"]!="fabric":
            raise ValueError("This demo cleans fabric sofas only; leather and suede need a different provider.")
    if service=="washing_machine":
        if "machine_type" in clean and clean["machine_type"] not in ("front-loading","top-loading"):
            raise ValueError("Choose front-loading or top-loading for one household washing machine.")
        issue=clean.get("issue")
        if "issue" in clean and (not isinstance(issue,str) or not 8<=len(issue.strip())<=300):
            raise ValueError("Describe the washing-machine problem in 8 to 300 characters.")
    if service=="furniture":
        if "item" in clean and clean["item"] not in ("chair","table","bookshelf"):
            raise ValueError("Choose one item type: flat-pack chair, table or bookshelf. Wardrobes and mixed-item jobs need a separate quote.")
        qty=clean.get("quantity")
        if "quantity" in clean and (type(qty) is not int or not 1<=qty<=3):
            raise ValueError("This package supports 1 to 3 items of the same type.")
        if "instructions" in clean and clean["instructions"] is not True:
            raise ValueError("Assembly requires the manufacturer's instructions. No quote has been created.")
    if service=="mattress_cleaning":
        if "size" in clean and clean["size"] not in ("single","double","queen","king"):
            raise ValueError("Choose one mattress size: single, double, queen or king. Mixed sizes require separate quotes.")
        if "quantity" in clean and (type(clean["quantity"]) is not int or not 1<=clean["quantity"]<=3):
            raise ValueError("This package supports 1 to 3 mattresses of one size.")
    if service=="carpet_cleaning":
        for field in ("length_ft","width_ft"):
            if field in clean and (type(clean[field]) not in (int,float) or not Decimal(str(clean[field])).is_finite() or not Decimal('.5')<=Decimal(str(clean[field]))<=20):
                raise ValueError("Give a carpet dimension from 0.5 to 20 feet.")
            if field in clean and Decimal(str(clean[field])).as_tuple().exponent < -2:
                raise ValueError("Give carpet dimensions in feet with at most two decimal places.")
        if all(field in clean for field in ("length_ft","width_ft")) and Decimal(str(clean['length_ft']))*Decimal(str(clean['width_ft']))>150:
            raise ValueError("This package covers at most 150 square feet. Please give a smaller carpet length in feet, or request a separate package.")
        if "material" in clean and clean["material"]!="synthetic":
            raise ValueError("This demo cleans synthetic carpets only. Wool, silk and cotton require a different provider.")
    if service=="refrigerator" and "refrigerator_type" in clean and clean["refrigerator_type"] not in ("single-door","double-door","side-by-side"):
        raise ValueError("Choose a single-door, double-door or side-by-side household refrigerator; commercial equipment is excluded.")
    if service=="water_purifier" and "purifier_type" in clean and clean["purifier_type"] not in ("RO","UV","UF","RO+UV","RO+UF","UV+UF","RO+UV+UF"):
        raise ValueError("This demo services RO, UV, UF or their combinations; other purifier types need a different provider.")
    if service in ("refrigerator","water_purifier") and "issue" in clean and (not isinstance(clean['issue'],str) or not 8<=len(clean['issue'].strip())<=300):
        raise ValueError("Describe the appliance problem or servicing purpose in 8 to 300 characters.")
    if complete:
        missing=[key for key in fields if key not in clean]
        if missing: raise ValueError(fields[missing[0]])
    return clean


def next_question(service,details):
    for key,question in FIELDS.get(service,{}).items():
        if key not in details: return key,question
    return None,None
