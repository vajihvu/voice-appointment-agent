"""Tests for configuration loading, YAML parsing, and PII masking."""

from app.core.config import get_settings
from app.core.logging import mask_phone_number


def test_settings_load_business_config():
    """Verify business_config.yaml loads expected clinic properties."""
    settings = get_settings()
    assert settings.business.get("name") == "BrightSmile Dental Clinic"
    assert settings.business.get("type") == "dental_clinic"
    assert len(settings.services) >= 3


def test_prompts_yaml_loaded():
    """Verify multilingual prompts are present in configuration."""
    settings = get_settings()
    assert "en" in settings.prompts.get("languages", {})
    assert "hi" in settings.prompts.get("languages", {})
    assert "kn" in settings.prompts.get("languages", {})


def test_pii_masking():
    """Verify caller phone numbers are masked properly."""
    assert mask_phone_number("+919876543210") == "+9198*****210"
    assert mask_phone_number("9876543210") == "98*****210"
    assert mask_phone_number("") == ""
    assert mask_phone_number(None) == ""
