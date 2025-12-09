"""
Workflow Execution Services

This package contains the workflow execution engine and related services:
- engine: Core execution engine for workflows, scripts, and data providers
- service: High-level execution service for orchestration
- async_executor: Async execution queuing
- module_loader: Runtime module loading
- type_inference: Parameter type extraction

Logging is handled by bifrost/_logging.py (Redis Stream -> Postgres).
"""
