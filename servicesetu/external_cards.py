"""External discovery cards reuse the existing ACP envelope and schemas."""
from decimal import Decimal, InvalidOperation
from .cards import envelope
from .external_mcp import clean_text

TOMTOM_CREDIT = 'Location data © TomTom. Discovered businesses; not onboarded or verified by ServiceSetu.'
TASKRABBIT_LIMIT = 'Taskrabbit marketplace information only. No ServiceSetu reservation, booking or payment. Final price, availability and terms are set on Taskrabbit.'


def tomtom_results(rows, geocoding=False):
    title = 'TomTom location matches' if geocoding else 'Businesses discovered through TomTom'
    if not rows:
        return envelope(title + ': no matching results were returned in India. No demo providers were substituted.\n\n' + TOMTOM_CREDIT)
    items, lines = [], [title, TOMTOM_CREDIT]
    for row in rows:
        label = f"{row['name']}\n{row['address']}\nLongitude {row['position'][0]}, latitude {row['position'][1]}"
        lines.append(label)
        items.append({'id': row['id'], 'title': row['name'], 'subtitle': row['address'],
            'secondary_text': 'Location match' if geocoding else 'Discovered business · not onboarded',
            'badges': [{'label': 'TomTom data', 'variant': 'info'}]})
    return envelope('\n\n'.join(lines), 'carousel', {'title': title, 'subtitle': TOMTOM_CREDIT, 'items': items})


def route_result(result):
    rows = [('Origin', result['origin']), ('Destination', result['destination']),
        ('Estimated distance', f"{result['meters']/1000:.2f} km"),
        ('Estimated travel time', f"{result['seconds']/60:.1f} minutes"),
        ('Meaning', 'Route estimate only; not technician tracking, availability or dispatch')]
    return envelope('TomTom route estimate\n'+'\n'.join(f'{k}: {v}' for k,v in rows)+'\n'+TOMTOM_CREDIT,
        'detail', {'title': 'TomTom route estimate', 'summary_rows': [{'label': k, 'value': v} for k,v in rows]})


def price_text(pricing):
    if not isinstance(pricing, dict):
        return 'No price estimate returned.'
    currency = pricing.get('currency')
    value = pricing.get('averageHourlyRate')
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or not isinstance(currency, str) or len(currency) != 3:
            raise ValueError
    except (ValueError, InvalidOperation):
        return 'No usable currency-qualified price estimate returned.'
    unit = ' per hour' if pricing.get('type') == 'hourly' else ' (rate basis not confirmed)'
    return f'Indicative average rate: {currency.upper()} {amount:.2f}{unit}. This is not a fixed quote; fees, task size and Tasker rates can change the final total.'


def taskrabbit_input(service=''):
    return envelope('Taskrabbit assistance needs an explicitly requested country and location. The current MCP booking connector supports the US only; Taskrabbit is unavailable in India. Example: Taskrabbit furniture assembly in US 10001.', 'form', {
        'title': 'Taskrabbit location and service', 'fields': [
            {'name': 'service', 'kind': 'text', 'label': 'Service needed', 'required': True},
            {'name': 'country', 'kind': 'select', 'label': 'Country', 'required': True,
             'options': [{'value': 'IN', 'label': 'India'}, {'value': 'US', 'label': 'United States'}, {'value': 'GB', 'label': 'United Kingdom'}]},
            {'name': 'postal', 'kind': 'text', 'label': 'US ZIP code or provide city and state below', 'required': False},
            {'name': 'city', 'kind': 'text', 'label': 'City', 'required': False},
            {'name': 'state', 'kind': 'text', 'label': 'Two-letter US state', 'required': False}],
        'submit_cta': {'label': 'Check Taskrabbit availability', 'selection': {'action': 'taskrabbit_check'}}})


def taskrabbit_available(data, token):
    if data.get('citySupported') is False or data.get('available') is not True:
        return envelope('Taskrabbit did not report this service as available in the requested location. '+TASKRABBIT_LIMIT)
    text = f"Taskrabbit: {clean_text(data.get('serviceLabel'),160)}\n"+price_text(data.get('pricing'))+'\n'+TASKRABBIT_LIMIT
    text += '\nContinue with the returned scoping questions. No draft is created until you explicitly request the final link.'
    taskers = data.get('topTaskers') or []
    if taskers:
        items = []
        for n, tasker in enumerate(taskers[:3]):
            name = clean_text(tasker.get('displayName'),100)
            initials = clean_text(tasker.get('initials'),8)
            rating = clean_text(tasker.get('averageRating'),12)
            reviews = clean_text(tasker.get('reviewsCount'),12)
            description = clean_text(tasker.get('description'),400)
            text += f'\n\n{initials} · {name}\nTaskrabbit rating {rating}; {reviews} reviews\n{description}'
            items.append({'id': f'taskrabbit:{n}', 'title': f'{initials} · {name}',
                'subtitle': f'Taskrabbit rating {rating} · {reviews} reviews', 'secondary_text': description,
                'badges': [{'label': 'External Taskrabbit marketplace', 'variant': 'info'}],
                'primary_cta': {'label': 'Continue scoping', 'selection': {'action': 'taskrabbit_scope', 'external_token': token}}})
        return envelope(text, 'carousel', {'title': 'Taskrabbit suggestions · not reserved', 'items': items})
    return envelope(text, 'detail', {'title': 'Taskrabbit availability estimate',
        'summary_rows': [{'label': 'Estimate', 'value': price_text(data.get('pricing'))}],
        'ctas': [{'label': 'Continue scoping', 'selection': {'action': 'taskrabbit_scope', 'external_token': token}}]})


def scope_question(question, token):
    options = question.get('options') or []
    field = {'name': 'answer', 'kind': 'text', 'label': clean_text(question['question'],500), 'required': not question.get('optional',False)}
    if options and not any(o.get('acceptsUserInput') for o in options):
        field.update(kind='select', options=[{'value': str(o.get('value',o.get('id'))), 'label': clean_text(o.get('text',o.get('value')),120)} for o in options])
    return envelope(clean_text(question['question'],500)+'\n'+', '.join(clean_text(o.get('text',o.get('value')),120) for o in options)+
        '\nUse the form, or send task answer: followed by your answer. '+TASKRABBIT_LIMIT, 'form', {'title': 'Taskrabbit task details',
        'fields': [field], 'submit_cta': {'label': 'Save task answer', 'selection': {'action': 'taskrabbit_answer', 'external_token': token, 'question_param':question['param']}}})


def draft_review(pending):
    lines = ['Taskrabbit draft review', price_text(pending['availability'].get('pricing')),
        'Location: '+clean_text(pending['availability']['location']['address'],300)]
    lines.extend(clean_text(a['question'],300)+': '+clean_text(a['answer'],700) for a in pending['answers'])
    lines.append('Create draft and continue will send these details to Taskrabbit and create a draft link. You finish booking and payment on Taskrabbit. '+TASKRABBIT_LIMIT)
    return envelope('\n\n'.join(lines), 'detail', {'title': 'Review external Taskrabbit draft',
        'summary_rows': [{'label': 'Booking', 'value': 'External draft only; nothing reserved or paid'}],
        'ctas': [{'label': 'Create draft and continue on Taskrabbit',
                  'selection': {'action': 'taskrabbit_continue', 'external_token': pending['token']}}]})
