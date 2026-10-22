"""Service definitions shared by intake and quote construction."""
import re


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
}


def detect_service(text):
    matches = [key for key, item in SERVICES.items()
               if re.search(item["pattern"], text, re.IGNORECASE)]
    # Multiple categories need clarification rather than an arbitrary booking.
    if set(matches)=={"ac","cleaning"} and not re.search(r"\b(home|house|bathroom)\b",text,re.IGNORECASE):
        return "ac"
    return matches[0] if len(matches) == 1 else None


def unavailable_message(service):
    if isinstance(service,str) and service in SERVICES:
        return (f"{SERVICES[service]['label']} is planned, but has no onboarded demo providers yet. "
                "You can currently try AC servicing or plumbing in Indiranagar, Bengaluru.")
    return "Demo supports AC servicing, plumbing, bathroom cleaning and electrical inspection only."


def catalogue_text(providers):
    lines=["### Services", "", "Fictional demo providers and test payments only.", ""]
    for key,item in SERVICES.items():
        count=sum(p["service"]==key for p in providers)
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
    return None
