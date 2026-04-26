from app.services.AgentServices import AgentServices

_agent_services: AgentServices | None = None

async def get_agent_services() -> AgentServices:
    global _agent_services
    if _agent_services is None:
        _agent_services = await AgentServices.create()
    return _agent_services