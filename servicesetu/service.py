"""Typed role boundary shared by local proofs and real uAgent messages."""
import asyncio
from .core import Rejected
from .payments import Payments


class Services:
    def __init__(self,store,payment_mode=None):
        self.store=store
        self.payments=Payments(store,payment_mode)

    def execute(self,role,action,owner,data):
        s=self.store
        if role=="matching" and action=="availability":
            return {"options":s.available_slots(data["job"])}
        if role=="matching" and action=="match":
            choices,excluded=s.match(data["job"])
            return {"providers":[p["id"] for p in choices],"excluded":excluded}
        if role=="verification" and action=="check":
            return s.trust(s.provider(data["provider"]),data["slot"])
        if role.startswith("provider:") and action=="quote":
            return s.quote(owner,role.split(":",1)[1],data["slot"],data.get("previous"),job=data.get("job"))
        if role=="booking":
            if action=="request": return s.request(owner,data["job"])
            if action=="hold": return s.hold(owner,data["quote"],data.get("recovery_of"),data.get("request_id"))
            if action=="approve":
                s.approve(owner,data["booking"],data["quote"])
                return s.booking(data["booking"],owner)
            if action=="status": return s.booking(data["booking"],owner)
            if action=="timeline": return {"events":s.timeline(owner,data["booking"])}
            if action=="complete":
                s.complete(owner,data["booking"])
                return s.booking(data["booking"],owner)
        if role=="payment":
            if action=="start": return self.payments.start(owner,data["booking"])
            if action=="commit": return self.payments.commit(owner,data["booking"],data["transaction"],data["currency"],data["amount"],data["recipient"],data["expected_recipient"])
            if action=="cancel": return self.payments.cancel(owner,data["booking"],data.get("actor","customer"))
        if role=="recovery" and action=="alternatives":
            choices,excluded=s.recovery(owner,data["booking"],data["job"])
            return {"providers":[p["id"] for p in choices],"excluded":excluded}
        raise Rejected("Action requires human review or is outside this agent's authority")


class LocalBus:
    """Offline adapter, explicitly not an Agentverse deployment."""
    def __init__(self,services):
        self.services=services
        self.calls=[]

    async def call(self,role,action,owner,**data):
        self.calls.append({"role":role,"action":action})
        return await asyncio.to_thread(self.services.execute,role,action,owner,data)
