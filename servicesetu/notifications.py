"""Best-effort private reply notices; stored threads remain the source of truth."""
import asyncio
import copy
from uuid import UUID
from .communications import Messaging
from .cards import message_notice,chat_message


async def notify_customers(store,ctx):
    inbox=Messaging(store)
    for item in inbox.pending_notices():
        success=False
        try:
            customer,session=item['owner'].rsplit(':',1)
            context=copy.copy(ctx);context._session=UUID(session)
            result=await asyncio.wait_for(context.send(customer,chat_message(message_notice(item['booking']))),timeout=8)
            status=getattr(getattr(result,'status',None),'value',getattr(result,'status',None))
            success=status in ('sent','delivered')
        except Exception:pass
        inbox.notice_result(item['id'],success)
