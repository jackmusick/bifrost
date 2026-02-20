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

from src.models.orm.agents import Agent, AgentRole
from src.models.orm.app_roles import AppRole
from src.models.orm.applications import Application
from src.models.orm.config import Config
from src.models.orm.events import EventSource, EventSubscription, ScheduleSource, WebhookSource
from src.models.orm.forms import Form, FormRole
from src.models.orm.integrations import Integration, IntegrationConfigSchema, IntegrationMapping
from src.models.orm.oauth import OAuthProvider
from src.models.orm.organizations import Organization
from src.models.orm.tables import Table
from src.models.orm.users import Role
from src.models.orm.workflow_roles import WorkflowRole
from src.models.orm.workflows import Workflow
from src.services.manifest import (
    Manifest,
    ManifestAgent,
    ManifestApp,
    ManifestConfig,
    ManifestEventSource,
    ManifestEventSubscription,
    ManifestForm,
    ManifestIntegration,
    ManifestIntegrationConfigSchema,
    ManifestIntegrationMapping,
    ManifestOAuthProvider,
    ManifestOrganization,
    ManifestRole,
    ManifestTable,
    ManifestWorkflow,
)

logger = logging.getLogger(__name__)


async def generate_manifest(db: AsyncSession) -> Manifest:
    """
    Generate a Manifest from current DB state.

    Queries all active entities and builds a complete manifest
    with org bindings, role assignments, and runtime config.
    """
    # Fetch all active workflows (sorted by name for deterministic manifest output)
    wf_result = await db.execute(
        select(Workflow).where(Workflow.is_active == True).order_by(Workflow.name)  # noqa: E712
    )
    workflows_list = wf_result.scalars().all()

    # Fetch all active forms (sorted by name)
    form_result = await db.execute(
        select(Form).where(Form.is_active == True).order_by(Form.name)  # noqa: E712
    )
    forms_list = form_result.scalars().all()

    # Fetch all active agents (sorted by name)
    agent_result = await db.execute(
        select(Agent).where(Agent.is_active == True).order_by(Agent.name)  # noqa: E712
    )
    agents_list = agent_result.scalars().all()

    # Fetch all apps (sorted by name)
    app_result = await db.execute(select(Application).order_by(Application.name))
    apps_list = app_result.scalars().all()

    # Fetch organizations (sorted by name)
    org_result = await db.execute(select(Organization).order_by(Organization.name))
    orgs_list = org_result.scalars().all()

    # Fetch roles (sorted by name)
    role_result = await db.execute(select(Role).order_by(Role.name))
    roles_list = role_result.scalars().all()

    # Fetch role assignments for all entity types
    wf_role_result = await db.execute(select(WorkflowRole))
    wf_roles_by_wf: dict[str, list[str]] = {}
    for wr in wf_role_result.scalars().all():
        wf_roles_by_wf.setdefault(str(wr.workflow_id), []).append(str(wr.role_id))

    form_role_result = await db.execute(select(FormRole))
    form_roles_by_form: dict[str, list[str]] = {}
    for fr in form_role_result.scalars().all():
        form_roles_by_form.setdefault(str(fr.form_id), []).append(str(fr.role_id))

    agent_role_result = await db.execute(select(AgentRole))
    agent_roles_by_agent: dict[str, list[str]] = {}
    for ar in agent_role_result.scalars().all():
        agent_roles_by_agent.setdefault(str(ar.agent_id), []).append(str(ar.role_id))

    app_role_result = await db.execute(select(AppRole))
    app_roles_by_app: dict[str, list[str]] = {}
    for apr in app_role_result.scalars().all():
        app_roles_by_app.setdefault(str(apr.app_id), []).append(str(apr.role_id))

    # Sort role lists for deterministic manifest output
    for roles in wf_roles_by_wf.values():
        roles.sort()
    for roles in form_roles_by_form.values():
        roles.sort()
    for roles in agent_roles_by_agent.values():
        roles.sort()
    for roles in app_roles_by_app.values():
        roles.sort()

    # ------------------------------------------------------------------
    # Integrations (with config_schema, oauth_provider, mappings)
    # ------------------------------------------------------------------
    integ_result = await db.execute(
        select(Integration)
        .where(Integration.is_deleted == False)  # noqa: E712
        .order_by(Integration.name)
    )
    integrations_list = integ_result.scalars().unique().all()

    # Config schema items (eager-loaded via selectin, but build a lookup anyway)
    config_schema_result = await db.execute(
        select(IntegrationConfigSchema).order_by(
            IntegrationConfigSchema.integration_id,
            IntegrationConfigSchema.position,
        )
    )
    config_schema_by_integ: dict[str, list[IntegrationConfigSchema]] = {}
    for cs in config_schema_result.scalars().all():
        config_schema_by_integ.setdefault(str(cs.integration_id), []).append(cs)

    # OAuth providers keyed by integration_id
    oauth_result = await db.execute(select(OAuthProvider))
    oauth_by_integ: dict[str, OAuthProvider] = {}
    for op in oauth_result.scalars().all():
        if op.integration_id:
            oauth_by_integ[str(op.integration_id)] = op

    # Integration mappings
    mapping_result = await db.execute(
        select(IntegrationMapping).order_by(
            IntegrationMapping.integration_id,
            IntegrationMapping.organization_id,
        )
    )
    mappings_by_integ: dict[str, list[IntegrationMapping]] = {}
    for im in mapping_result.scalars().all():
        mappings_by_integ.setdefault(str(im.integration_id), []).append(im)

    # ------------------------------------------------------------------
    # Configs (non-secret values, secrets redacted to None)
    # ------------------------------------------------------------------
    from src.models.enums import ConfigType

    config_result = await db.execute(select(Config).order_by(Config.key))
    configs_list = config_result.scalars().all()

    # ------------------------------------------------------------------
    # Tables
    # ------------------------------------------------------------------
    table_result = await db.execute(select(Table).order_by(Table.name))
    tables_list = table_result.scalars().all()

    # ------------------------------------------------------------------
    # Event sources + subscriptions
    # ------------------------------------------------------------------
    event_source_result = await db.execute(
        select(EventSource)
        .where(EventSource.is_active == True)  # noqa: E712
        .order_by(EventSource.name)
    )
    event_sources_list = event_source_result.scalars().unique().all()

    # Schedule sources keyed by event_source_id
    schedule_result = await db.execute(select(ScheduleSource))
    schedule_by_source: dict[str, ScheduleSource] = {}
    for ss in schedule_result.scalars().all():
        schedule_by_source[str(ss.event_source_id)] = ss

    # Webhook sources keyed by event_source_id
    webhook_result = await db.execute(select(WebhookSource))
    webhook_by_source: dict[str, WebhookSource] = {}
    for ws in webhook_result.scalars().all():
        webhook_by_source[str(ws.event_source_id)] = ws

    # Subscriptions keyed by event_source_id
    sub_result = await db.execute(
        select(EventSubscription)
        .where(EventSubscription.is_active == True)  # noqa: E712
        .order_by(EventSubscription.event_source_id, EventSubscription.workflow_id)
    )
    subs_by_source: dict[str, list[EventSubscription]] = {}
    for sub in sub_result.scalars().all():
        subs_by_source.setdefault(str(sub.event_source_id), []).append(sub)

    # ------------------------------------------------------------------
    # Build manifest
    # ------------------------------------------------------------------
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
        integrations={
            integ.name: ManifestIntegration(
                id=str(integ.id),
                entity_id=integ.entity_id,
                entity_id_name=integ.entity_id_name,
                default_entity_id=integ.default_entity_id,
                list_entities_data_provider_id=(
                    str(integ.list_entities_data_provider_id)
                    if integ.list_entities_data_provider_id else None
                ),
                config_schema=[
                    ManifestIntegrationConfigSchema(
                        key=cs.key,
                        type=cs.type,
                        required=cs.required,
                        description=cs.description,
                        options=cs.options,
                        position=cs.position,
                    )
                    for cs in config_schema_by_integ.get(str(integ.id), [])
                ],
                oauth_provider=(
                    ManifestOAuthProvider(
                        provider_name=op.provider_name,
                        display_name=op.display_name,
                        oauth_flow_type=op.oauth_flow_type,
                        client_id=op.client_id or "__NEEDS_SETUP__",
                        authorization_url=op.authorization_url,
                        token_url=op.token_url,
                        token_url_defaults=op.token_url_defaults or None,
                        scopes=op.scopes or [],
                        redirect_uri=op.redirect_uri,
                    )
                    if (op := oauth_by_integ.get(str(integ.id))) else None
                ),
                mappings=[
                    ManifestIntegrationMapping(
                        organization_id=str(im.organization_id) if im.organization_id else None,
                        entity_id=im.entity_id,
                        entity_name=im.entity_name,
                        oauth_token_id=str(im.oauth_token_id) if im.oauth_token_id else None,
                    )
                    for im in mappings_by_integ.get(str(integ.id), [])
                ],
            )
            for integ in integrations_list
        },
        configs={
            # Key by config UUID to avoid cross-org collisions on same key name
            str(cfg.id): ManifestConfig(
                id=str(cfg.id),
                integration_id=str(cfg.integration_id) if cfg.integration_id else None,
                key=cfg.key,
                config_type=cfg.config_type.value if cfg.config_type else "string",
                description=cfg.description,
                organization_id=str(cfg.organization_id) if cfg.organization_id else None,
                value=None if cfg.config_type == ConfigType.SECRET else cfg.value,
            )
            for cfg in configs_list
        },
        tables={
            table.name: ManifestTable(
                id=str(table.id),
                description=table.description,
                organization_id=str(table.organization_id) if table.organization_id else None,
                application_id=str(table.application_id) if table.application_id else None,
                **{"schema": table.schema},  # alias for table_schema
            )
            for table in tables_list
        },
        events={
            es.name: _build_event_source_manifest(
                es, schedule_by_source, webhook_by_source, subs_by_source
            )
            for es in event_sources_list
        },
        forms={
            form.name: ManifestForm(
                id=str(form.id),
                path=f"forms/{form.id}.form.yaml",
                organization_id=str(form.organization_id) if form.organization_id else None,
                roles=form_roles_by_form.get(str(form.id), []),
                access_level=form.access_level.value if form.access_level else "role_based",
            )
            for form in forms_list
        },
        agents={
            agent.name: ManifestAgent(
                id=str(agent.id),
                path=f"agents/{agent.id}.agent.yaml",
                organization_id=str(agent.organization_id) if agent.organization_id else None,
                roles=agent_roles_by_agent.get(str(agent.id), []),
                access_level=agent.access_level.value if agent.access_level else "role_based",
            )
            for agent in agents_list
            if not agent.is_system  # Exclude system agents
        },
        apps={
            app.name: ManifestApp(
                id=str(app.id),
                path=f"{(app.repo_path or f'apps/{app.slug}').rstrip('/')}/app.yaml",
                slug=app.slug,
                organization_id=str(app.organization_id) if app.organization_id else None,
                roles=app_roles_by_app.get(str(app.id), []),
                access_level=app.access_level if app.access_level else "authenticated",
            )
            for app in apps_list
        },
    )

    logger.info(
        f"Generated manifest: {len(manifest.workflows)} workflows, "
        f"{len(manifest.forms)} forms, {len(manifest.agents)} agents, "
        f"{len(manifest.apps)} apps, {len(manifest.integrations)} integrations, "
        f"{len(manifest.configs)} configs, {len(manifest.tables)} tables, "
        f"{len(manifest.events)} events"
    )

    return manifest


