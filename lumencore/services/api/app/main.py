from fastapi import FastAPI

from .agents.agent_registry import ensure_agent_registry_seeded
from .config import settings
from .connectors.startup import register_default_connectors
from .db import init_db, session_scope
from .routes.agents import router as agents_router
from .routes.agent_runs import router as agent_runs_router
from .routes.commands import router as commands_router
from .routes.command import router as command_router
from .routes.command_queue import router as command_queue_router
from .routes.connectors import router as connectors_router
from .routes.nodes import router as nodes_router
from .routes.operator import router as operator_router
from .routes.execution_control import router as execution_control_router
from .routes.execution_tasks import router as execution_tasks_router
from .routes.health import router as health_router
from .routes.recovery import router as recovery_router
from .routes.input import router as input_router
from .routes.jobs import router as jobs_router
from .routes.plans import router as plans_router
from .routes.system import router as system_router
from .routes.memory import router as memory_router
from .routes.tasks import router as tasks_router
from .routes.workflows import router as workflows_router
from .services.deployment.deployment_service import get_deployment_state, mark_failed_restart, record_deploy, record_restart
from .services.runtime_health import get_runtime_health_snapshot
from .tools.bootstrap import register_placeholder_tools


app = FastAPI(title='Lumencore API', version='4.1.0')



@app.on_event('startup')
def on_startup() -> None:
    register_default_connectors()
    register_placeholder_tools()
    init_db()
    with session_scope() as session:
        ensure_agent_registry_seeded(session)
    record_restart()
    deployment_state = get_deployment_state()
    if deployment_state.get("last_known_good_release") != settings.release_id:
        record_deploy(settings.release_id)
    if get_runtime_health_snapshot().get("status") != "ok":
        mark_failed_restart()


app.include_router(health_router)
app.include_router(recovery_router)
app.include_router(input_router)
app.include_router(system_router)
app.include_router(jobs_router)
app.include_router(agents_router)
app.include_router(agent_runs_router)
app.include_router(commands_router)
app.include_router(command_router)
app.include_router(command_queue_router)
app.include_router(connectors_router)
app.include_router(nodes_router)
app.include_router(operator_router, prefix="/api/operator", tags=["operator"])
app.include_router(execution_tasks_router)
app.include_router(execution_control_router)
app.include_router(plans_router)
app.include_router(tasks_router)
app.include_router(memory_router)
app.include_router(workflows_router)




