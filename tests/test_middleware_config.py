import importlib


def test_cors_origins_default_to_local_development(monkeypatch):
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    module = importlib.reload(importlib.import_module("src.config.middleware_config"))

    assert module.middleware_config.CORS_ALLOW_ORIGINS == ["http://localhost:8000"]


def test_cors_origins_parse_comma_separated_env(monkeypatch):
    monkeypatch.setenv(
        "CORS_ALLOW_ORIGINS",
        "https://example.com, https://admin.example.com",
    )
    module = importlib.reload(importlib.import_module("src.config.middleware_config"))

    assert module.middleware_config.CORS_ALLOW_ORIGINS == [
        "https://example.com",
        "https://admin.example.com",
    ]
