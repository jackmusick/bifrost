"""
Tests for portable workflow ref serialization.

These tests verify that:
1. @field_serializer transforms workflow UUIDs to portable refs when context provided
2. Without context, UUIDs are preserved as-is
3. Form, Agent, and nested FormField models all support portable refs
"""

from datetime import datetime
from uuid import uuid4

from src.models.contracts.forms import FormPublic, FormField, FormSchema
from src.models.contracts.agents import AgentPublic
from src.models.enums import FormFieldType, AgentAccessLevel


class TestFormPublicPortableRefs:
    """Test FormPublic serializes workflow refs with context."""

    def test_workflow_id_transformed_with_context(self):
        """workflow_id should be transformed when workflow_map provided."""
        workflow_uuid = str(uuid4())
        portable_ref = "workflows/my_module.py::my_function"

        form = FormPublic(
            id=uuid4(),
            name="Test Form",
            workflow_id=workflow_uuid,
            is_active=True,
        )

        # Serialize with workflow_map context
        result = form.model_dump(
            mode="json",
            context={"workflow_map": {workflow_uuid: portable_ref}}
        )

        assert result["workflow_id"] == portable_ref

    def test_launch_workflow_id_transformed_with_context(self):
        """launch_workflow_id should be transformed when workflow_map provided."""
        workflow_uuid = str(uuid4())
        portable_ref = "workflows/launcher.py::launch"

        form = FormPublic(
            id=uuid4(),
            name="Test Form",
            launch_workflow_id=workflow_uuid,
            is_active=True,
        )

        result = form.model_dump(
            mode="json",
            context={"workflow_map": {workflow_uuid: portable_ref}}
        )

        assert result["launch_workflow_id"] == portable_ref

    def test_workflow_id_preserved_without_context(self):
        """workflow_id should remain UUID when no context provided."""
        workflow_uuid = str(uuid4())

        form = FormPublic(
            id=uuid4(),
            name="Test Form",
            workflow_id=workflow_uuid,
            is_active=True,
        )

        # Serialize without context
        result = form.model_dump(mode="json")

        assert result["workflow_id"] == workflow_uuid

    def test_unknown_uuid_preserved(self):
        """UUIDs not in workflow_map should be preserved as-is."""
        workflow_uuid = str(uuid4())
        other_uuid = str(uuid4())
        portable_ref = "workflows/other.py::func"

        form = FormPublic(
            id=uuid4(),
            name="Test Form",
            workflow_id=workflow_uuid,
            is_active=True,
        )

        # workflow_map doesn't contain our UUID
        result = form.model_dump(
            mode="json",
            context={"workflow_map": {other_uuid: portable_ref}}
        )

        # Should preserve original UUID
        assert result["workflow_id"] == workflow_uuid


class TestFormFieldPortableRefs:
    """Test FormField serializes data_provider_id with context."""

    def test_data_provider_id_transformed_with_context(self):
        """data_provider_id should be transformed when workflow_map provided."""
        provider_uuid = uuid4()
        portable_ref = "workflows/data_provider.py::get_options"

        field = FormField(
            name="country",
            label="Country",
            type=FormFieldType.SELECT,
            data_provider_id=provider_uuid,
        )

        result = field.model_dump(
            mode="json",
            context={"workflow_map": {str(provider_uuid): portable_ref}}
        )

        assert result["data_provider_id"] == portable_ref

    def test_data_provider_id_preserved_without_context(self):
        """data_provider_id should remain UUID when no context provided."""
        provider_uuid = uuid4()

        field = FormField(
            name="country",
            label="Country",
            type=FormFieldType.SELECT,
            data_provider_id=provider_uuid,
        )

        result = field.model_dump(mode="json")

        # Should be stringified UUID
        assert result["data_provider_id"] == str(provider_uuid)


