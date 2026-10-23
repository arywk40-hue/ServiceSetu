"""Best-effort private reply notices; stored threads remain the source of truth."""
import asyncio
import copy
from uuid import UUID
from .communications import Messaging
from .cards import message_notice,chat_message,booking_status


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


async def notify_bookings(store,ctx):
    """Durable payment/cancellation results go to the original ACP session."""
    with store.connect() as db:
        rows=db.execute('''SELECT n.event,n.booking,b.owner,e.kind FROM booking_notices n
          JOIN bookings b ON b.id=n.booking JOIN events e ON e.seq=n.event
          WHERE n.sent=0 AND n.attempts<20 AND n.next_attempt<=? ORDER BY n.event LIMIT 20''',(store.clock(),)).fetchall()
    for item in rows:
        success=False
        try:
            owner=item['owner'];customer,session=owner.rsplit(':',1)
            context=copy.copy(ctx);context._session=UUID(session)
            b=store.booking(item['booking'],owner)
            reply=booking_status(b,store.get_quote(b['quote'],owner))
            if item['kind']=='provider_cancelled':reply['text']='Your provider cancelled this booking. Review the payment status below. Send recover to find alternatives within the original constraints; every replacement needs fresh approval.\n\n'+reply['text']
            result=await asyncio.wait_for(context.send(customer,chat_message(reply)),timeout=8)
            status=getattr(getattr(result,'status',None),'value',getattr(result,'status',None))
            success=status in ('sent','delivered')
        except Exception:pass
        with store.tx() as db:
            db.execute('UPDATE booking_notices SET sent=?,attempts=attempts+1,next_attempt=? WHERE event=?',(int(success),store.clock()+30,item['event']))
