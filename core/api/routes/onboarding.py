from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List
from ...api.deps import get_current_user
from ...memory.long_term import db
from ...memory.models import UserOnboardingState
from ...onboarding.seeder import seed_example_data
from sqlalchemy import select
from ...logs.logger import logger

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

class OnboardingStateResponse(BaseModel):
    has_completed_tour: bool
    has_created_first_task: bool
    has_created_first_agent: bool
    has_created_first_workflow: bool
    dismissed_prompts: List[str]
    onboarding_complete: bool

async def _get_or_create_state(user_id: str) -> UserOnboardingState:
    async with db.get_session() as session:
        result = await session.execute(select(UserOnboardingState).where(UserOnboardingState.user_id == user_id))
        state = result.scalar_one_or_none()
        if not state:
            state = UserOnboardingState(user_id=user_id)
            session.add(state)
            await session.commit()
        return state

@router.get("/state", response_model=OnboardingStateResponse)
async def get_onboarding_state(current_user: object = Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", ""))
    state = await _get_or_create_state(user_id)
    return OnboardingStateResponse(
        has_completed_tour=state.has_completed_tour,
        has_created_first_task=state.has_created_first_task,
        has_created_first_agent=state.has_created_first_agent,
        has_created_first_workflow=state.has_created_first_workflow,
        dismissed_prompts=state.dismissed_prompts or [],
        onboarding_complete=state.has_completed_tour and (state.has_created_first_task or state.has_created_first_agent or state.has_created_first_workflow),
    )

@router.post("/complete/{step}")
async def complete_step(step: str, current_user: object = Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", ""))
    state = await _get_or_create_state(user_id)
    async with db.get_session() as session:
        if step == "tour":
            state.has_completed_tour = True
        elif step == "first_task":
            state.has_created_first_task = True
        elif step == "first_agent":
            state.has_created_first_agent = True
        elif step == "first_workflow":
            state.has_created_first_workflow = True
        await session.commit()
    logger.info(f"User {user_id} completed onboarding step: {step}")
    return {"success": True}

@router.post("/seed")
async def seed_data(current_user: object = Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", ""))
    await seed_example_data(user_id)
    return {"success": True}
