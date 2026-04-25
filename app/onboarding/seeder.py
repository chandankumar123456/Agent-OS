from uuid import uuid4
from datetime import datetime
from ..memory.long_term import db
from ..memory.models import (
    AgentConfigV2Model,
    WorkflowModel,
    TaskModel,
    StepModel,
    TraceModel,
    NodeTraceModel,
    SpanModel,
)
from sqlalchemy import select
from ..logs.logger import logger

EXAMPLE_AGENTS = [
    {
        "agent_id": "example_researcher_v2",
        "name": "Research Analyst",
        "role": "researcher",
        "goal": "Find and synthesize information on any topic",
        "backstory": "You are a research analyst with expertise in web search and text processing.",
        "model": "gpt-4o",
        "temperature": 0.3,
        "tools": ["web_search", "text_processor"],
    },
    {
        "agent_id": "example_coder_v2",
        "name": "Code Assistant",
        "role": "coder",
        "goal": "Write clean, well-documented code",
        "backstory": "You are a senior software engineer specializing in multiple languages.",
        "model": "gpt-4o",
        "temperature": 0.1,
        "tools": ["shell"],
    },
    {
        "agent_id": "example_analyst_v2",
        "name": "Data Analyst",
        "role": "analyst",
        "goal": "Calculate metrics, process text, and present findings clearly",
        "backstory": "You are a data analyst with strong statistical skills.",
        "model": "gpt-4o-mini",
        "temperature": 0.2,
        "tools": ["calculator", "text_processor"],
    },
]

EXAMPLE_WORKFLOWS = [
    {
        "name": "Content Pipeline",
        "definition": {
            "nodes": [
                {"id": "research", "step": "Research topic", "agent_type": "executor", "node_type": "agent"},
                {"id": "draft", "step": "Draft content", "agent_type": "executor", "node_type": "agent", "depends_on": ["research"]},
                {"id": "review", "step": "Review content", "agent_type": "verifier", "node_type": "agent", "depends_on": ["draft"]},
            ]
        }
    },
    {
        "name": "Data Processing",
        "definition": {
            "nodes": [
                {"id": "ingest", "step": "Ingest data", "agent_type": "executor", "node_type": "agent"},
                {"id": "transform", "step": "Transform data", "agent_type": "executor", "node_type": "agent", "depends_on": ["ingest"]},
                {"id": "analyze", "step": "Analyze results", "agent_type": "verifier", "node_type": "agent", "depends_on": ["transform"]},
            ]
        }
    },
]


