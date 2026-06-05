"""Application.app_model discriminator (v2 standalone app model, criterion 12).

inline_v1 (default, legacy) vs standalone_v2. All existing apps default inline_v1.
"""
from __future__ import annotations

from src.models.orm.applications import Application


def test_application_has_app_model_default_inline() -> None:
    cols = Application.__table__.columns
    assert "app_model" in cols
    assert cols["app_model"].default.arg == "inline_v1"
    assert cols["app_model"].server_default.arg == "inline_v1"
