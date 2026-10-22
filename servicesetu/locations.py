"""Conservative location normalization; possible typos require confirmation."""
import re
import unicodedata
from difflib import SequenceMatcher

ALIASES = {
    "city": {"bengaluru":"bengaluru", "bangalore":"bengaluru"},
    "area": {"indiranagar":"indiranagar"},
}


def compact(value):
    if not isinstance(value, str): return ""
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", value).casefold())


def canonical(value, field):
    return ALIASES[field].get(compact(value))


def suggestion(value, field):
    word = compact(value)
    if len(word) < 6: return None
    matches = {target for alias,target in ALIASES[field].items()
               if abs(len(word)-len(alias)) <= 2 and SequenceMatcher(None,word,alias).ratio() >= 0.86}
    return next(iter(matches)) if len(matches) == 1 else None


def mentions(text):
    """Preserve explicit supported names and likely typos before model cleanup."""
    words = re.findall(r"[^\W\d_]+", text.casefold(), re.UNICODE)
    found = {}
    for field in ALIASES:
        exact, possible = None, None
        for size in (1,2):
            for index in range(len(words)-size+1):
                if any(w in ("not","no","outside","except") for w in words[max(0,index-2):index]):
                    continue
                phrase = " ".join(words[index:index+size])
                if canonical(phrase,field): exact = phrase
                elif size == 1 and suggestion(phrase,field): possible = phrase
        if exact or possible: found[field] = exact or possible
    return found


def clean_context(partial):
    result = dict(partial)
    for field in ALIASES:
        result[field] = canonical(result.get(field),field)
    return result


def location_only(text):
    """A named-place correction must not re-extract numeric request terms."""
    if re.search(r"\d|[₹$]",text): return False
    words = re.findall(r"[^\W\d_]+", text.casefold(), re.UNICODE)
    covered = set()
    for index in range(len(words)):
        for size in (1,2):
            phrase = " ".join(words[index:index+size])
            if any(canonical(phrase,field) or suggestion(phrase,field) for field in ALIASES):
                covered.update(range(index,min(index+size,len(words))))
    fillers = {"actually","i","mean","meant","my","location","area","city","is",
               "in","at","it","its","the","correct","sorry","please","change","to","and"}
    return bool(covered) and all(index in covered or word in fillers for index,word in enumerate(words))


def resolve(partial, text=""):
    result = dict(partial)
    result.update(mentions(text))
    pending = {}
    unsupported = False
    for field in ALIASES:
        value = result.get(field)
        exact = canonical(value,field)
        if value and not exact:
            candidate = suggestion(value,field)
            if candidate: pending[field] = candidate
            else: unsupported = True
        result[field] = exact
    # An area-only correction must not inherit an unsupported old city.
    if (result.get("area") or pending.get("area")) == "indiranagar" and not (result.get("city") or pending.get("city")) and not unsupported:
        pending.setdefault("city","bengaluru")
    if pending:
        proposal = {field:result[field] for field in ALIASES if result.get(field)}
        proposal.update(pending)
        return result, proposal, unsupported
    return result, None, unsupported