class TestFormSchemaNestedRefs:
    """Test that nested FormField refs are transformed in FormSchema."""

    def test_nested_data_provider_transformed(self):
        """data_provider_id in nested FormField should be transformed."""
        provider_uuid = uuid4()
        portable_ref = "workflows/data_provider.py::get_options"

        schema = FormSchema(
            fields=[
                FormField(
                    name="text_field",
                    label="Text",
                    type=FormFieldType.TEXT,
                ),
                FormField(
                    name="country",
                    label="Country",
                    type=FormFieldType.SELECT,
                    data_provider_id=provider_uuid,
                ),
            ]
        )

        result = schema.model_dump(
            mode="json",
            context={"workflow_map": {str(provider_uuid): portable_ref}}
        )

        # First field has no data_provider_id (or it's None)
        assert result["fields"][0].get("data_provider_id") is None

        # Second field should have transformed ref
        assert result["fields"][1]["data_provider_id"] == portable_ref


class TestAgentPublicPortableRefs:
    """Test AgentPublic serializes tool_ids with context."""

    def test_tool_ids_transformed_with_context(self):
        """tool_ids should be transformed when workflow_map provided."""
        tool1_uuid = str(uuid4())
        tool2_uuid = str(uuid4())
        ref1 = "workflows/tool1.py::execute"
        ref2 = "workflows/tool2.py::run"

        agent = AgentPublic(
            id=uuid4(),
            name="Test Agent",
            system_prompt="You are helpful.",
            channels=["chat"],
            access_level=AgentAccessLevel.AUTHENTICATED,
            is_active=True,
            created_by="test",
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 1),
            tool_ids=[tool1_uuid, tool2_uuid],
        )

        result = agent.model_dump(
            mode="json",
            context={"workflow_map": {tool1_uuid: ref1, tool2_uuid: ref2}}
        )

        assert result["tool_ids"] == [ref1, ref2]

    def test_tool_ids_preserved_without_context(self):
        """tool_ids should remain UUIDs when no context provided."""
        tool_uuid = str(uuid4())

        agent = AgentPublic(
            id=uuid4(),
            name="Test Agent",
            system_prompt="You are helpful.",
            channels=["chat"],
            access_level=AgentAccessLevel.AUTHENTICATED,
            is_active=True,
            created_by="test",
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 1),
            tool_ids=[tool_uuid],
        )

        result = agent.model_dump(mode="json")

        assert result["tool_ids"] == [tool_uuid]

    def test_partial_tool_ids_transformation(self):
        """Only tool_ids in workflow_map should be transformed."""
        tool1_uuid = str(uuid4())
        tool2_uuid = str(uuid4())
        ref1 = "workflows/tool1.py::execute"

        agent = AgentPublic(
            id=uuid4(),
            name="Test Agent",
            system_prompt="You are helpful.",
            channels=["chat"],
            access_level=AgentAccessLevel.AUTHENTICATED,
            is_active=True,
            created_by="test",
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 1),
            tool_ids=[tool1_uuid, tool2_uuid],
        )

        # Only tool1 is in the map
        result = agent.model_dump(
            mode="json",
            context={"workflow_map": {tool1_uuid: ref1}}
        )

        # tool1 transformed, tool2 preserved
        assert result["tool_ids"] == [ref1, tool2_uuid]

    def test_empty_tool_ids_with_context(self):
        """Empty tool_ids should remain empty."""
        agent = AgentPublic(
            id=uuid4(),
            name="Test Agent",
            system_prompt="You are helpful.",
            channels=["chat"],
            access_level=AgentAccessLevel.AUTHENTICATED,
            is_active=True,
            created_by="test",
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 1),
            tool_ids=[],
        )

        result = agent.model_dump(
            mode="json",
            context={"workflow_map": {"some-uuid": "some-ref"}}
        )

        assert result["tool_ids"] == []


# =============================================================================
# Round-Trip Tests (Export -> Import)
# =============================================================================


