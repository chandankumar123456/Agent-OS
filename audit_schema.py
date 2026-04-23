"""
Schema audit: Compare ORM models to actual DB schema.
Reports any mismatches between code expectations and database reality.
"""
import asyncio
from sqlalchemy import text, inspect
from app.memory.long_term import db
from app.memory.models import (
    TaskModel, StepModel, WorkflowModel, WorkflowNodeModel, WorkflowEdgeModel,
    ContextModel, MessageModel, TraceModel, NodeTraceModel, SpanModel,
    ToolModel, AgentModel, ConfigModel, UserModel
)

ORM_MODELS = {
    "tasks": TaskModel,
    "steps": StepModel,
    "workflows": WorkflowModel,
    "workflow_nodes": WorkflowNodeModel,
    "workflow_edges": WorkflowEdgeModel,
    "context": ContextModel,
    "messages": MessageModel,
    "traces": TraceModel,
    "node_traces": NodeTraceModel,
    "spans": SpanModel,
    "tools": ToolModel,
    "agents": AgentModel,
    "config": ConfigModel,
    "users": UserModel,
}


def get_orm_columns(model):
    """Extract column info from ORM model."""
    cols = {}
    for col in model.__table__.columns:
        cols[col.name] = {
            "type": str(col.type),
            "nullable": col.nullable,
            "primary_key": col.primary_key,
            "unique": col.unique if hasattr(col, 'unique') else False,
        }
    return cols


async def get_db_columns(table_name):
    """Extract column info from actual DB."""
    async with db.engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = :table
            ORDER BY ordinal_position
        """), {"table": table_name})
        cols = {}
        for row in result:
            cols[row[0]] = {
                "type": row[1],
                "nullable": row[2] == "YES",
            }
        return cols


async def audit():
    await db.connect()
    mismatches = []

    for table_name, model in ORM_MODELS.items():
        orm_cols = get_orm_columns(model)
        db_cols = await get_db_columns(table_name)

        if not db_cols:
            mismatches.append(f"❌ Table '{table_name}' does not exist in DB")
            continue

        # Check for missing columns in DB
        for col_name in orm_cols:
            if col_name not in db_cols:
                mismatches.append(f"FAIL: {table_name}.{col_name}: exists in ORM but MISSING in DB")

        # Check for extra columns in DB (not in ORM)
        for col_name in db_cols:
            if col_name not in orm_cols:
                mismatches.append(f"WARN: {table_name}.{col_name}: exists in DB but NOT in ORM")

        # Check type mismatches
        for col_name in orm_cols:
            if col_name in db_cols:
                orm_type = orm_cols[col_name]["type"].lower()
                db_type = db_cols[col_name]["type"].lower()

                # Normalize types for comparison
                type_map = {
                    "varchar": "character varying",
                    "text": "text",
                    "integer": "integer",
                    "float": "double precision",
                    "boolean": "boolean",
                    "json": "json",
                    "datetime": "timestamp without time zone",
                    "timestamp": "timestamp without time zone",
                }

                orm_normalized = type_map.get(orm_type.split("(")[0].strip(), orm_type)
                db_normalized = db_type.split("(")[0].strip()

                # Allow some flexibility in type matching
                if "varchar" in orm_normalized and "character varying" in db_normalized:
                    continue
                if "text" in orm_normalized and "text" in db_normalized:
                    continue
                if "json" in orm_normalized and "json" in db_normalized:
                    continue
                if "float" in orm_normalized and "double precision" in db_normalized:
                    continue
                if "datetime" in orm_normalized and "timestamp" in db_normalized:
                    continue
                if orm_normalized != db_normalized:
                    mismatches.append(
                        f"WARN: {table_name}.{col_name}: type mismatch "
                        f"(ORM={orm_normalized}, DB={db_normalized})"
                    )

                # Check nullable mismatch
                if orm_cols[col_name]["nullable"] != db_cols[col_name]["nullable"]:
                    mismatches.append(
                        f"FAIL: {table_name}.{col_name}: nullable mismatch "
                        f"(ORM={orm_cols[col_name]['nullable']}, DB={db_cols[col_name]['nullable']})"
                    )

    await db.disconnect()

    if not mismatches:
        print("PASS: Schema audit PASSED: No mismatches found")
    else:
        print(f"\nINFO: Schema audit found {len(mismatches)} issue(s):\n")
        for m in mismatches:
            print(f"  {m}")

    return len(mismatches) == 0


if __name__ == "__main__":
    result = asyncio.run(audit())
    exit(0 if result else 1)
