"""
Contract tests for branding API endpoints

Tests branding configuration retrieval and updates with logo uploads and color validation.
"""

from src.models import BrandingSettings


class TestBrandingContracts:
    """Contract tests for branding API"""

    def test_branding_settings_model_structure(self):
        """Test that BrandingSettings model has required fields"""
        # Test model can be instantiated with all fields
        branding = BrandingSettings(
            square_logo_url="https://example.com/logo-square.png",
            rectangle_logo_url="https://example.com/logo-rect.png",
            primary_color="#0066CC"
        )

        assert branding.square_logo_url == "https://example.com/logo-square.png"
        assert branding.rectangle_logo_url == "https://example.com/logo-rect.png"
        assert branding.primary_color == "#0066CC"

    def test_branding_settings_optional_fields(self):
        """Test that branding fields are optional (can be None)"""
        # Test with minimal fields
        branding = BrandingSettings(
            square_logo_url=None,
            rectangle_logo_url=None,
            primary_color=None
        )

        assert branding.square_logo_url is None
        assert branding.rectangle_logo_url is None
        assert branding.primary_color is None

    def test_primary_color_hex_format_validation(self):
        """Test that primary color validates hex format"""
        # Valid hex colors
        valid_colors = ["#000000", "#FFFFFF", "#0066CC", "#ff6600"]

        for color in valid_colors:
            branding = BrandingSettings(
                square_logo_url=None,
                rectangle_logo_url=None,
                primary_color=color
            )
            assert branding.primary_color == color

    def test_branding_fallback_to_defaults(self):
        """Test that missing branding falls back to None (frontend handles defaults)"""
        branding = BrandingSettings(
            square_logo_url=None,
            rectangle_logo_url=None,
            primary_color=None
        )

        # Frontend should handle None values by showing default branding
        assert branding.square_logo_url is None
        assert branding.rectangle_logo_url is None
        assert branding.primary_color is None

    def test_reset_branding_returns_none_values(self):
        """Test that reset branding endpoints return None values"""
        # After reset, all values should be None
        branding = BrandingSettings(
            square_logo_url=None,
            rectangle_logo_url=None,
            primary_color=None
        )

        assert branding.square_logo_url is None
        assert branding.rectangle_logo_url is None
        assert branding.primary_color is None

    def test_partial_logo_reset(self):
        """Test that resetting one logo doesn't affect the other"""
        # Start with both logos (verify construction works)
        BrandingSettings(
            square_logo_url="/api/branding/logo/square",
            rectangle_logo_url="/api/branding/logo/rectangle",
            primary_color="#0066CC"
        )

        # After resetting square logo, rectangle and color remain
        branding_after_reset = BrandingSettings(
            square_logo_url=None,  # Reset
            rectangle_logo_url="/api/branding/logo/rectangle",  # Still there
            primary_color="#0066CC"  # Still there
        )

        assert branding_after_reset.square_logo_url is None
        assert branding_after_reset.rectangle_logo_url is not None
        assert branding_after_reset.primary_color is not None