class TestFormRoundTripSerialization:
    """Test form export/import round-trip with portable refs (Task 2C.1)."""

    def test_form_round_trip_serialization(self):
        """Verify form can be exported and re-imported with portable refs."""
        from src.services.file_storage.ref_translation import transform_path_refs_to_uuids

        # Setup: workflow UUIDs and portable refs
        workflow_uuid = str(uuid4())
        launch_workflow_uuid = str(uuid4())
        data_provider_uuid = uuid4()

        portable_workflow_ref = "workflows/submit_form.py::process"
        portable_launch_ref = "workflows/startup.py::init"
        portable_data_provider_ref = "workflows/providers.py::get_countries"

        # Create form with all workflow ref types
        form = FormPublic(
            id=uuid4(),
            name="Test Form",
            description="A form with all workflow ref types",
            workflow_id=workflow_uuid,
            launch_workflow_id=launch_workflow_uuid,
            is_active=True,
            form_schema=FormSchema(
                fields=[
                    FormField(
                        name="text_field",
                        label="Text",
                        type=FormFieldType.TEXT,
                    ),
                    FormField(
                        name="country",
                        label="Country",
                        type=FormFieldType.SELECT,
                        data_provider_id=data_provider_uuid,
                    ),
                ]
            ),
        )

        # Export with workflow_map context
        workflow_map = {
            workflow_uuid: portable_workflow_ref,
            launch_workflow_uuid: portable_launch_ref,
            str(data_provider_uuid): portable_data_provider_ref,
        }
        exported = form.model_dump(mode="json", context={"workflow_map": workflow_map})

        # Verify portable refs in export
        assert exported["workflow_id"] == portable_workflow_ref
        assert exported["launch_workflow_id"] == portable_launch_ref
        assert exported["form_schema"]["fields"][1]["data_provider_id"] == portable_data_provider_ref

        # Simulate import - build the reverse map
        ref_to_uuid = {
            portable_workflow_ref: workflow_uuid,
            portable_launch_ref: launch_workflow_uuid,
            portable_data_provider_ref: str(data_provider_uuid),
        }

        # Define which fields contain workflow refs (as they would be in _export metadata)
        workflow_ref_fields = [
            "workflow_id",
            "launch_workflow_id",
            "form_schema.fields.1.data_provider_id",
        ]

        # Transform portable refs back to UUIDs
        transform_path_refs_to_uuids(exported, workflow_ref_fields, ref_to_uuid)

        # Verify UUIDs are restored
        assert exported["workflow_id"] == workflow_uuid
        assert exported["launch_workflow_id"] == launch_workflow_uuid
        assert exported["form_schema"]["fields"][1]["data_provider_id"] == str(data_provider_uuid)

        # Verify non-ref fields are preserved
        assert exported["name"] == "Test Form"
        assert exported["form_schema"]["fields"][0]["name"] == "text_field"
        assert exported["form_schema"]["fields"][0]["label"] == "Text"

    def test_form_with_multiple_data_providers(self):
        """Verify form with multiple data provider fields exports/imports correctly."""
        from src.services.file_storage.ref_translation import transform_path_refs_to_uuids

        provider1_uuid = uuid4()
        provider2_uuid = uuid4()
        ref1 = "workflows/providers.py::get_countries"
        ref2 = "workflows/providers.py::get_cities"

        form = FormPublic(
            id=uuid4(),
            name="Multi-Provider Form",
            is_active=True,
            form_schema=FormSchema(
                fields=[
                    FormField(
                        name="country",
                        label="Country",
                        type=FormFieldType.SELECT,
                        data_provider_id=provider1_uuid,
                    ),
                    FormField(
                        name="city",
                        label="City",
                        type=FormFieldType.SELECT,
                        data_provider_id=provider2_uuid,
                    ),
                ]
            ),
        )

        workflow_map = {
            str(provider1_uuid): ref1,
            str(provider2_uuid): ref2,
        }
        exported = form.model_dump(mode="json", context={"workflow_map": workflow_map})

        # Verify both transformed
        assert exported["form_schema"]["fields"][0]["data_provider_id"] == ref1
        assert exported["form_schema"]["fields"][1]["data_provider_id"] == ref2

        # Import back
        ref_to_uuid = {ref1: str(provider1_uuid), ref2: str(provider2_uuid)}
        workflow_ref_fields = [
            "form_schema.fields.0.data_provider_id",
            "form_schema.fields.1.data_provider_id",
        ]
        transform_path_refs_to_uuids(exported, workflow_ref_fields, ref_to_uuid)

        assert exported["form_schema"]["fields"][0]["data_provider_id"] == str(provider1_uuid)
        assert exported["form_schema"]["fields"][1]["data_provider_id"] == str(provider2_uuid)


