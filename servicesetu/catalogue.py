"""Service definitions shared by intake and quote construction."""
import re
from decimal import Decimal,ROUND_CEILING


SERVICES = {
    "ac": {"label": "AC servicing", "bookable": True,
           "pattern": r"\bac\b|air.condition",
           "scope": "One AC service visit",
           "exclusions": "Parts and additional work require a new quote and approval"},
    "plumbing": {"label": "Plumbing", "bookable": True,
                 "pattern": r"\bplumb\w*\b|\btap\b|\bleak\w*\b",
                 "scope": "One standard tap repair visit",
                 "exclusions": "Parts and additional work require a new quote and approval"},
    "cleaning": {"label": "Bathroom cleaning", "bookable": True,
                 "pattern": r"\bclean\w*\b|\bhousekeeping\b",
                 "package": "one bathroom cleaning",
                 "scope": "Cleaning of one bathroom: accessible floor, wall tiles, basin and toilet surfaces",
                 "exclusions": "Extra bathrooms, whole-home cleaning, mould remediation, hazardous waste and repairs are excluded; extra work requires a new quote and approval"},
    "electrical": {"label": "Electrical inspection", "bookable": True,
                   "pattern": r"\belectric\w*\b|\bwiring\b|\bsocket\w*\b",
                   "package": "electrical inspection",
                   "scope": "One electrical inspection visit for one reported household issue; assessment only",
                   "exclusions": "Repairs, parts, rewiring, mains work and emergency response are excluded; extra work requires a new quote and approval"},
    "kitchen_cleaning": {"label": "Kitchen cleaning", "bookable": True,
                         "pattern": r"\bkitchen\b", "package": "one kitchen cleaning",
                         "scope": "Cleaning of one household kitchen: accessible counters, sink, hob exterior and floor",
                         "exclusions": "Cabinet interiors, chimney dismantling, appliance interiors, hazardous waste and repairs are excluded; extra work requires a new quote and approval"},
    "sofa_cleaning": {"label": "Fabric sofa cleaning", "bookable": True,
                      "pattern": r"\bsofa\b|\bcouch\b", "package": "sofa cleaning",
                      "scope": "Cleaning of the confirmed number of fabric sofa seats",
                      "exclusions": "Leather, suede, cushions sold separately, stain-removal guarantees and repairs are excluded; extra work requires a new quote and approval"},
    "washing_machine": {"label": "Washing-machine inspection", "bookable": True,
                        "pattern": r"\bwashing[ -]?machine\b|\bwasher\b", "package": "washing machine inspection",
                        "scope": "Inspection of one household washing machine for the reported problem; diagnosis only",
                        "exclusions": "Parts, repairs, installation and commercial machines are excluded; any repair needs a separate quote and approval"},
    "furniture": {"label": "Flat-pack furniture assembly", "bookable": True,
                  "pattern": r"\bfurniture\b|\bflat[ -]?pack\b|\bassembly\b", "package": "furniture assembly",
                  "scope": "Assembly of the confirmed flat-pack chairs, tables or bookshelves using supplied instructions",
                  "exclusions": "Wardrobes, wall mounting, drilling, custom carpentry, missing parts and repairs are excluded; extra work requires a new quote and approval"},
    "mattress_cleaning": {"label":"Mattress cleaning", "bookable":True,
                          "pattern":r"\bmat{1,2}ress(?:es)?\b", "package":"mattress cleaning",
                          "scope":"Surface cleaning of the confirmed mattress size and quantity",
                          "exclusions":"Mould remediation, hazardous contamination, internal repairs and guaranteed stain or pest removal are excluded; extra work requires a new quote and approval"},
    "carpet_cleaning": {"label":"Synthetic carpet cleaning", "bookable":True,
                        "pattern":r"\bcarpets?\b|\brugs?\b", "package":"one carpet cleaning",
                        "scope":"Cleaning of one synthetic carpet with confirmed dimensions, up to 150 square feet",
                        "exclusions":"Wool, silk, fitted carpets, multiple rugs, hazardous waste and stain-removal guarantees are excluded; extra work requires a new quote and approval"},
    "refrigerator": {"label":"Refrigerator inspection", "bookable":True,
                     "pattern":r"\bfridge\b|\brefrigerator\b", "package":"refrigerator inspection",
                     "scope":"Inspection of one household refrigerator for the reported problem; diagnosis only",
                     "exclusions":"Parts, refrigerant, repairs, commercial equipment and food-safety certification are excluded; repairs need a new quote and approval"},
    "water_purifier": {"label":"Water-purifier servicing", "bookable":True,
                       "pattern":r"\bpurifier\b|\bwater[ -]?filter\b", "package":"water purifier servicing",
                       "scope":"Routine servicing of one household purifier: accessible exterior cleaning, visual filter-housing inspection and basic flow check",
                       "exclusions":"Filters, membranes, parts, installation, repairs and water-quality certification are excluded; extra work requires a new quote and approval"},
}