def _build_event_source_manifest(
    es: EventSource,
    schedule_by_source: dict[str, ScheduleSource],
    webhook_by_source: dict[str, WebhookSource],
    subs_by_source: dict[str, list[EventSubscription]],
) -> ManifestEventSource:
    """Build a ManifestEventSource from ORM objects."""
    es_id = str(es.id)

    # Schedule config
    sched = schedule_by_source.get(es_id)
    cron_expression = sched.cron_expression if sched else None
    tz = sched.timezone if sched else None
    schedule_enabled = sched.enabled if sched else None

    # Webhook config (exclude external state: external_id, state, expires_at)
    wh = webhook_by_source.get(es_id)
    adapter_name = wh.adapter_name if wh else None
    webhook_integration_id = str(wh.integration_id) if wh and wh.integration_id else None
    webhook_config = wh.config if wh and wh.config else None

    # Subscriptions
    subs = subs_by_source.get(es_id, [])

    return ManifestEventSource(
        id=es_id,
        source_type=es.source_type if isinstance(es.source_type, str) else es.source_type.value,
        organization_id=str(es.organization_id) if es.organization_id else None,
        is_active=es.is_active,
        cron_expression=cron_expression,
        timezone=tz,
        schedule_enabled=schedule_enabled,
        adapter_name=adapter_name,
        webhook_integration_id=webhook_integration_id,
        webhook_config=webhook_config,
        subscriptions=[
            ManifestEventSubscription(
                id=str(sub.id),
                workflow_id=str(sub.workflow_id),
                event_type=sub.event_type,
                filter_expression=sub.filter_expression,
                input_mapping=sub.input_mapping,
                is_active=sub.is_active,
            )
            for sub in subs
        ],
    )
