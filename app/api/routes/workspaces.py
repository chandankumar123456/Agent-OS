from fastapi import APIRouter, HTTPException, Depends
from typing import List
from pydantic import BaseModel
from uuid import uuid4
from ...auth.rbac import require_role, Role
from ...api.deps import get_current_user
from ...memory.long_term import db
from ...memory.models import WorkspaceModel, WorkspaceMemberModel
from ...logs.logger import logger
from sqlalchemy import select

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class WorkspaceCreate(BaseModel):
    name: str


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    owner_id: str
    created_at: str


class MemberAddRequest(BaseModel):
    user_id: str
    role: str = "member"


class MemberResponse(BaseModel):
    id: str
    workspace_id: str
    user_id: str
    role: str
    joined_at: str


@router.post("", response_model=WorkspaceResponse)
async def create_workspace(
    request: WorkspaceCreate,
    current_user = Depends(require_role(Role.admin))
):
    ws = WorkspaceModel(id=str(uuid4()), name=request.name, owner_id=str(current_user.id))
    async with db.get_session() as session:
        session.add(ws)
        await session.commit()
        await session.refresh(ws)
    logger.info(f"Workspace created: {ws.id} by user {current_user.id}")
    return WorkspaceResponse(
        id=ws.id,
        name=ws.name,
        owner_id=ws.owner_id,
        created_at=ws.created_at.isoformat() if ws.created_at else ""
    )


@router.get("", response_model=List[WorkspaceResponse])
async def list_workspaces(current_user = Depends(get_current_user)):
    user_id = str(current_user.id)
    async with db.get_session() as session:
        result = await session.execute(select(WorkspaceModel).where(WorkspaceModel.owner_id == user_id))
        owned = result.scalars().all()

        result2 = await session.execute(select(WorkspaceMemberModel).where(WorkspaceMemberModel.user_id == user_id))
        memberships = result2.scalars().all()
        workspace_ids = [m.workspace_id for m in memberships]

        if workspace_ids:
            result3 = await session.execute(select(WorkspaceModel).where(WorkspaceModel.id.in_(workspace_ids)))
            member_ws = result3.scalars().all()
        else:
            member_ws = []

        owned_ids = {o.id for o in owned}
        all_ws = list(owned) + [w for w in member_ws if w.id not in owned_ids]

        return [
            WorkspaceResponse(
                id=w.id,
                name=w.name,
                owner_id=w.owner_id,
                created_at=w.created_at.isoformat() if w.created_at else ""
            )
            for w in all_ws
        ]


@router.post("/{workspace_id}/members", response_model=MemberResponse)
async def add_member(
    workspace_id: str,
    request: MemberAddRequest,
    current_user = Depends(get_current_user)
):
    async with db.get_session() as session:
        ws = await session.execute(select(WorkspaceModel).where(WorkspaceModel.id == workspace_id))
        workspace = ws.scalar_one_or_none()
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")
        if workspace.owner_id != str(current_user.id):
            raise HTTPException(status_code=403, detail="Only workspace owner can add members")

        existing = await session.execute(
            select(WorkspaceMemberModel)
            .where(WorkspaceMemberModel.workspace_id == workspace_id)
            .where(WorkspaceMemberModel.user_id == request.user_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="User is already a member")

        member = WorkspaceMemberModel(
            workspace_id=workspace_id,
            user_id=request.user_id,
            role=request.role
        )
        session.add(member)
        await session.commit()
        await session.refresh(member)

    return MemberResponse(
        id=member.id,
        workspace_id=member.workspace_id,
        user_id=member.user_id,
        role=member.role,
        joined_at=member.joined_at.isoformat() if member.joined_at else ""
    )


@router.get("/{workspace_id}/members", response_model=List[MemberResponse])
async def list_members(workspace_id: str, current_user = Depends(get_current_user)):
    async with db.get_session() as session:
        ws = await session.execute(select(WorkspaceModel).where(WorkspaceModel.id == workspace_id))
        workspace = ws.scalar_one_or_none()
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        is_owner = workspace.owner_id == str(current_user.id)
        is_member = False
        if not is_owner:
            membership = await session.execute(
                select(WorkspaceMemberModel)
                .where(WorkspaceMemberModel.workspace_id == workspace_id)
                .where(WorkspaceMemberModel.user_id == str(current_user.id))
            )
            is_member = membership.scalar_one_or_none() is not None

        if not is_owner and not is_member:
            raise HTTPException(status_code=403, detail="Access denied")

        result = await session.execute(select(WorkspaceMemberModel).where(WorkspaceMemberModel.workspace_id == workspace_id))
        members = result.scalars().all()

        return [
            MemberResponse(
                id=m.id,
                workspace_id=m.workspace_id,
                user_id=m.user_id,
                role=m.role,
                joined_at=m.joined_at.isoformat() if m.joined_at else ""
            )
            for m in members
        ]


@router.delete("/{workspace_id}/members/{user_id}")
async def remove_member(
    workspace_id: str,
    user_id: str,
    current_user = Depends(get_current_user)
):
    async with db.get_session() as session:
        ws = await session.execute(select(WorkspaceModel).where(WorkspaceModel.id == workspace_id))
        workspace = ws.scalar_one_or_none()
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")
        if workspace.owner_id != str(current_user.id):
            raise HTTPException(status_code=403, detail="Only workspace owner can remove members")

        result = await session.execute(
            select(WorkspaceMemberModel)
            .where(WorkspaceMemberModel.workspace_id == workspace_id)
            .where(WorkspaceMemberModel.user_id == user_id)
        )
        member = result.scalar_one_or_none()
        if not member:
            raise HTTPException(status_code=404, detail="Member not found")

        await session.delete(member)
        await session.commit()

    return {"success": True}
