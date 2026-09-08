from dataclasses import replace

import pytest
from pydantic import ValidationError

from app import runtime_settings
from app.config import settings
from app.providers import ProviderError, validate_provider_base_url
from app.runtime_settings import ProviderRoleUpdate


def test_runtime_update_accepts_arbitrary_provider_and_keeps_key_secret(monkeypatch) -> None:
    configured = replace(settings, extraction_base_url="", extraction_api_key="")
    monkeypatch.setattr(runtime_settings, "settings", configured)

    update = ProviderRoleUpdate(
        base_url="https://inference.example/v1",
        api_key="runtime-secret",
        model="company/unseen-model-2030",
        timeout_seconds=47,
        max_output_tokens=3210,
    )
    runtime_settings.apply_provider_update("extraction", update)

    assert configured.extraction_base_url == "https://inference.example/v1"
    assert configured.extraction_model == "company/unseen-model-2030"
    assert configured.extraction_api_key == "runtime-secret"
    assert "runtime-secret" not in repr(update)


def test_runtime_provider_network_boundary_rejects_credential_and_ssrf_urls() -> None:
    with pytest.raises(ProviderError, match="credentials"):
        validate_provider_base_url("https://user:secret@example.com/v1")
    with pytest.raises(ProviderError, match="HTTPS"):
        validate_provider_base_url("http://provider.example/v1")
    with pytest.raises(ProviderError, match="Private"):
        validate_provider_base_url("https://169.254.169.254/latest")
    validate_provider_base_url("http://localhost:11434/v1")


def test_runtime_provider_path_cannot_be_an_absolute_cross_host_url() -> None:
    with pytest.raises(ValidationError, match="origin-relative"):
        ProviderRoleUpdate(path="https://attacker.example/chat/completions")
