"""
Contract tests for Forms API models
Tests Pydantic validation rules for request/response models
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.models.models import (
    CreateFormRequest,
    Form,
    FormField,
    FormFieldType,
    FormSchema,
    UpdateFormRequest,
)


# Note: Models use snake_case (e.g., workflow_id, form_schema, is_global)
# This matches the OpenAPI/TypeScript schema


class TestCreateFormRequest:
    """Test validation for CreateFormRequest model"""

    def test_valid_create_form_request(self):
        """Test valid create form request"""
        request = CreateFormRequest(
            name="Customer Onboarding",
            workflow_id="00000000-0000-0000-0000-000000000001",
            form_schema=FormSchema(
                fields=[
                    FormField(
                        name="company_name",
                        label="Company Name",
                        type=FormFieldType.TEXT,
                        required=True
                    )
                ]
            )
        )
        assert request.name == "Customer Onboarding"
        assert request.workflow_id == "00000000-0000-0000-0000-000000000001"
        assert len(request.form_schema.fields) == 1
        assert request.is_global is False  # Default

    def test_create_form_with_global_flag(self):
        """Test creating a global form"""
        request = CreateFormRequest(
            name="Global Template",
            workflow_id="00000000-0000-0000-0000-000000000002",
            form_schema=FormSchema(fields=[]),
            is_global=True
        )
        assert request.is_global is True

    def test_create_form_with_description(self):
        """Test creating form with optional description"""
        request = CreateFormRequest(
            name="Test Form",
            workflow_id="00000000-0000-0000-0000-000000000003",
            form_schema=FormSchema(fields=[]),
            description="This is a test form"
        )
        assert request.description == "This is a test form"

    def test_missing_required_name(self):
        """Test that name is required"""
        with pytest.raises(ValidationError) as exc_info:
            CreateFormRequest(
                workflow_id="00000000-0000-0000-0000-000000000001",
                form_schema=FormSchema(fields=[])
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) and e["type"] == "missing" for e in errors)

    def test_missing_required_workflow_id(self):
        """Test that workflow_id is required"""
        with pytest.raises(ValidationError) as exc_info:
            CreateFormRequest(
                name="Test Form",
                form_schema=FormSchema(fields=[])
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("workflow_id",) and e["type"] == "missing" for e in errors)

    def test_missing_required_form_schema(self):
        """Test that form_schema is required"""
        with pytest.raises(ValidationError) as exc_info:
            CreateFormRequest(
                name="Test Form",
                workflow_id="00000000-0000-0000-0000-000000000001"
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("form_schema",) and e["type"] == "missing" for e in errors)


class TestUpdateFormRequest:
    """Test validation for UpdateFormRequest model"""

    def test_valid_update_form_request_all_fields(self):
        """Test valid update form request with all fields"""
        request = UpdateFormRequest(
            name="Updated Form",
            description="Updated description",
            workflow_id="00000000-0000-0000-0000-000000000001",
            form_schema=FormSchema(
                fields=[
                    FormField(
                        name="field1",
                        label="Field 1",
                        type=FormFieldType.TEXT,
                        required=True
                    )
                ]
            ),
            is_active=False
        )
        assert request.name == "Updated Form"
        assert request.description == "Updated description"
        assert request.is_active is False

    def test_update_form_request_partial(self):
        """Test update with only some fields"""
        request = UpdateFormRequest(
            name="New Name"
        )
        assert request.name == "New Name"
        assert request.description is None
        assert request.workflow_id is None
        assert request.form_schema is None

    def test_update_form_request_empty_valid(self):
        """Test that update request can be empty (all optional)"""
        request = UpdateFormRequest()
        assert request.name is None
        assert request.description is None
        assert request.workflow_id is None
        assert request.form_schema is None
        assert request.is_active is None

    def test_update_form_request_activate(self):
        """Test activating a form via update"""
        request = UpdateFormRequest(is_active=True)
        assert request.is_active is True

    def test_update_form_request_deactivate(self):
        """Test deactivating a form via update"""
        request = UpdateFormRequest(is_active=False)
        assert request.is_active is False


class TestFormSchema:
    """Test validation for FormSchema model"""

    def test_valid_form_schema_with_fields(self):
        """Test valid form schema with multiple fields"""
        schema = FormSchema(
            fields=[
                FormField(
                    name="field1",
                    label="Field 1",
                    type=FormFieldType.TEXT,
                    required=True
                ),
                FormField(
                    name="field2",
                    label="Field 2",
                    type=FormFieldType.NUMBER,
                    required=False
                )
            ]
        )
        assert len(schema.fields) == 2
        assert schema.fields[0].name == "field1"
        assert schema.fields[1].type == FormFieldType.NUMBER

    def test_empty_form_schema(self):
        """Test form schema with no fields"""
        schema = FormSchema(fields=[])
        assert len(schema.fields) == 0

    def test_missing_fields_array(self):
        """Test that fields array is required"""
        with pytest.raises(ValidationError) as exc_info:
            FormSchema()

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("fields",) and e["type"] == "missing" for e in errors)


class TestFormField:
    """Test validation for FormField model"""

    def test_valid_text_field(self):
        """Test valid text field"""
        field = FormField(
            name="company_name",
            label="Company Name",
            type=FormFieldType.TEXT,
            required=True
        )
        assert field.name == "company_name"
        assert field.label == "Company Name"
        assert field.type == FormFieldType.TEXT
        assert field.required is True

    def test_valid_number_field(self):
        """Test valid number field"""
        field = FormField(
            name="employee_count",
            label="Employee Count",
            type=FormFieldType.NUMBER,
            required=False
        )
        assert field.type == FormFieldType.NUMBER
        assert field.required is False

    def test_valid_email_field(self):
        """Test valid email field"""
        field = FormField(
            name="contact_email",
            label="Contact Email",
            type=FormFieldType.EMAIL,
            required=True
        )
        assert field.type == FormFieldType.EMAIL

    def test_valid_select_field(self):
        """Test valid select field"""
        field = FormField(
            name="region",
            label="Region",
            type=FormFieldType.SELECT,
            required=True
        )
        assert field.type == FormFieldType.SELECT

    def test_valid_textarea_field(self):
        """Test valid textarea field"""
        field = FormField(
            name="description",
            label="Description",
            type=FormFieldType.TEXTAREA,
            required=False
        )
        assert field.type == FormFieldType.TEXTAREA

    def test_field_with_validation(self):
        """Test field with validation object"""
        field = FormField(
            name="age",
            label="Age",
            type=FormFieldType.NUMBER,
            required=True,
            validation={"min": 0, "max": 120}
        )
        assert field.validation == {"min": 0, "max": 120}

    def test_field_with_data_provider(self):
        """Test field with data_provider string"""
        field = FormField(
            name="organization",
            label="Organization",
            type=FormFieldType.SELECT,
            required=True,
            data_provider="msgraph_organizations"
        )
        assert field.data_provider == "msgraph_organizations"

    def test_field_defaults(self):
        """Test that optional fields have proper defaults"""
        field = FormField(
            name="test",
            label="Test",
            type=FormFieldType.TEXT
        )
        assert field.required is False  # Default
        assert field.validation is None
        assert field.data_provider is None

    def test_missing_required_name(self):
        """Test that name is required"""
        with pytest.raises(ValidationError) as exc_info:
            FormField(
                label="Test",
                type=FormFieldType.TEXT
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) and e["type"] == "missing" for e in errors)

    def test_missing_required_label_for_input_fields(self):
        """Test that label is required for input fields (text, select, etc.)"""
        with pytest.raises(ValidationError) as exc_info:
            FormField(
                name="test",
                type=FormFieldType.TEXT
            )

        errors = exc_info.value.errors()
        # Now raises a value_error from model_validator (not a missing field error)
        assert any("label is required" in str(e.get("msg", "")) for e in errors)

    def test_label_not_required_for_markdown(self):
        """Test that label is NOT required for markdown display fields"""
        # Markdown fields use 'content' instead of 'label'
        field = FormField(
            name="info",
            type=FormFieldType.MARKDOWN,
            content="## Welcome\n\nThis is markdown content."
        )
        assert field.label is None
        assert field.content == "## Welcome\n\nThis is markdown content."

    def test_content_required_for_markdown(self):
        """Test that content is required for markdown fields"""
        with pytest.raises(ValidationError) as exc_info:
            FormField(
                name="info",
                type=FormFieldType.MARKDOWN
            )

        errors = exc_info.value.errors()
        assert any("content is required" in str(e.get("msg", "")) for e in errors)

    def test_missing_required_type(self):
        """Test that type is required"""
        with pytest.raises(ValidationError) as exc_info:
            FormField(
                name="test",
                label="Test"
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("type",) and e["type"] == "missing" for e in errors)

    def test_invalid_field_type(self):
        """Test that type must be a valid enum value"""
        with pytest.raises(ValidationError) as exc_info:
            FormField(
                name="test",
                label="Test",
                type="invalid_type"
            )

        errors = exc_info.value.errors()
        assert any("type" in str(e) for e in errors)


class TestFormResponse:
    """Test Form response model structure"""

    def test_valid_form_response(self):
        """Test valid form response"""
        form = Form(
            id="form-123",
            org_id="org-456",
            name="Test Form",
            workflow_id="00000000-0000-0000-0000-000000000001",
            form_schema=FormSchema(
                fields=[
                    FormField(
                        name="field1",
                        label="Field 1",
                        type=FormFieldType.TEXT,
                        required=True
                    )
                ]
            ),
            is_active=True,
            is_global=False,
            created_by="user-789",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        assert form.id == "form-123"
        assert form.org_id == "org-456"
        assert form.name == "Test Form"
        assert form.is_active is True
        assert form.is_global is False

    def test_form_response_with_description(self):
        """Test form response with optional description"""
        form = Form(
            id="form-123",
            org_id="org-456",
            name="Test Form",
            description="Test description",
            workflow_id="00000000-0000-0000-0000-000000000001",
            form_schema=FormSchema(fields=[]),
            is_active=True,
            is_global=False,
            created_by="user-789",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        assert form.description == "Test description"

    def test_global_form_response(self):
        """Test global form response"""
        form = Form(
            id="form-123",
            org_id="GLOBAL",
            name="Global Form",
            workflow_id="00000000-0000-0000-0000-000000000001",
            form_schema=FormSchema(fields=[]),
            is_active=True,
            is_global=True,
            created_by="user-789",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        assert form.org_id == "GLOBAL"
        assert form.is_global is True

    def test_form_defaults(self):
        """Test that form fields have proper defaults"""
        form = Form(
            id="form-123",
            org_id="org-456",
            name="Test Form",
            workflow_id="00000000-0000-0000-0000-000000000001",
            form_schema=FormSchema(fields=[]),
            created_by="user-789",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        assert form.is_active is True  # Default
        assert form.is_global is False  # Default
        assert form.description is None

    def test_form_missing_required_fields(self):
        """Test that all required fields must be present"""
        with pytest.raises(ValidationError) as exc_info:
            Form(
                id="form-123",
                org_id="org-456",
                name="Test Form"
                # Missing: form_schema, created_by, created_at, updated_at
            )

        errors = exc_info.value.errors()
        required_fields = {"form_schema", "created_by", "created_at", "updated_at"}
        missing_fields = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert required_fields.issubset(missing_fields)

    def test_form_serialization(self):
        """Test that form can be serialized to dict/JSON"""
        form = Form(
            id="form-123",
            org_id="org-456",
            name="Test Form",
            workflow_id="00000000-0000-0000-0000-000000000001",
            form_schema=FormSchema(
                fields=[
                    FormField(
                        name="field1",
                        label="Field 1",
                        type=FormFieldType.TEXT,
                        required=True
                    )
                ]
            ),
            is_active=True,
            is_global=False,
            created_by="user-789",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        form_dict = form.model_dump()
        assert "id" in form_dict
        assert "org_id" in form_dict
        assert "name" in form_dict
        assert "workflow_id" in form_dict
        assert "form_schema" in form_dict
        assert "is_active" in form_dict
        assert "is_global" in form_dict
        assert "created_by" in form_dict
        assert "created_at" in form_dict
        assert "updated_at" in form_dict

    def test_form_json_serialization(self):
        """Test that form can be serialized to JSON mode"""
        form = Form(
            id="form-123",
            org_id="org-456",
            name="Test Form",
            workflow_id="00000000-0000-0000-0000-000000000001",
            form_schema=FormSchema(fields=[]),
            is_active=True,
            is_global=False,
            created_by="user-789",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        form_dict = form.model_dump(mode="json")
        assert isinstance(form_dict["created_at"], str)  # datetime -> ISO string
        assert isinstance(form_dict["updated_at"], str)  # datetime -> ISO string