CATEGORIES={
    "cleaning":("cleaning","kitchen_cleaning","sofa_cleaning","mattress_cleaning","carpet_cleaning"),
    "appliances":("ac","washing_machine","refrigerator","water_purifier"),
    "repairs":("plumbing","electrical"),
    "assembly":("furniture",),
}

CLEANING_OFFERINGS={
    "p7":{"kitchen_cleaning":119900,"sofa_cleaning":24900},
    "p8":{"kitchen_cleaning":139900,"sofa_cleaning":29900},
    "p9":{"kitchen_cleaning":99900,"sofa_cleaning":19900},
}

EXTENDED_OFFERINGS={
    "p7":{"mattress_cleaning":49900,"carpet_cleaning":1500},
    "p8":{"mattress_cleaning":59900,"carpet_cleaning":1800},
    "p9":{"mattress_cleaning":39900,"carpet_cleaning":1200},
    "p13":{"refrigerator":49900,"water_purifier":69900},
    "p14":{"refrigerator":59900,"water_purifier":79900},
}


def detect_service(text):
    matches = [key for key, item in SERVICES.items()
               if re.search(item["pattern"], text, re.IGNORECASE)]
    specific=[key for key in matches if key in ("kitchen_cleaning","sofa_cleaning","washing_machine","mattress_cleaning","carpet_cleaning","refrigerator","water_purifier")]
    if len(specific)==1 and set(matches)<=set(specific+["cleaning"]):
        return specific[0]
    # Multiple categories need clarification rather than an arbitrary booking.
    if set(matches)=={"ac","cleaning"} and not re.search(r"\b(home|house|bathroom)\b",text,re.IGNORECASE):
        return "ac"
    return matches[0] if len(matches) == 1 else None


def unavailable_message(service):
    if isinstance(service,str) and service in SERVICES:
        return (f"{SERVICES[service]['label']} is planned, but has no onboarded demo providers yet. "
                "You can currently try AC servicing or plumbing in Indiranagar, Bengaluru.")
    return "Demo supports these services: "+", ".join(item["label"] for item in SERVICES.values())+"."


def catalogue_text(providers,category=None):
    lines=["### Services", "", "Fictional demo providers and test payments only.", ""]
    for key,item in SERVICES.items():
        if category and key not in CATEGORIES[category]: continue
        count=sum(key in provider_services(p) for p in providers)
        status=f"{count} demo providers; availability and credentials checked for your appointment" if count else "no providers in this demo database"
        lines.append(f"- **{item['label']}:** {status}.")
        lines.append(f"  Package: {item['scope']}.")
    lines.extend(["", "Demo area: Indiranagar, Bengaluru. Tell me the service, area, date, time and budget to begin."])
    return "\n".join(lines)