class TestAgentRoundTripSerialization:
    """Test agent export/import round-trip with portable refs (Task 2C.2)."""

    def test_agent_round_trip_serialization(self):
        """Verify agent can be exported and re-imported with portable refs."""
        from src.services.file_storage.ref_translation import transform_path_refs_to_uuids

        tool1_uuid = str(uuid4())
        tool2_uuid = str(uuid4())
        tool3_uuid = str(uuid4())

        ref1 = "workflows/tools/search.py::search"
        ref2 = "workflows/tools/update.py::update"
        ref3 = "workflows/tools/delete.py::delete"

        agent = AgentPublic(
            id=uuid4(),
            name="Test Agent",
            description="An agent with tools",
            system_prompt="You are helpful.",
            channels=["chat"],
            access_level=AgentAccessLevel.AUTHENTICATED,
            is_active=True,
            created_by="test",
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 1),
            tool_ids=[tool1_uuid, tool2_uuid, tool3_uuid],
        )

        # Export with workflow_map
        workflow_map = {
            tool1_uuid: ref1,
            tool2_uuid: ref2,
            tool3_uuid: ref3,
        }
        exported = agent.model_dump(mode="json", context={"workflow_map": workflow_map})

        # Verify all tool refs transformed
        assert exported["tool_ids"] == [ref1, ref2, ref3]

        # Simulate import
        ref_to_uuid = {ref1: tool1_uuid, ref2: tool2_uuid, ref3: tool3_uuid}

        # For list fields, we need to transform each element
        # The transform_path_refs_to_uuids works on individual paths
        workflow_ref_fields = [
            "tool_ids.0",
            "tool_ids.1",
            "tool_ids.2",
        ]
        transform_path_refs_to_uuids(exported, workflow_ref_fields, ref_to_uuid)

        # Verify UUIDs restored
        assert exported["tool_ids"] == [tool1_uuid, tool2_uuid, tool3_uuid]

        # Verify other fields preserved
        assert exported["name"] == "Test Agent"
        assert exported["system_prompt"] == "You are helpful."

    def test_agent_with_empty_tool_ids_round_trip(self):
        """Verify agent with no tools exports/imports correctly."""
        from src.services.file_storage.ref_translation import transform_path_refs_to_uuids

        agent = AgentPublic(
            id=uuid4(),
            name="No-Tools Agent",
            system_prompt="You are helpful.",
            channels=["chat"],
            access_level=AgentAccessLevel.AUTHENTICATED,
            is_active=True,
            created_by="test",
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 1),
            tool_ids=[],
        )

        exported = agent.model_dump(
            mode="json",
            context={"workflow_map": {"some-uuid": "some-ref"}}
        )

        assert exported["tool_ids"] == []

        # Import with no refs to transform
        transform_path_refs_to_uuids(exported, [], {})
        assert exported["tool_ids"] == []


