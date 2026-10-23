"""External paths never call ServiceSetu matching, booking, or payment mutations."""
import re
import secrets
import json
from . import cards
from . import external_cards as render
from .discovery import TomTom, Taskrabbit
from .external_mcp import ExternalError, clean_text


class ExternalConversation:
    def __init__(self, store, tomtom=None, taskrabbit=None):
        self.store = store
        self.tomtom = tomtom or TomTom()
        self.taskrabbit = taskrabbit or Taskrabbit()

    def pending(self, state, picked):
        pending = state.get('taskrabbit_request')
        if (not pending or picked.get('external_token') != pending['token']
                or pending['deadline'] <= self.store.clock()):
            raise ExternalError('ownership', 'Use the latest Taskrabbit review in this same conversation; expired requests need a fresh availability check.')
        return pending

    def claim_draft(self, owner, token):
        with self.store.tx() as db:
            row=db.execute('SELECT payload FROM sessions WHERE id=?',(owner,)).fetchone()
            saved=json.loads(row['payload']) if row else {}
            request=saved.get('taskrabbit_request') or {}
            if request.get('token')!=token or request.get('phase')!='review' or request.get('deadline',0)<=self.store.clock():
                raise ExternalError('retry','This Taskrabbit draft was already requested or expired. No duplicate draft will be created.')
            request['phase']='started'
            db.execute('UPDATE sessions SET payload=? WHERE id=?',(json.dumps(saved),owner))

    async def handle(self, owner, text, picked, state):
        action = picked.get('action', '')
        try:
            route = re.fullmatch(r'(?:tomtom\s+)?route\s+from\s+(.+?)\s+to\s+(.+)', text.strip(), re.I)
            geocode = re.fullmatch(r'(?:tomtom\s+)?geocode\s+(.+)', text.strip(), re.I)
            search = re.fullmatch(r'tomtom\s+(?:find\s+|search\s+)?(.+?)\s+in\s+(.+)', text.strip(), re.I)
            if action == 'tomtom_route' or route:
                origin, destination = (picked.get('origin'), picked.get('destination')) if action else route.groups()
                return render.route_result(await self.tomtom.route(origin, destination, owner))
            if action == 'tomtom_geocode' or geocode:
                return render.tomtom_results(await self.tomtom.geocode(picked.get('query') if action else geocode[1], owner), True)
            if action == 'tomtom_search' or search:
                service, location = (picked.get('service'), picked.get('location')) if action else search.groups()
                return render.tomtom_results(await self.tomtom.search(service, location, owner))
            task_prompt = re.match(r'^taskrabbit\b\s*(.*)', text.strip(), re.I)
            if action == 'taskrabbit_check' or (task_prompt and not action):
                if action:
                    args = {k: str(picked.get(k) or '').strip() for k in ('service','country','postal','city','state')}
                else:
                    rest = task_prompt[1]
                    if re.search(r'\b(india|mandi|bengaluru|bangalore|mumbai|delhi)\b|\b\d{6}\b',rest,re.I):
                        raise ExternalError('geography', 'Taskrabbit is unavailable in India. For local discovery, try TomTom plumbers in Mandi, Himachal Pradesh or TomTom repair shops in Bengaluru. No overseas location has been substituted.')
                    match = re.fullmatch(r'(.+?)\s+in\s+(?:US|USA|United States)\s+(\d{5})',rest,re.I)
                    if not match:
                        return render.taskrabbit_input()
                    args = {'service': match[1], 'country': 'US', 'postal': match[2]}
                # Check geography before any remote call; explicit customer country is required.
                self.taskrabbit.location(args.get('country'),args.get('postal',''),args.get('city',''),args.get('state',''))
                state.pop('taskrabbit_request',None)
                self.store.save_session(owner,state)
                if args['service'].lower() in ('services','list services','supported services'):
                    data = await self.taskrabbit.services(**{k:v for k,v in args.items() if k!='service'},owner=owner)
                    labels = [clean_text(s.get('label'),100) for s in data.get('services',[])[:60] if isinstance(s,dict)]
                    return cards.envelope('Taskrabbit services in the requested US location:\n'+('\n'.join(labels) if data.get('citySupported') is True else 'This location is not supported.')+'\n'+render.TASKRABBIT_LIMIT)
                data = await self.taskrabbit.check(**args,owner=owner)
                if data.get('available') is True and data.get('citySupported') is not False:
                    questions = data['scopingQuestions']
                    if (len(questions)>12 or any(not isinstance(q,dict) or not isinstance(q.get('question'),str) or not q.get('param') for q in questions)):
                        raise ExternalError('schema','Taskrabbit returned unsupported scoping questions.')
                    state['taskrabbit_request'] = {'token': 'ext_'+secrets.token_hex(16),
                        'deadline': self.store.clock()+600, 'availability': {k:data[k] for k in ('available','categoryId','location','pricing','scopingQuestions') if k in data},
                        'answers': [], 'phase': 'questions'}
                    self.store.save_session(owner,state)
                return render.taskrabbit_available(data,state.get('taskrabbit_request',{}).get('token',''))
            if action in ('taskrabbit_scope','taskrabbit_answer','taskrabbit_continue'):
                pending = self.pending(state,picked)
                if pending.get('url'):
                    return cards.envelope('[Continue booking on Taskrabbit]('+pending['url']+')\n'+render.TASKRABBIT_LIMIT)
                if pending.get('phase') == 'started':
                    raise ExternalError('unknown','The draft request is awaiting an outcome. It will not be sent again automatically. Check Taskrabbit directly; no ServiceSetu booking or payment was created.')
                questions = pending['availability']['scopingQuestions']
                if action == 'taskrabbit_answer':
                    index = len(pending['answers'])
                    if index >= len(questions):
                        return render.draft_review(pending)
                    question = questions[index]
                    if picked.get('question_param')!=question['param']:
                        raise ExternalError('stale','This answer belongs to an older Taskrabbit question. Use the latest question card.')
                    answer = str(picked.get('answer') or '').strip()
                    options = question.get('options') or []
                    if not answer and not question.get('optional'):
                        return render.scope_question(question,pending['token'])
                    if options and not any(o.get('acceptsUserInput') for o in options):
                        allowed = {str(o.get('value',o.get('id'))).lower(): str(o.get('value',o.get('id'))) for o in options}
                        if answer.lower() not in allowed:
                            return render.scope_question(question,pending['token'])
                        answer = allowed[answer.lower()]
                    if len(answer)>1000:
                        raise ExternalError('input','Keep this task answer under 1000 characters.')
                    pending['answers'].append({'question': question['question'], 'param': question['param'], 'answer': answer})
                    self.store.save_session(owner,state)
                if action == 'taskrabbit_continue':
                    if len(pending['answers']) != len(questions) or not any(a['param']=='job_size' and a['answer'] for a in pending['answers']):
                        raise ExternalError('scoping','Complete the returned task questions, including task size, before creating a draft link.')
                    if pending['phase'] != 'review':
                        raise ExternalError('approval','Review the exact draft details before continuing on Taskrabbit.')
                    self.claim_draft(owner,pending['token'])
                    pending['phase'] = 'started'
                    pending['url'] = await self.taskrabbit.deep_link(pending['availability'],pending['answers'],owner)
                    pending['phase'] = 'linked'
                    self.store.save_session(owner,state)
                    return cards.envelope('[Continue booking on Taskrabbit]('+pending['url']+')\n'+render.TASKRABBIT_LIMIT)
                index = len(pending['answers'])
                if index < len(questions):
                    return render.scope_question(questions[index],pending['token'])
                pending['phase'] = 'review'
                self.store.save_session(owner,state)
                return render.draft_review(pending)
            pending = state.get('taskrabbit_request')
            if pending and pending.get('phase') == 'questions' and not action:
                # Explicit prefix keeps normal booking commands and new requests available.
                answer = re.fullmatch(r'task answer\s*:\s*(.+)',text,re.I|re.S)
                if answer:
                    index=len(pending['answers'])
                    questions=pending['availability']['scopingQuestions']
                    if index<len(questions):
                        return await self.handle(owner,text,{'action':'taskrabbit_answer','external_token':pending['token'],'question_param':questions[index]['param'],'answer':answer[1]},state)
            if action.startswith(('tomtom_','taskrabbit_')):
                raise ExternalError('action','Use the current external discovery or Taskrabbit card.')
            return None
        except ExternalError as error:
            return cards.envelope(clean_text(str(error),900)+'\n\nNo ServiceSetu booking or payment was created. Onboarded providers and fictional demo providers remain separate from external discovery.')
