from fastapi import APIRouter, HTTPException, Depends
from ...agents.v2.registry import agent_registry_v2
from ...agents.v2.schemas import AgentConfigV2
from ...api.deps import get_current_user
from ...logs.logger import logger

router = APIRouter(prefix="/agents/v2", tags=["agents-v2"])

BUILT_IN_TEMPLATES = [
    {
        "id": "researcher",
        "name": "Research Agent",
        "config": AgentConfigV2(
            agent_id="template_researcher",
            name="Research Agent",
            role="researcher",
            goal="Uncover cutting-edge developments in any topic",
            backstory="You're a seasoned researcher with a knack for uncovering the latest developments.",
            model="gpt-4o",
            temperature=0.3,
            tools=[{"tool_name": "web_search"}, {"tool_name": "text_processor"}],
        ).model_dump(),
    },
    {
        "id": "coder",
        "name": "Code Agent",
        "config": AgentConfigV2(
            agent_id="template_coder",
            name="Code Agent",
            role="coder",
            goal="Write and debug code efficiently",
            backstory="Expert software engineer with 10 years of experience.",
            model="gpt-4o",
            temperature=0.1,
            tools=[{"tool_name": "shell"}],
        ).model_dump(),
    },
    {
        "id": "creative",
        "name": "Creative Writer",
        "config": AgentConfigV2(
            agent_id="template_creative",
            name="Creative Writer",
            role="creative",
            goal="Create compelling creative content",
            backstory="Award-winning creative writer with a unique voice.",
            model="gpt-4o",
            temperature=0.9,
            tools=[{"tool_name": "text_processor"}],
        ).model_dump(),
    },
]

@router.get("/templates")
async def list_templates(_: object = Depends(get_current_user)):
    return {"templates": BUILT_IN_TEMPLATES}

@router.get("")
async def list_agents(_: object = Depends(get_current_user)):
    agents = await agent_registry_v2.list_all()
    return {"agents": [a.model_dump() for a in agents]}

@router.post("")
async def create_agent(config: AgentConfigV2, current_user: object = Depends(get_current_user)):
    result = await agent_registry_v2.register(config)
    logger.info(f"User {getattr(current_user, 'id', 'unknown')} created agent v2 {config.agent_id}")
    return {"agent": result.model_dump()}

@router.get("/{agent_id}")
async def get_agent(agent_id: str, _: object = Depends(get_current_user)):
    agent = await agent_registry_v2.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"agent": agent.model_dump()}

@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, current_user: object = Depends(get_current_user)):
    deleted = await agent_registry_v2.delete(agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    logger.info(f"User {getattr(current_user, 'id', 'unknown')} deleted agent v2 {agent_id}")
    return {"message": f"Agent {agent_id} deleted"}
