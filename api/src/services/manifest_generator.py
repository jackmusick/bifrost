"""
Manifest Generator — serializes current platform DB state to a Manifest.

Used for:
- First-time git connection (export platform state)
- Manual "export to manifest" operations
- Reconciliation verification
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.agents import Agent
from src.models.orm.applications import Application
from src.models.orm.forms import Form, FormRole
from src.models.orm.organizations import Organization
from src.models.orm.users import Role
from src.models.orm.workflow_roles import WorkflowRole
from src.models.orm.workflows import Workflow
from src.services.manifest import (
    Manifest,
    ManifestAgent,
    ManifestApp,
    ManifestForm,
    ManifestOrganization,
    ManifestRole,
    ManifestWorkflow,
)

logger = logging.getLogger(__name__)


async def generate_manifest(db: AsyncSession) -> Manifest:
    """
    Generate a Manifest from current DB state.

    Queries all active entities and builds a complete manifest
    with org bindings, role assignments, and runtime config.
    """
    # Fetch all active workflows
    wf_result = await db.execute(
        select(Workflow).where(Workflow.is_active == True)  # noqa: E712
    )
    workflows_list = wf_result.scalars().all()

    # Fetch all active forms
    form_result = await db.execute(
        select(Form).where(Form.is_active == True)  # noqa: E712
    )
    forms_list = form_result.scalars().all()

    # Fetch all active agents
    agent_result = await db.execute(
        select(Agent).where(Agent.is_active == True)  # noqa: E712
    )
    agents_list = agent_result.scalars().all()

    # Fetch all apps (Application has no is_active field)
    app_result = await db.execute(select(Application))
    apps_list = app_result.scalars().all()

    # Fetch organizations
    org_result = await db.execute(select(Organization))
    orgs_list = org_result.scalars().all()

    # Fetch roles (roles are global — no organization_id on Role model)
    role_result = await db.execute(select(Role))
    roles_list = role_result.scalars().all()

    # Fetch role assignments for forms and workflows
    wf_role_result = await db.execute(select(WorkflowRole))
    wf_roles_by_wf: dict[str, list[str]] = {}
    for wr in wf_role_result.scalars().all():
        wf_roles_by_wf.setdefault(str(wr.workflow_id), []).append(str(wr.role_id))

    form_role_result = await db.execute(select(FormRole))
    form_roles_by_form: dict[str, list[str]] = {}
    for fr in form_role_result.scalars().all():
        form_roles_by_form.setdefault(str(fr.form_id), []).append(str(fr.role_id))

    # Build manifest
    manifest = Manifest(
        organizations=[
            ManifestOrganization(id=str(org.id), name=org.name)
            for org in orgs_list
        ],
        roles=[
            ManifestRole(
                id=str(role.id),
                name=role.name,
            )
            for role in roles_list
        ],
        workflows={
            wf.name: ManifestWorkflow(
                id=str(wf.id),
                path=wf.path,
                function_name=wf.function_name,
                type=wf.type or "workflow",
                organization_id=str(wf.organization_id) if wf.organization_id else None,
                roles=wf_roles_by_wf.get(str(wf.id), []),
                access_level=wf.access_level or "role_based",
                endpoint_enabled=wf.endpoint_enabled or False,
                timeout_seconds=wf.timeout_seconds or 1800,
                public_endpoint=wf.public_endpoint or False,
                category=wf.category or "General",
                tags=wf.tags or [],
            )
            for wf in workflows_list
        },
        forms={
            form.name: ManifestForm(
                id=str(form.id),
                path=f"forms/{form.id}.form.yaml",
                organization_id=str(form.organization_id) if form.organization_id else None,
                roles=form_roles_by_form.get(str(form.id), []),
            )
            for form in forms_list
        },
        agents={
            agent.name: ManifestAgent(
                id=str(agent.id),
                path=f"agents/{agent.id}.agent.yaml",
                organization_id=str(agent.organization_id) if agent.organization_id else None,
                roles=[],
            )
            for agent in agents_list
        },
        apps={
            app.name: ManifestApp(
                id=str(app.id),
                path=f"apps/{app.slug or app.id}/app.yaml",
                organization_id=str(app.organization_id) if app.organization_id else None,
                roles=[],
            )
            for app in apps_list
        },
    )

    logger.info(
        f"Generated manifest: {len(manifest.workflows)} workflows, "
        f"{len(manifest.forms)} forms, {len(manifest.agents)} agents, "
        f"{len(manifest.apps)} apps"
    )

    return manifest
