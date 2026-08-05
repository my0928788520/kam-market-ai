import pytest
from kam_market_ai.public_deployment import AllowedFrameAncestorsValidator, DeploymentMode, EmbedRouteConfig, HealthCheckProvider, PublicEmbedConfig, ReadinessProvider

def test_public_embed_defaults_are_read_only_and_deterministic():
    config=PublicEmbedConfig(); assert config.deployment_mode is DeploymentMode.READ_ONLY
    assert "frame-ancestors 'self'" in config.content_security_policy and "*" not in config.content_security_policy
    assert EmbedRouteConfig().allowed_instruments == ("TX","MTX","TMF")

@pytest.mark.parametrize("value", ["*","http://blog.example","https://localhost","https://blog.example/path","https://blog.example?a=1"])
def test_invalid_ancestors_fail_closed(value):
    with pytest.raises(ValueError): AllowedFrameAncestorsValidator.validate((value,))

def test_health_and_readiness_never_expose_runtime_or_credentials():
    assert HealthCheckProvider().payload()=={"status":"ok","service":"kam-market-ai","mode":"read-only"}
    assert ReadinessProvider().payload()=={"status":"ready","service":"kam-market-ai","mode":"read-only"}
