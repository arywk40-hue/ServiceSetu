"""Bounded retries for transient Agentverse destination-resolution failures."""
import asyncio


def delivered(result):
    status=getattr(getattr(result,'status',None),'value',getattr(result,'status',None))
    return status in ('sent','delivered')


async def send_customer(ctx,customer,message):
    # Keep the ChatMessage msg_id identical across delivery retries. Never retry
    # the booking/payment operation merely because a response could not be sent.
    result=None
    for attempt in range(3):
        try:result=await ctx.send(customer,message)
        except Exception:result=None
        if delivered(result):return result
        if attempt<2:await asyncio.sleep(0.5*(attempt+1))
    return result