def package_from_text(service,text):
    low=text.casefold()
    if service=="cleaning" and re.search(r"\b(one|1|single)\s+bathroom\b",low):
        if not re.search(r"\b(two|three|whole.home|entire.home|2|3)\b",low):
            return SERVICES[service]["package"]
    if service=="electrical" and re.search(r"\b(electrical|electric|wiring|socket)\s+inspection\b",low):
        return SERVICES[service]["package"]
    if service=="kitchen_cleaning" and re.search(r"\b(one|1|single)\s+kitchen\b",low) and not re.search(r"\b(two|three|2|3)\b",low):
        return SERVICES[service]["package"]
    if service=="sofa_cleaning" and re.search(r"\b(sofa|couch)\b",low) and re.search(r"clean|shampoo",low):
        return SERVICES[service]["package"]
    if service=="washing_machine" and re.search(r"\binspection\b",low) and re.search(SERVICES[service]["pattern"],low):
        return SERVICES[service]["package"]
    if service=="furniture" and re.search(r"\bassembl\w*\b",low):
        return SERVICES[service]["package"]
    if service=="mattress_cleaning" and re.search(SERVICES[service]["pattern"],low) and re.search(r"clean|shampoo",low):
        return SERVICES[service]["package"]
    if service=="carpet_cleaning" and re.search(r"\b(one|1|single)\s+(?:carpet|rug)\b",low) and not re.search(r"\b(two|three|2|3)\s+(?:carpets|rugs)\b",low):
        return SERVICES[service]["package"]
    if service=="refrigerator" and re.search(r"\binspection\b",low) and re.search(SERVICES[service]["pattern"],low):
        return SERVICES[service]["package"]
    if service=="water_purifier" and re.search(SERVICES[service]["pattern"],low) and re.search(r"\bservic\w*\b|\bmaintenance\b",low):
        return SERVICES[service]["package"]
    return None


def provider_services(provider):
    return {provider["service"],*provider.get("offerings",{})}


def provider_amount(provider,service,details=None):
    if service not in provider_services(provider): raise ValueError("Provider does not offer this service")
    amount=provider.get("offerings",{}).get(service,provider["amount"])
    details=details or {}
    if service=="sofa_cleaning": return amount*details["seats"]
    if service=="furniture":
        unit={"chair":34900,"table":54900,"bookshelf":69900}[details["item"]]
        return (unit+provider.get("assembly_surcharge",0))*details["quantity"]
    if service=="mattress_cleaning":
        extra={"single":0,"double":20000,"queen":30000,"king":40000}[details["size"]]
        return (amount+extra)*details["quantity"]
    if service=="carpet_cleaning":
        area=Decimal(str(details["length_ft"]))*Decimal(str(details["width_ft"]))
        minimum={"p7":49900,"p8":59900,"p9":39900}.get(provider["id"],49900)
        return max(minimum,int((area*amount).quantize(Decimal("1"),rounding=ROUND_CEILING)))
    return amount


def quote_scope(service,details):
    scope=SERVICES[service]["scope"]
    if service=="sofa_cleaning": return f"Cleaning of {details['seats']} fabric sofa seats"
    if service=="washing_machine":
        return f"Inspection of one {details['machine_type']} household washing machine; reported problem: {details['issue']}. Diagnosis only"
    if service=="furniture":
        return f"Assembly of {details['quantity']} flat-pack {details['item']} item(s), with supplied instructions; no wall mounting"
    if service=="mattress_cleaning":
        return f"Surface cleaning of {details['quantity']} {details['size']}-size mattress(es)"
    if service=="carpet_cleaning":
        return f"Cleaning of one synthetic carpet, {details['length_ft']:g} by {details['width_ft']:g} feet"
    if service=="refrigerator":
        return f"Inspection of one {details['refrigerator_type']} household refrigerator; reported problem: {details['issue']}. Diagnosis only"
    if service=="water_purifier":
        return f"Servicing of one {details['purifier_type']} household purifier: exterior cleaning, visual filter-housing inspection and basic flow check; purpose: {details['issue']}"
    return scope
