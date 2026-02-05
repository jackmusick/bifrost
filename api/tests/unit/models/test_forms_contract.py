"""
Contract tests for Forms API models
Tests Pydantic validation rules for request/response models
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.models import (
    CreateFormRequest,
    FormFieldType,
    FormSchema,
)
from src.models.contracts.forms import Form, FormField


# Note: Models use snake_case (e.g., workflow_id, form_schema, is_global)
# This matches the OpenAPI/TypeScript schema


class TestCreateFormRequest:
    """Test validation for CreateFormRequest model"""

    @pytest.mark.parametrize("missing_field", ["name", "workflow_id", "form_schema"])
    def test_missing_required_field(self, missing_field):
        """Test that each required field is enforced"""
        fields = {
            "name": "Test Form",
            "workflow_id": "00000000-0000-0000-0000-000000000001",
            "form_schema": FormSchema(fields=[]),
        }
        del fields[missing_field]
        with pytest.raises(ValidationError) as exc_info:
            CreateFormRequest(**fields)

        errors = exc_info.value.errors()
        assert any(e["loc"] == (missing_field,) and e["type"] == "missing" for e in errors)


class TestFormSchema:
    """Test validation for FormSchema model"""

    def test_missing_fields_array(self):
        """Test that fields array is required"""
        with pytest.raises(ValidationError) as exc_info:
            FormSchema()

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("fields",) and e["type"] == "missing" for e in errors)


class TestFormField:
    """Test validation for FormField model"""

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
