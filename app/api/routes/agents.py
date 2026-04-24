from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from uuid import uuid4
from datetime import datetime
from ...api.deps import get_current_user
from ...memory.long_term import agent_repo
from ...logs.logger import logger

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentConfig(BaseModel):
    name: str
    role: str
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048
    tools: List[str] = []
    version: Optional[str] = "1.0.0"


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
    version: Optional[str] = "1.0.0"


class AgentVersionResponse(BaseModel):
    version: str
    name: str
    role: str
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048
    tools: List[str] = []
    created_at: datetime


class AgentVersionListResponse(BaseModel):
    versions: List[AgentVersionResponse]


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
        version=config.get("version", "1.0.0"),
    )


def _to_version_response(version_row) -> AgentVersionResponse:
    return AgentVersionResponse(
        version=version_row.version,
        name=version_row.name,
        role=version_row.role,
        system_prompt=version_row.system_prompt,
        model=version_row.model,
        temperature=version_row.temperature,
        max_tokens=version_row.max_tokens,
        tools=version_row.tools or [],
        created_at=version_row.created_at,
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
        version=config.version,
        status="active",
    )
    logger.info(f"User {getattr(current_user, 'id', 'unknown')} created agent {agent_id}")
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
        "version": config.version,
    })


@router.put("/{agent_id}", response_model=AgentConfigResponse)
async def update_agent(agent_id: str, config: AgentConfig, current_user: object = Depends(get_current_user)):
    await agent_repo.upsert(
        agent_key=agent_id,
        name=config.name,
        role=config.role,
        system_prompt=config.system_prompt,
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        tools=config.tools,
        version=config.version,
        status="active",
    )
    logger.info(f"User {getattr(current_user, 'id', 'unknown')} updated agent {agent_id}")
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
        "version": config.version,
    })


@router.get("/{agent_id}/versions", response_model=AgentVersionListResponse)
async def list_agent_versions(agent_id: str, _: object = Depends(get_current_user)):
    agent = await agent_repo.get_by_agent_key(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    versions = await agent_repo.list_versions(agent_id)
    return AgentVersionListResponse(versions=[_to_version_response(v) for v in versions])


@router.post("/{agent_id}/versions", response_model=AgentVersionResponse)
async def create_agent_version(agent_id: str, config: AgentConfig, current_user: object = Depends(get_current_user)):
    agent = await agent_repo.get_by_agent_key(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    version = config.version or f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    try:
        v = await agent_repo.create_version(
            agent_key=agent_id,
            version=version,
            name=config.name or agent.name,
            role=config.role or agent.role,
            system_prompt=config.system_prompt or agent.system_prompt,
            model=config.model or agent.model,
            temperature=config.temperature if config.temperature is not None else agent.temperature,
            max_tokens=config.max_tokens if config.max_tokens is not None else agent.max_tokens,
            tools=config.tools if config.tools else agent.tools,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    logger.info(f"User {getattr(current_user, 'id', 'unknown')} created version {version} for agent {agent_id}")
    return _to_version_response(v)


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, current_user: object = Depends(get_current_user)):
    if agent_id in {"planner", "executor", "verifier", "core_planner", "core_executor", "core_verifier"}:
        raise HTTPException(status_code=400, detail="Core agents cannot be deleted")
    deleted = await agent_repo.delete(agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    logger.info(f"User {getattr(current_user, 'id', 'unknown')} deleted agent {agent_id}")
    return {"message": f"Agent {agent_id} deleted"}
