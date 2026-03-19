# Lumencore

AI Control Plane for autonomous agents, workflows, and execution systems.

## Core Principle
Everything runs inside one system:
- No side scripts
- No external tools outside control-plane
- All inputs routed through orchestrator

## Structure

- /lumencore → core system
- /agents → agent logic
- /connectors → external integrations
- /workflows → execution pipelines
- /dashboard → control UI
- /control-plane → orchestration layer

## Rules

- Do NOT create parallel systems
- Do NOT bypass control-plane
- All execution must be traceable

## Current Phase

Phase 25:
- Decouple input route from command route
- Stabilize execution pipeline

## Goal

One unified system that can:
- orchestrate agents
- execute workflows
- scale to autonomous operation
- ## Execution Model

Lumencore runs as a single control plane that processes all input through a unified pipeline:

INPUT → ROUTER → COMMAND → AGENT → EXECUTION → OUTPUT

- Input: Telegram / Dashboard / API
- Router: determines intent
- Command: normalized instruction
- Agent: executes logic
- Execution: performs action
- Output: response + logs

All flows must pass through this pipeline.
No direct execution is allowed outside this path.
