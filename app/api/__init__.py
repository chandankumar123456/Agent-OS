from fastapi import APIRouter
from .routes import tasks, auth, tools, agents, config, workflows, tools_v2, workflows_v2, agents_v2, onboarding, analytics, chat, providers, knowledge, events, workspaces, api_keys, deployments
from ..logs.metrics import metrics_collector

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(tasks.router)
# tools_v2 MUST be registered BEFORE tools so that static /tools/v2 routes
# take precedence over the parameterized /tools/{tool_name} route.
api_router.include_router(tools_v2.router)
api_router.include_router(tools.router)
api_router.include_router(agents.router)
api_router.include_router(config.router)
api_router.include_router(workflows.router)
api_router.include_router(workflows_v2.router)
api_router.include_router(agents_v2.router)
api_router.include_router(onboarding.router)
api_router.include_router(analytics.router)
api_router.include_router(chat.router)
api_router.include_router(providers.router)
api_router.include_router(knowledge.router)
api_router.include_router(events.router)
api_router.include_router(workspaces.router)
api_router.include_router(api_keys.router)
api_router.include_router(deployments.router)


@api_router.get("/metrics")
async def metrics():
    return metrics_collector.get_json_summary()
