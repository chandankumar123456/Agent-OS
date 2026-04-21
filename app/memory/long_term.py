from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from datetime import datetime
from typing import Optional, Dict, Any, List
from types import SimpleNamespace
from .models import Base, TaskModel, StepModel, ContextModel, MessageModel, UserModel
from ..config.settings import settings
from ..logs.logger import logger

DATABASE_URL = settings.DATABASE_URL or "postgresql+asyncpg://agentos:agentos@localhost:5432/agentos"

_MEMORY_TASKS: Dict[str, Any] = {}
_MEMORY_STEPS: Dict[str, Any] = {}
_MEMORY_USERS: Dict[str, Any] = {}


def _memory_row(**kwargs):
    return SimpleNamespace(**kwargs)


class Database:
    def __init__(self):
        self.engine = None
        self.session_factory = None
    
    async def connect(self):
        try:
            self.engine = create_async_engine(DATABASE_URL, echo=False)
            self.session_factory = sessionmaker(
                self.engine, class_=AsyncSession, expire_on_commit=False
            )
            
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            logger.info("Database connected")
        except Exception as e:
            self.engine = None
            self.session_factory = None
            logger.warning(f"Database unavailable, using in-memory fallback: {e}")
    
    async def disconnect(self):
        if self.engine:
            await self.engine.dispose()
            logger.info("Database disconnected")
    
    def get_session(self) -> AsyncSession:
        return self.session_factory()


db = Database()


class TaskRepository:
    async def create(
        self,
        task_id: str,
        query: str,
        status: str = "pending"
    ) -> TaskModel:
        if not db.session_factory:
            task = _memory_row(
                id=task_id,
                query=query,
                status=status,
                result=None,
                error=None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            _MEMORY_TASKS[task_id] = task
            return task

        async with db.get_session() as session:
            task = TaskModel(id=task_id, query=query, status=status)
            session.add(task)
            await session.commit()
            await session.refresh(task)
            return task
    
    async def get(self, task_id: str) -> Optional[TaskModel]:
        if not db.session_factory:
            return _MEMORY_TASKS.get(task_id)

        async with db.get_session() as session:
            result = await session.execute(
                select(TaskModel).where(TaskModel.id == task_id)
            )
            return result.scalar_one_or_none()
    
    async def update(
        self,
        task_id: str,
        status: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> Optional[TaskModel]:
        if not db.session_factory:
            task = _MEMORY_TASKS.get(task_id)
            if task:
                if status:
                    task.status = status
                if result is not None:
                    task.result = result
                if error:
                    task.error = error
                task.updated_at = datetime.utcnow()
            return task

        async with db.get_session() as session:
            result_obj = await session.execute(
                select(TaskModel).where(TaskModel.id == task_id)
            )
            task = result_obj.scalar_one_or_none()
            
            if task:
                if status:
                    task.status = status
                if result is not None:
                    task.result = result
                if error:
                    task.error = error
                
                await session.commit()
                await session.refresh(task)
            
            return task
    
    async def list_all(self) -> List[TaskModel]:
        if not db.session_factory:
            return sorted(_MEMORY_TASKS.values(), key=lambda task: task.created_at, reverse=True)

        async with db.get_session() as session:
            result = await session.execute(
                select(TaskModel).order_by(TaskModel.created_at.desc())
            )
            return result.scalars().all()


class StepRepository:
    async def create(
        self,
        step_id: str,
        task_id: str,
        step_number: int,
        agent_type: str,
        input_data: Optional[Dict[str, Any]] = None
    ) -> StepModel:
        if not db.session_factory:
            step = _memory_row(
                id=step_id,
                task_id=task_id,
                step_number=step_number,
                agent_type=agent_type,
                status="pending",
                input_data=input_data,
                output_data=None,
                confidence=None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            _MEMORY_STEPS[step_id] = step
            return step

        async with db.get_session() as session:
            step = StepModel(
                id=step_id,
                task_id=task_id,
                step_number=step_number,
                agent_type=agent_type,
                input_data=input_data
            )
            session.add(step)
            await session.commit()
            await session.refresh(step)
            return step
    
    async def update(
        self,
        step_id: str,
        status: Optional[str] = None,
        output_data: Optional[Dict[str, Any]] = None,
        confidence: Optional[float] = None
    ) -> Optional[StepModel]:
        if not db.session_factory:
            step = _MEMORY_STEPS.get(step_id)
            if step:
                if status:
                    step.status = status
                if output_data is not None:
                    step.output_data = output_data
                if confidence is not None:
                    step.confidence = confidence
                step.updated_at = datetime.utcnow()
            return step

        async with db.get_session() as session:
            result = await session.execute(
                select(StepModel).where(StepModel.id == step_id)
            )
            step = result.scalar_one_or_none()
            
            if step:
                if status:
                    step.status = status
                if output_data is not None:
                    step.output_data = output_data
                if confidence is not None:
                    step.confidence = confidence
                
                await session.commit()
                await session.refresh(step)
            
            return step
    
    async def get_by_task(self, task_id: str) -> List[StepModel]:
        if not db.session_factory:
            return sorted(
                [step for step in _MEMORY_STEPS.values() if step.task_id == task_id],
                key=lambda step: step.step_number,
            )

        async with db.get_session() as session:
            result = await session.execute(
                select(StepModel)
                .where(StepModel.task_id == task_id)
                .order_by(StepModel.step_number)
            )
            return result.scalars().all()


task_repo = TaskRepository()
step_repo = StepRepository()


class UserRepository:
    async def create(
        self,
        user_id: str,
        email: str,
        hashed_password: str,
        name: Optional[str] = None,
        api_key: Optional[str] = None
    ) -> UserModel:
        if not db.session_factory:
            user = _memory_row(
                id=user_id,
                email=email,
                hashed_password=hashed_password,
                name=name,
                api_key=api_key,
                is_active=True,
                created_at=datetime.utcnow(),
            )
            _MEMORY_USERS[user_id] = user
            return user

        async with db.get_session() as session:
            user = UserModel(
                id=user_id,
                email=email,
                hashed_password=hashed_password,
                name=name,
                api_key=api_key
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user
    
    async def get_by_email(self, email: str) -> Optional[UserModel]:
        if not db.session_factory:
            return next((user for user in _MEMORY_USERS.values() if user.email == email), None)

        async with db.get_session() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.email == email)
            )
            return result.scalar_one_or_none()
    
    async def get_by_id(self, user_id: str) -> Optional[UserModel]:
        if not db.session_factory:
            return _MEMORY_USERS.get(user_id)

        async with db.get_session() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            return result.scalar_one_or_none()
    
    async def get_by_api_key(self, api_key: str) -> Optional[UserModel]:
        if not db.session_factory:
            return next((user for user in _MEMORY_USERS.values() if user.api_key == api_key), None)

        async with db.get_session() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.api_key == api_key)
            )
            return result.scalar_one_or_none()
    
    async def update_api_key(
        self,
        user_id: str,
        api_key: str
    ) -> Optional[UserModel]:
        if not db.session_factory:
            user = _MEMORY_USERS.get(user_id)
            if user:
                user.api_key = api_key
            return user

        async with db.get_session() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if user:
                user.api_key = api_key
                await session.commit()
                await session.refresh(user)
            
            return user


user_repo = UserRepository()