async def seed_example_data(user_id: str):
    logger.info(f"Seeding example data for user {user_id}")

    async with db.get_session() as session:
        # Seed v2 agents idempotently
        for agent_data in EXAMPLE_AGENTS:
            try:
                result = await session.execute(
                    select(AgentConfigV2Model).where(AgentConfigV2Model.agent_id == agent_data["agent_id"])
                )
                existing = result.scalar_one_or_none()
                if existing:
                    logger.info(f"Agent {agent_data['agent_id']} already exists, skipping")
                    continue

                agent = AgentConfigV2Model(
                    id=uuid4(),
                    agent_id=agent_data["agent_id"],
                    name=agent_data["name"],
                    role=agent_data["role"],
                    goal=agent_data["goal"],
                    backstory=agent_data["backstory"],
                    model=agent_data["model"],
                    temperature=agent_data["temperature"],
                    tools=agent_data["tools"],
                    status="active",
                )
                session.add(agent)
                await session.commit()
                logger.info(f"Seeded agent {agent_data['name']}")
            except Exception as e:
                logger.warning(f"Failed to seed agent {agent_data['name']}: {e}")
                await session.rollback()

        # Seed workflows idempotently
        for wf_data in EXAMPLE_WORKFLOWS:
            try:
                result = await session.execute(
                    select(WorkflowModel).where(
                        WorkflowModel.user_id == user_id,
                        WorkflowModel.name == wf_data["name"]
                    )
                )
                existing = result.scalar_one_or_none()
                if existing:
                    logger.info(f"Workflow {wf_data['name']} already exists, skipping")
                    continue

                wf = WorkflowModel(
                    id=str(uuid4()),
                    task_id=str(uuid4()),
                    user_id=user_id,
                    name=wf_data["name"],
                    definition=wf_data["definition"],
                    status="saved",
                )
                session.add(wf)
                await session.commit()
                logger.info(f"Seeded workflow {wf_data['name']}")
            except Exception as e:
                logger.warning(f"Failed to seed workflow {wf_data['name']}: {e}")
                await session.rollback()

        # Create a completed demo task with trace if not exists
        try:
            result = await session.execute(
                select(TaskModel).where(
                    TaskModel.user_id == user_id,
                    TaskModel.query == "Demo: Research multi-agent orchestration benefits"
                )
            )
            existing_task = result.scalar_one_or_none()
            if not existing_task:
                task_id = str(uuid4())
                task = TaskModel(
                    id=task_id,
                    user_id=user_id,
                    query="Demo: Research multi-agent orchestration benefits",
                    status="completed",
                    result={
                        "summary": "Multi-agent orchestration enables scalable, fault-tolerant systems by distributing tasks across specialized agents.",
                        "key_benefits": ["scalability", "fault_tolerance", "specialization", "parallelism"]
                    },
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                session.add(task)
                await session.commit()

                # Add steps
                step1 = StepModel(
                    id=str(uuid4()),
                    task_id=task_id,
                    step_number=1,
                    agent_type="planner",
                    status="completed",
                    input_data={"query": "Research multi-agent orchestration benefits"},
                    output_data={"plan": ["research", "synthesize", "present"]},
                    created_at=datetime.utcnow(),
                )
                step2 = StepModel(
                    id=str(uuid4()),
                    task_id=task_id,
                    step_number=2,
                    agent_type="executor",
                    status="completed",
                    depends_on=[step1.id],
                    input_data={"plan": ["research", "synthesize", "present"]},
                    output_data={"findings": ["scalability", "fault_tolerance"]},
                    created_at=datetime.utcnow(),
                )
                session.add(step1)
                session.add(step2)
                await session.commit()

                # Add trace
                trace_id = str(uuid4())
                trace = TraceModel(
                    id=str(uuid4()),
                    task_id=task_id,
                    user_id=user_id,
                    trace_id=trace_id,
                    status="completed",
                    created_at=datetime.utcnow(),
                )
                session.add(trace)
                await session.commit()

                # Add node traces
                node_trace1 = NodeTraceModel(
                    id=str(uuid4()),
                    task_id=task_id,
                    user_id=user_id,
                    trace_id=trace_id,
                    node_id=step1.id,
                    status="completed",
                    input_data={"query": "Research multi-agent orchestration benefits"},
                    output_data={"plan": ["research", "synthesize", "present"]},
                    started_at=datetime.utcnow(),
                    finished_at=datetime.utcnow(),
                )
                node_trace2 = NodeTraceModel(
                    id=str(uuid4()),
                    task_id=task_id,
                    user_id=user_id,
                    trace_id=trace_id,
                    node_id=step2.id,
                    status="completed",
                    input_data={"plan": ["research", "synthesize", "present"]},
                    output_data={"findings": ["scalability", "fault_tolerance"]},
                    started_at=datetime.utcnow(),
                    finished_at=datetime.utcnow(),
                )
                session.add(node_trace1)
                session.add(node_trace2)
                await session.commit()

                # Add spans
                span1 = SpanModel(
                    id=str(uuid4()),
                    trace_id=trace_id,
                    span_id=str(uuid4()),
                    operation="plan_task",
                    agent_name="planner",
                    status="completed",
                    start_time=datetime.utcnow(),
                    end_time=datetime.utcnow(),
                )
                span2 = SpanModel(
                    id=str(uuid4()),
                    trace_id=trace_id,
                    span_id=str(uuid4()),
                    operation="execute_research",
                    agent_name="executor",
                    status="completed",
                    start_time=datetime.utcnow(),
                    end_time=datetime.utcnow(),
                )
                session.add(span1)
                session.add(span2)
                await session.commit()

                logger.info(f"Created demo task with trace: {task_id}")
        except Exception as e:
            logger.warning(f"Failed to create demo task: {e}")
            await session.rollback()

    logger.info(f"Example data seeding complete for user {user_id}")