class TestAppRoundTripSerialization:
    """Test app/page export/import round-trip with portable refs (Task 2C.3)."""

    def test_page_definition_round_trip_serialization(self):
        """Verify PageDefinition with components exports/imports portable refs correctly."""
        from src.services.file_storage.ref_translation import transform_path_refs_to_uuids
        from src.models.contracts.app_components import (
            PageDefinition,
            LayoutContainer,
            ButtonComponent,
            ButtonProps,
            DataSourceConfig,
        )

        # Setup workflow UUIDs
        button_workflow_uuid = str(uuid4())
        launch_workflow_uuid = str(uuid4())
        data_source_workflow_uuid = str(uuid4())

        button_ref = "workflows/actions.py::submit"
        launch_ref = "workflows/init.py::load_data"
        data_source_ref = "workflows/data.py::fetch_items"

        # Create page with button component and data sources
        page = PageDefinition(
            id="page_1",
            title="Test Page",
            path="/test",
            layout=LayoutContainer(
                id="layout_1",
                type="column",
                children=[
                    ButtonComponent(
                        id="btn_1",
                        type="button",
                        props=ButtonProps(
                            label="Submit",
                            action_type="workflow",
                            workflow_id=button_workflow_uuid,
                        ),
                    ),
                ],
            ),
            data_sources=[
                DataSourceConfig(
                    id="ds_1",
                    type="workflow",
                    workflow_id=data_source_workflow_uuid,
                ),
            ],
            launch_workflow_id=launch_workflow_uuid,
        )

        # Export with workflow_map
        workflow_map = {
            button_workflow_uuid: button_ref,
            launch_workflow_uuid: launch_ref,
            data_source_workflow_uuid: data_source_ref,
        }
        exported = page.model_dump(mode="json", context={"workflow_map": workflow_map})

        # Verify portable refs in export
        assert exported["layout"]["children"][0]["props"]["workflow_id"] == button_ref
        assert exported["launch_workflow_id"] == launch_ref
        assert exported["data_sources"][0]["workflow_id"] == data_source_ref

        # Simulate import
        ref_to_uuid = {
            button_ref: button_workflow_uuid,
            launch_ref: launch_workflow_uuid,
            data_source_ref: data_source_workflow_uuid,
        }
        workflow_ref_fields = [
            "layout.children.0.props.workflow_id",
            "launch_workflow_id",
            "data_sources.0.workflow_id",
        ]
        transform_path_refs_to_uuids(exported, workflow_ref_fields, ref_to_uuid)

        # Verify UUIDs restored
        assert exported["layout"]["children"][0]["props"]["workflow_id"] == button_workflow_uuid
        assert exported["launch_workflow_id"] == launch_workflow_uuid
        assert exported["data_sources"][0]["workflow_id"] == data_source_workflow_uuid

        # Verify other fields preserved
        assert exported["title"] == "Test Page"
        assert exported["path"] == "/test"

    def test_page_with_data_table_row_actions(self):
        """Verify DataTable with row action workflows exports/imports correctly."""
        from src.services.file_storage.ref_translation import transform_path_refs_to_uuids
        from src.models.contracts.app_components import (
            PageDefinition,
            LayoutContainer,
            DataTableComponent,
            DataTableProps,
            TableColumn,
            TableAction,
            TableActionOnClick,
        )

        action_workflow_uuid = str(uuid4())
        action_ref = "workflows/actions.py::delete_row"

        page = PageDefinition(
            id="page_1",
            title="Data Page",
            path="/data",
            layout=LayoutContainer(
                id="layout_1",
                type="column",
                children=[
                    DataTableComponent(
                        id="table_1",
                        type="data-table",
                        props=DataTableProps(
                            data_source="items",
                            columns=[
                                TableColumn(key="name", header="Name"),
                            ],
                            row_actions=[
                                TableAction(
                                    label="Delete",
                                    on_click=TableActionOnClick(
                                        type="workflow",
                                        workflow_id=action_workflow_uuid,
                                    ),
                                ),
                            ],
                        ),
                    ),
                ],
            ),
        )

        workflow_map = {action_workflow_uuid: action_ref}
        exported = page.model_dump(mode="json", context={"workflow_map": workflow_map})

        # Verify nested workflow ref transformed
        assert exported["layout"]["children"][0]["props"]["row_actions"][0]["on_click"]["workflow_id"] == action_ref

        # Import back
        ref_to_uuid = {action_ref: action_workflow_uuid}
        workflow_ref_fields = [
            "layout.children.0.props.row_actions.0.on_click.workflow_id",
        ]
        transform_path_refs_to_uuids(exported, workflow_ref_fields, ref_to_uuid)

        assert exported["layout"]["children"][0]["props"]["row_actions"][0]["on_click"]["workflow_id"] == action_workflow_uuid

    def test_page_with_stat_card_onclick(self):
        """Verify StatCard with onClick workflow exports/imports correctly."""
        from src.services.file_storage.ref_translation import transform_path_refs_to_uuids
        from src.models.contracts.app_components import (
            PageDefinition,
            LayoutContainer,
            StatCardComponent,
            StatCardProps,
            StatCardOnClick,
        )

        workflow_uuid = str(uuid4())
        workflow_ref = "workflows/stats.py::drill_down"

        page = PageDefinition(
            id="page_1",
            title="Stats Page",
            path="/stats",
            layout=LayoutContainer(
                id="layout_1",
                type="column",
                children=[
                    StatCardComponent(
                        id="stat_1",
                        type="stat-card",
                        props=StatCardProps(
                            title="Total Users",
                            value="{{ data.user_count }}",
                            on_click=StatCardOnClick(
                                type="workflow",
                                workflow_id=workflow_uuid,
                            ),
                        ),
                    ),
                ],
            ),
        )

        workflow_map = {workflow_uuid: workflow_ref}
        exported = page.model_dump(mode="json", context={"workflow_map": workflow_map})

        assert exported["layout"]["children"][0]["props"]["on_click"]["workflow_id"] == workflow_ref

        ref_to_uuid = {workflow_ref: workflow_uuid}
        workflow_ref_fields = ["layout.children.0.props.on_click.workflow_id"]
        transform_path_refs_to_uuids(exported, workflow_ref_fields, ref_to_uuid)

        assert exported["layout"]["children"][0]["props"]["on_click"]["workflow_id"] == workflow_uuid


