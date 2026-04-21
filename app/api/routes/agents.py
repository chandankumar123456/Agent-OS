from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from uuid import uuid4
from datetime import datetime
from ...api.deps import get_current_user
from ...memory.long_term import agent_repo

router = APIRouter(prefix="/agents", tags=["agents"])


def _is_admin(user: object) -> bool:
    return getattr(user, "role", "user") == "admin"


class AgentConfig(BaseModel):
    name: str
    role: str
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048
    tools: List[str] = []


class AgentConfigResponse(BaseModel):
    agent_id: str
    name: str
    role: str
    status: str
    created_at: datetime
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048
    tools: List[str] = []


class AgentListResponse(BaseModel):
    agents: List[AgentConfigResponse]


def _to_response(agent_id: str, config: Dict[str, Any]) -> AgentConfigResponse:
    return AgentConfigResponse(
        agent_id=agent_id,
        name=config["name"],
        role=config["role"],
        status=config.get("status", "active"),
        created_at=config.get("created_at", datetime.utcnow()),
        system_prompt=config.get("system_prompt"),
        model=config.get("model"),
        temperature=config.get("temperature", 0.7),
        max_tokens=config.get("max_tokens", 2048),
        tools=config.get("tools", []),
    )


@router.get("", response_model=AgentListResponse)
async def list_agents(_: object = Depends(get_current_user)):
    agents = await agent_repo.list_all()
    return AgentListResponse(
        agents=[
            _to_response(agent.agent_key, {
                "name": agent.name,
                "role": agent.role,
                "status": agent.status,
                "created_at": agent.created_at,
                "system_prompt": agent.system_prompt,
                "model": agent.model,
                "temperature": agent.temperature,
                "max_tokens": agent.max_tokens,
                "tools": agent.tools or [],
            })
            for agent in agents
        ]
    )


@router.get("/{agent_id}", response_model=AgentConfigResponse)
async def get_agent(agent_id: str, _: object = Depends(get_current_user)):
    agent = await agent_repo.get_by_agent_key(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return _to_response(agent.agent_key, {
        "name": agent.name,
        "role": agent.role,
        "status": agent.status,
        "created_at": agent.created_at,
        "system_prompt": agent.system_prompt,
        "model": agent.model,
        "temperature": agent.temperature,
        "max_tokens": agent.max_tokens,
        "tools": agent.tools or [],
    })


@router.post("", response_model=AgentConfigResponse)
async def create_agent(config: AgentConfig, current_user: object = Depends(get_current_user)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Forbidden")
    agent_id = str(uuid4())
    await agent_repo.upsert(
        agent_key=agent_id,
        name=config.name,
        role=config.role,
        system_prompt=config.system_prompt,
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        tools=config.tools,
        status="active",
    )
    return _to_response(agent_id, {
        "name": config.name,
        "role": config.role,
        "status": "active",
        "created_at": datetime.utcnow(),
        "system_prompt": config.system_prompt,
        "model": config.model,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "tools": config.tools,
    })


@router.put("/{agent_id}", response_model=AgentConfigResponse)
async def update_agent(agent_id: str, config: AgentConfig, current_user: object = Depends(get_current_user)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Forbidden")
    await agent_repo.upsert(
        agent_key=agent_id,
        name=config.name,
        role=config.role,
        system_prompt=config.system_prompt,
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        tools=config.tools,
        status="active",
    )
    return _to_response(agent_id, {
        "name": config.name,
        "role": config.role,
        "status": "active",
        "created_at": datetime.utcnow(),
        "system_prompt": config.system_prompt,
        "model": config.model,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "tools": config.tools,
    })


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, current_user: object = Depends(get_current_user)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Forbidden")
    if agent_id in {"planner", "executor", "verifier"}:
        raise HTTPException(status_code=400, detail="Core agents cannot be deleted")
    deleted = await agent_repo.delete(agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"message": f"Agent {agent_id} deleted"}
