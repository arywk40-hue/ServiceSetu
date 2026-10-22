"""Fail-closed provider coverage; no postal or geocoding API is implied."""
from .locations import canonical,country_code,pin_code


def regions(provider):
    if 'coverage' in provider:
        value=provider['coverage']
        return value if isinstance(value,list) else []
    # Compatibility for the original seeded locality. This is not nationwide coverage.
    pins=['560038'] if canonical(provider.get('city'),'city')=='bengaluru' and canonical(provider.get('area'),'area')=='indiranagar' else []
    return [{'country':provider.get('country','IN'),'city':provider.get('city'),'areas':[provider.get('area')],
             'pincodes':provider.get('pincodes',pins),'legacy_locality':True}]


def covers(provider,job):
    city,area=canonical(job.get('city'),'city'),canonical(job.get('area'),'area')
    if not city or not area or country_code(job.get('country'))!='IN':return False
    pin=pin_code(job.get('pincode')) if job.get('pincode') is not None else None
    if job.get('pincode') is not None and pin is None:return False
    for region in regions(provider):
        if not isinstance(region,dict) or country_code(region.get('country'))!='IN':continue
        if canonical(region.get('city'),'city')!=city:continue
        areas=region.get('areas',[]);pins=region.get('pincodes',[])
        if not isinstance(areas,list) or not isinstance(pins,list):continue
        if any(not isinstance(value,str) or canonical(value,'area') is None for value in areas):continue
        if any(type(value) not in (str,int) or pin_code(value) is None for value in pins):continue
        allowed_areas={canonical(value,'area') for value in areas if isinstance(value,str)}-{None}
        allowed_pins={pin_code(value) for value in pins if type(value) in (str,int)}-{None}
        if not allowed_areas and not allowed_pins:continue
        if allowed_areas and area not in allowed_areas:continue
        if pin:
            if not allowed_pins or pin not in allowed_pins:continue
        elif allowed_pins and not allowed_areas and not region.get('legacy_locality'):continue
        return True
    return False


def requires_pin(job,providers):
    if job.get('pincode') or not job.get('city') or not job.get('area'):return False
    if any(covers(provider,job) for provider in providers):return False
    return any(isinstance(region,dict) and canonical(region.get('city'),'city')==canonical(job['city'],'city')
               and region.get('pincodes') and not region.get('areas')
               for provider in providers for region in regions(provider))


def location_label(location):
    if not location:return ''
    text=', '.join(str(location[field]).title() for field in ('area','city') if location.get(field))
    if location.get('pincode'):text+=' · PIN '+str(location['pincode'])
    return text


def location_key(location):
    return (country_code(location.get('country')),canonical(location.get('city'),'city'),
            canonical(location.get('area'),'area'),pin_code(location.get('pincode')))


DEMO_REGIONS=[
    {'country':'IN','city':'bengaluru','areas':['indiranagar'],'pincodes':['560038'],'legacy_locality':True},
    {'country':'IN','city':'mumbai','areas':['powai'],'pincodes':['400076']},
]
