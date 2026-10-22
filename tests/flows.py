"""Synthetic customer steps shared by lifecycle tests."""
import json

async def with_address(conversation, owner, text, bus):
    reply=await conversation.handle(owner,text,bus)
    payload=json.loads(reply.get('metadata',{}).get('card_payload','{}'))
    choice=next((item['selection'] for item in payload.get('ctas',[]) if item.get('selection',{}).get('action')=='open_quote_address'),None)
    if choice:
        reply=await conversation.handle(owner,json.dumps(choice),bus)
        payload=json.loads(reply['metadata']['card_payload'])
    picked=payload.get('submit_cta',{}).get('selection',{})
    if picked.get('action')=='set_address':
        reply=await conversation.handle(owner,json.dumps(dict(picked,address_line='Flat 12, Demo House, Example Road')),bus)
    return reply
