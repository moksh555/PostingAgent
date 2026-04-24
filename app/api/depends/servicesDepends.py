from app.services.AgentServices import AgentServices
import functools

@functools.lru_cache(maxsize=1)
def get_agent_services() -> AgentServices:
    return AgentServices()