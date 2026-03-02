"""Tests for Application.repo_prefix property."""
from src.models.orm.applications import Application


class TestApplicationRepoPrefix:
    def test_uses_repo_path_when_set(self):
        app = Application(slug="dashboard", repo_path="custom/dashboard")
        assert app.repo_prefix == "custom/dashboard/"

    def test_falls_back_to_apps_slug(self):
        app = Application(slug="dashboard", repo_path=None)
        assert app.repo_prefix == "apps/dashboard/"

    def test_strips_trailing_slash(self):
        app = Application(slug="dashboard", repo_path="custom/dashboard/")
        assert app.repo_prefix == "custom/dashboard/"

    def test_empty_string_repo_path_falls_back(self):
        app = Application(slug="dashboard", repo_path="")
        assert app.repo_prefix == "apps/dashboard/"
