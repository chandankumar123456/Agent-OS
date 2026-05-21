"""
Deduplicate workflows before applying unique constraint.

Run this script BEFORE applying the unique constraint on workflows.task_id.
It keeps the newest workflow per task_id and deletes older duplicates
along with their related nodes and edges.

Usage:
    python scripts/dedup_workflows.py
"""
import asyncio
import sys
sys.path.insert(0, "E:\\Projects\\AgentOS")

from sqlalchemy import select, delete
from core.memory.long_term import db
from core.memory.models import WorkflowModel, WorkflowNodeModel, WorkflowEdgeModel


async def deduplicate():
    await db.connect()
    session = db.get_session()

    async with session as s:
        # Find all task_ids with multiple workflows
        from sqlalchemy import func
        result = await s.execute(
            select(WorkflowModel.task_id)
            .group_by(WorkflowModel.task_id)
            .having(func.count(WorkflowModel.id) > 1)
        )
        dup_task_ids = [row[0] for row in result.all()]

        if not dup_task_ids:
            print("No duplicate workflows found.")
            return

        print(f"Found {len(dup_task_ids)} task_ids with duplicate workflows.")

        for task_id in dup_task_ids:
            result = await s.execute(
                select(WorkflowModel)
                .where(WorkflowModel.task_id == task_id)
                .order_by(WorkflowModel.created_at.desc())
            )
            workflows = result.scalars().all()
            keep = workflows[0]
            to_delete = workflows[1:]

            print(f"  Task {task_id}: keeping {keep.id}, deleting {len(to_delete)} older workflow(s)")

            for wf in to_delete:
                # Delete related edges
                await s.execute(
                    delete(WorkflowEdgeModel).where(WorkflowEdgeModel.workflow_id == wf.id)
                )
                # Delete related nodes
                await s.execute(
                    delete(WorkflowNodeModel).where(WorkflowNodeModel.workflow_id == wf.id)
                )
                # Delete workflow
                await s.delete(wf)

            await s.commit()

        print("Deduplication complete.")

    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(deduplicate())