class TestMissingRefsGracefulDegradation:
    """Test graceful handling when refs can't be resolved during import (Task 2C.4)."""

    def test_unresolved_refs_stay_as_portable_strings(self):
        """Refs that can't be resolved should stay as portable ref strings."""
        from src.services.file_storage.ref_translation import transform_path_refs_to_uuids

        workflow_uuid = str(uuid4())
        portable_workflow_ref = "workflows/submit.py::process"
        portable_launch_ref = "workflows/missing.py::init"  # This one won't be in ref_to_uuid

        form = FormPublic(
            id=uuid4(),
            name="Test Form",
            workflow_id=workflow_uuid,
            launch_workflow_id=str(uuid4()),  # Will be exported as a ref
            is_active=True,
        )

        # Export with both refs mapped
        workflow_map = {
            workflow_uuid: portable_workflow_ref,
            form.launch_workflow_id: portable_launch_ref,
        }
        exported = form.model_dump(mode="json", context={"workflow_map": workflow_map})

        assert exported["workflow_id"] == portable_workflow_ref
        assert exported["launch_workflow_id"] == portable_launch_ref

        # Import with only partial ref_to_uuid map (missing launch_workflow ref)
        ref_to_uuid = {
            portable_workflow_ref: workflow_uuid,
            # portable_launch_ref intentionally missing
        }

        workflow_ref_fields = ["workflow_id", "launch_workflow_id"]
        unresolved = transform_path_refs_to_uuids(exported, workflow_ref_fields, ref_to_uuid)

        # workflow_id should be resolved
        assert exported["workflow_id"] == workflow_uuid

        # launch_workflow_id should remain as portable string (graceful degradation)
        assert exported["launch_workflow_id"] == portable_launch_ref

        # Unresolved refs should be reported
        assert len(unresolved) == 1
        assert unresolved[0].field == "launch_workflow_id"
        assert unresolved[0].ref == portable_launch_ref

    def test_partial_tool_ids_resolution(self):
        """Some tool_ids resolve, others remain as portable refs."""
        from src.services.file_storage.ref_translation import transform_path_refs_to_uuids

        tool1_uuid = str(uuid4())
        tool2_uuid = str(uuid4())
        ref1 = "workflows/tool1.py::execute"
        ref2 = "workflows/tool2.py::run"

        agent = AgentPublic(
            id=uuid4(),
            name="Test Agent",
            system_prompt="You are helpful.",
            channels=["chat"],
            access_level=AgentAccessLevel.AUTHENTICATED,
            is_active=True,
            created_by="test",
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 1),
            tool_ids=[tool1_uuid, tool2_uuid],
        )

        workflow_map = {tool1_uuid: ref1, tool2_uuid: ref2}
        exported = agent.model_dump(mode="json", context={"workflow_map": workflow_map})

        # Only provide mapping for tool1, not tool2
        ref_to_uuid = {ref1: tool1_uuid}

        workflow_ref_fields = ["tool_ids.0", "tool_ids.1"]
        unresolved = transform_path_refs_to_uuids(exported, workflow_ref_fields, ref_to_uuid)

        # tool1 resolved, tool2 remains as portable ref
        assert exported["tool_ids"][0] == tool1_uuid
        assert exported["tool_ids"][1] == ref2

        # One unresolved ref reported
        assert len(unresolved) == 1
        assert unresolved[0].field == "tool_ids.1"
        assert unresolved[0].ref == ref2

    def test_nested_component_unresolved_refs(self):
        """Nested component workflow refs that can't resolve stay as portable strings."""
        from src.services.file_storage.ref_translation import transform_path_refs_to_uuids
        from src.models.contracts.app_components import (
            PageDefinition,
            LayoutContainer,
            ButtonComponent,
            ButtonProps,
        )

        button1_uuid = str(uuid4())
        button2_uuid = str(uuid4())
        ref1 = "workflows/action1.py::execute"
        ref2 = "workflows/action2.py::run"

        page = PageDefinition(
            id="page_1",
            title="Test Page",
            path="/test",
            layout=LayoutContainer(
                id="layout_1",
                type="column",
                children=[
                    ButtonComponent(
                        id="btn_1",
                        type="button",
                        props=ButtonProps(
                            label="Button 1",
                            action_type="workflow",
                            workflow_id=button1_uuid,
                        ),
                    ),
                    ButtonComponent(
                        id="btn_2",
                        type="button",
                        props=ButtonProps(
                            label="Button 2",
                            action_type="workflow",
                            workflow_id=button2_uuid,
                        ),
                    ),
                ],
            ),
        )

        workflow_map = {button1_uuid: ref1, button2_uuid: ref2}
        exported = page.model_dump(mode="json", context={"workflow_map": workflow_map})

        # Only resolve button1
        ref_to_uuid = {ref1: button1_uuid}

        workflow_ref_fields = [
            "layout.children.0.props.workflow_id",
            "layout.children.1.props.workflow_id",
        ]
        unresolved = transform_path_refs_to_uuids(exported, workflow_ref_fields, ref_to_uuid)

        # button1 resolved, button2 stays as portable ref
        assert exported["layout"]["children"][0]["props"]["workflow_id"] == button1_uuid
        assert exported["layout"]["children"][1]["props"]["workflow_id"] == ref2

        assert len(unresolved) == 1
        assert unresolved[0].field == "layout.children.1.props.workflow_id"
        assert unresolved[0].ref == ref2

    def test_empty_ref_to_uuid_map(self):
        """All refs remain as portable strings when ref_to_uuid is empty."""
        from src.services.file_storage.ref_translation import transform_path_refs_to_uuids

        workflow_uuid = str(uuid4())
        portable_ref = "workflows/submit.py::process"

        form = FormPublic(
            id=uuid4(),
            name="Test Form",
            workflow_id=workflow_uuid,
            is_active=True,
        )

        workflow_map = {workflow_uuid: portable_ref}
        exported = form.model_dump(mode="json", context={"workflow_map": workflow_map})

        # Import with empty map - simulates new environment with no workflows yet
        unresolved = transform_path_refs_to_uuids(exported, ["workflow_id"], {})

        # Ref stays as portable string
        assert exported["workflow_id"] == portable_ref

        # Reported as unresolved
        assert len(unresolved) == 1
        assert unresolved[0].ref == portable_ref
