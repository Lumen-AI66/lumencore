from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .config import settings


engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


@contextmanager
def session_scope() -> Session:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ensure_phase4_schema() -> None:
    statements = [
        "ALTER TABLE public.phase3_jobs ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64)",
        "UPDATE public.phase3_jobs SET tenant_id = 'owner' WHERE tenant_id IS NULL",
        "ALTER TABLE public.phase3_jobs ALTER COLUMN tenant_id SET DEFAULT 'owner'",
        "ALTER TABLE public.phase3_jobs ALTER COLUMN tenant_id SET NOT NULL",
        "ALTER TABLE public.agents ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64)",
        "UPDATE public.agents SET tenant_id = 'owner' WHERE tenant_id IS NULL",
        "ALTER TABLE public.agents ALTER COLUMN tenant_id SET DEFAULT 'owner'",
        "ALTER TABLE public.agents ALTER COLUMN tenant_id SET NOT NULL",
        "ALTER TABLE public.agent_runs ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64)",
        "UPDATE public.agent_runs SET tenant_id = 'owner' WHERE tenant_id IS NULL",
        "ALTER TABLE public.agent_runs ALTER COLUMN tenant_id SET DEFAULT 'owner'",
        "ALTER TABLE public.agent_runs ALTER COLUMN tenant_id SET NOT NULL",
        """
        CREATE TABLE IF NOT EXISTS public.agent_audit_events (
            id VARCHAR(36) PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
            tenant_id VARCHAR(64) NOT NULL DEFAULT 'owner',
            agent_id UUID NULL REFERENCES public.agents(id) ON DELETE SET NULL,
            action VARCHAR(128) NOT NULL,
            policy_result VARCHAR(32) NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_agent_audit_events_timestamp ON public.agent_audit_events (timestamp DESC)",
        """
        CREATE TABLE IF NOT EXISTS public.command_runs (
            id VARCHAR(36) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL DEFAULT 'owner',
            command_text TEXT NOT NULL,
            normalized_command TEXT NOT NULL,
            intent VARCHAR(64) NOT NULL,
            planned_task_type VARCHAR(64) NULL,
            requested_mode VARCHAR(32) NULL,
            selected_agent_id UUID NULL REFERENCES public.agents(id) ON DELETE SET NULL,
            status VARCHAR(32) NOT NULL,
            execution_decision VARCHAR(32) NOT NULL DEFAULT 'allowed',
            approval_required BOOLEAN NOT NULL DEFAULT FALSE,
            approval_status VARCHAR(32) NOT NULL DEFAULT 'not_required',
            policy_reason TEXT NULL,
            job_id VARCHAR(36) NULL REFERENCES public.phase3_jobs(id) ON DELETE SET NULL,
            result_summary JSONB NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "UPDATE public.command_runs SET tenant_id = 'owner' WHERE tenant_id IS NULL",
        "ALTER TABLE public.command_runs ALTER COLUMN tenant_id SET DEFAULT 'owner'",
        "ALTER TABLE public.command_runs ALTER COLUMN tenant_id SET NOT NULL",
        "ALTER TABLE public.command_runs ADD COLUMN IF NOT EXISTS requested_mode VARCHAR(32) NULL",
        "ALTER TABLE public.command_runs ADD COLUMN IF NOT EXISTS execution_decision VARCHAR(32)",
        "UPDATE public.command_runs SET execution_decision = 'allowed' WHERE execution_decision IS NULL",
        "ALTER TABLE public.command_runs ALTER COLUMN execution_decision SET DEFAULT 'allowed'",
        "ALTER TABLE public.command_runs ALTER COLUMN execution_decision SET NOT NULL",
        "ALTER TABLE public.command_runs ADD COLUMN IF NOT EXISTS approval_required BOOLEAN",
        "UPDATE public.command_runs SET approval_required = FALSE WHERE approval_required IS NULL",
        "ALTER TABLE public.command_runs ALTER COLUMN approval_required SET DEFAULT FALSE",
        "ALTER TABLE public.command_runs ALTER COLUMN approval_required SET NOT NULL",
        "ALTER TABLE public.command_runs ADD COLUMN IF NOT EXISTS approval_status VARCHAR(32)",
        "UPDATE public.command_runs SET approval_status = 'not_required' WHERE approval_status IS NULL",
        "ALTER TABLE public.command_runs ALTER COLUMN approval_status SET DEFAULT 'not_required'",
        "ALTER TABLE public.command_runs ALTER COLUMN approval_status SET NOT NULL",
        "ALTER TABLE public.command_runs ADD COLUMN IF NOT EXISTS policy_reason TEXT NULL",
        "ALTER TABLE public.command_runs ADD COLUMN IF NOT EXISTS last_control_action VARCHAR(32) NULL",
        "ALTER TABLE public.command_runs ADD COLUMN IF NOT EXISTS last_control_reason TEXT NULL",
        "ALTER TABLE public.command_runs ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ NULL",
        "ALTER TABLE public.command_runs ADD COLUMN IF NOT EXISTS retried_from_id VARCHAR(36) NULL",
        "ALTER TABLE public.command_runs ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ NULL",
        "ALTER TABLE public.command_runs ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ NULL",
        "CREATE INDEX IF NOT EXISTS idx_command_runs_created_at ON public.command_runs (created_at DESC)",        "CREATE TABLE IF NOT EXISTS public.operator_events (\n            id VARCHAR(36) PRIMARY KEY,\n            command_id VARCHAR(36) NOT NULL REFERENCES public.command_runs(id) ON DELETE CASCADE,\n            event_type VARCHAR(64) NOT NULL,\n            timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),\n            metadata_json JSONB NULL\n        )",
        "CREATE INDEX IF NOT EXISTS idx_operator_events_command_id ON public.operator_events (command_id, timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS idx_operator_events_event_type ON public.operator_events (event_type, timestamp DESC)",
        """
        CREATE TABLE IF NOT EXISTS public.project_budgets (
            id VARCHAR(36) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL DEFAULT 'owner',
            project_id VARCHAR(128) NOT NULL,
            monthly_limit DOUBLE PRECISION NOT NULL DEFAULT 0,
            current_spend DOUBLE PRECISION NOT NULL DEFAULT 0,
            last_reset TIMESTAMPTZ NULL,
            provider VARCHAR(64) NOT NULL DEFAULT 'internal',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "UPDATE public.project_budgets SET tenant_id = 'owner' WHERE tenant_id IS NULL",
        "ALTER TABLE public.project_budgets ALTER COLUMN tenant_id SET DEFAULT 'owner'",
        "ALTER TABLE public.project_budgets ALTER COLUMN tenant_id SET NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_project_budgets_tenant_project ON public.project_budgets (tenant_id, project_id)",
        """
        CREATE TABLE IF NOT EXISTS public.agent_secret_permissions (
            id SERIAL PRIMARY KEY,
            agent_id UUID NOT NULL REFERENCES public.agents(id) ON DELETE CASCADE,
            secret_scope VARCHAR(32) NOT NULL,
            secret_key VARCHAR(255) NOT NULL,
            tenant_id VARCHAR(64) NOT NULL DEFAULT 'owner',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "UPDATE public.agent_secret_permissions SET tenant_id = 'owner' WHERE tenant_id IS NULL",
        "ALTER TABLE public.agent_secret_permissions ALTER COLUMN tenant_id SET DEFAULT 'owner'",
        "ALTER TABLE public.agent_secret_permissions ALTER COLUMN tenant_id SET NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_agent_secret_permissions_agent ON public.agent_secret_permissions (agent_id)",
        """
        CREATE TABLE IF NOT EXISTS public.agent_run_state (
            run_id VARCHAR(36) PRIMARY KEY REFERENCES public.agent_runs(id) ON DELETE CASCADE,
            tenant_id VARCHAR(64) NOT NULL DEFAULT 'owner',
            agent_id UUID NULL REFERENCES public.agents(id) ON DELETE SET NULL,
            agent_type VARCHAR(64) NOT NULL,
            command_id VARCHAR(36) NULL REFERENCES public.command_runs(id) ON DELETE SET NULL,
            task_id VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            current_step VARCHAR(128) NULL,
            last_decision JSONB NULL,
            retry_count INTEGER NOT NULL DEFAULT 0,
            started_at TIMESTAMPTZ NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ NULL,
            last_error TEXT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_agent_run_state_status_updated ON public.agent_run_state (status, updated_at DESC)",
        """
        CREATE TABLE IF NOT EXISTS public.agent_task_state (
            task_id VARCHAR(64) PRIMARY KEY,
            run_id VARCHAR(36) NOT NULL REFERENCES public.agent_runs(id) ON DELETE CASCADE,
            tenant_id VARCHAR(64) NOT NULL DEFAULT 'owner',
            task_type VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            input_summary JSONB NULL,
            output_summary JSONB NULL,
            failure_metadata JSONB NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_agent_task_state_run_id ON public.agent_task_state (run_id)",
        """
        CREATE TABLE IF NOT EXISTS public.agent_state_events (
            id VARCHAR(36) PRIMARY KEY,
            run_id VARCHAR(36) NOT NULL REFERENCES public.agent_runs(id) ON DELETE CASCADE,
            tenant_id VARCHAR(64) NOT NULL DEFAULT 'owner',
            task_id VARCHAR(64) NULL,
            event_type VARCHAR(128) NOT NULL,
            step_name VARCHAR(128) NULL,
            message TEXT NOT NULL,
            payload_summary JSONB NULL,
            severity VARCHAR(32) NOT NULL DEFAULT 'info',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_agent_state_events_run_created ON public.agent_state_events (run_id, created_at ASC)",
        """
        CREATE TABLE IF NOT EXISTS public.execution_tasks (
            task_id VARCHAR(36) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL DEFAULT 'owner',
            command_id VARCHAR(36) NULL REFERENCES public.command_runs(id) ON DELETE SET NULL,
            agent_id UUID NULL REFERENCES public.agents(id) ON DELETE SET NULL,
            agent_type VARCHAR(64) NOT NULL,
            task_type VARCHAR(64) NOT NULL DEFAULT 'agent_task',
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            priority INTEGER NOT NULL DEFAULT 100,
            retries INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 0,
            available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at TIMESTAMPTZ NULL,
            finished_at TIMESTAMPTZ NULL,
            error TEXT NULL,
            result_summary JSONB NULL,
            task_metadata JSONB NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_execution_tasks_ready ON public.execution_tasks (status, priority, available_at, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_execution_tasks_command_id ON public.execution_tasks (command_id)",
        """
        CREATE TABLE IF NOT EXISTS public.plan_runs (
            plan_id VARCHAR(36) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL DEFAULT 'owner',
            command_id VARCHAR(36) NULL REFERENCES public.command_runs(id) ON DELETE SET NULL,
            plan_type VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            total_steps INTEGER NOT NULL DEFAULT 0,
            current_step_index INTEGER NOT NULL DEFAULT 0,
            error TEXT NULL,
            result_summary JSONB NULL,
            plan_metadata JSONB NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_plan_runs_status_updated ON public.plan_runs (status, updated_at DESC)",
        "ALTER TABLE public.plan_runs ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ NULL",
        "ALTER TABLE public.plan_runs ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ NULL",
        """
        CREATE TABLE IF NOT EXISTS public.plan_steps (
            step_id VARCHAR(36) PRIMARY KEY,
            plan_id VARCHAR(36) NOT NULL REFERENCES public.plan_runs(plan_id) ON DELETE CASCADE,
            step_index INTEGER NOT NULL,
            step_type VARCHAR(64) NOT NULL,
            agent_type VARCHAR(64) NOT NULL,
            title VARCHAR(160) NOT NULL,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            execution_task_id VARCHAR(36) NULL REFERENCES public.execution_tasks(task_id) ON DELETE SET NULL,
            error TEXT NULL,
            result_summary JSONB NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_plan_steps_plan_index ON public.plan_steps (plan_id, step_index ASC)",
        "ALTER TABLE public.plan_steps ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ NULL",
        "ALTER TABLE public.plan_steps ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ NULL",
        """
        CREATE TABLE IF NOT EXISTS public.workflow_runs (
            workflow_id VARCHAR(36) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL DEFAULT 'owner',
            command_id VARCHAR(36) NULL REFERENCES public.command_runs(id) ON DELETE SET NULL,
            workflow_type VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            linked_plan_id VARCHAR(36) NULL REFERENCES public.plan_runs(plan_id) ON DELETE SET NULL,
            input_summary JSONB NULL,
            workflow_metadata JSONB NULL,
            result_summary JSONB NULL,
            error TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_workflow_runs_status_updated ON public.workflow_runs (status, updated_at DESC)",
        "ALTER TABLE public.workflow_runs ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ NULL",
        "ALTER TABLE public.workflow_runs ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ NULL",
        "CREATE INDEX IF NOT EXISTS idx_workflow_runs_command_id ON public.workflow_runs (command_id)",
    ]

    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_phase4_schema()


def check_db() -> dict:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"ok": True, "message": "database reachable"}
    except SQLAlchemyError as exc:
        return {"ok": False, "message": str(exc)}








