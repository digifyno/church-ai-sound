"""Tests for config.py CORS origin validation."""

import importlib
import sys
import pytest


def _load_config(cors_env: str):
    """Import config with a custom CORS_ORIGINS env var, bypassing the module cache."""
    import os
    # Remove cached module so env changes take effect
    sys.modules.pop("config", None)
    os.environ["CORS_ORIGINS"] = cors_env
    try:
        import config
        return config
    finally:
        del os.environ["CORS_ORIGINS"]
        sys.modules.pop("config", None)


def test_valid_http_origin_passes():
    cfg = _load_config("http://192.168.8.100:5050")
    assert cfg.SOCKETIO_CORS_ORIGINS == ["http://192.168.8.100:5050"]


def test_valid_https_origin_passes():
    cfg = _load_config("https://example.com")
    assert cfg.SOCKETIO_CORS_ORIGINS == ["https://example.com"]


def test_empty_hostname_rejected():
    """http:// with no host must be dropped (prevents ws:// wildcard in CSP)."""
    cfg = _load_config("http://")
    assert cfg.SOCKETIO_CORS_ORIGINS == []


def test_scheme_only_rejected():
    """Scheme with no netloc must be dropped."""
    cfg = _load_config("http://,https://")
    assert cfg.SOCKETIO_CORS_ORIGINS == []


def test_ftp_scheme_rejected():
    cfg = _load_config("ftp://evil.com")
    assert cfg.SOCKETIO_CORS_ORIGINS == []


def test_mixed_valid_and_invalid():
    """Valid origins are kept; invalid ones are silently dropped."""
    cfg = _load_config("http://192.168.8.100:5050,http://,ftp://evil.com,https://good.example.com")
    assert cfg.SOCKETIO_CORS_ORIGINS == [
        "http://192.168.8.100:5050",
        "https://good.example.com",
    ]


def test_default_origins_are_valid():
    """The built-in defaults must pass validation without any env override."""
    sys.modules.pop("config", None)
    import config
    assert "http://localhost:5050" in config.SOCKETIO_CORS_ORIGINS
    assert "http://127.0.0.1:5050" in config.SOCKETIO_CORS_ORIGINS
    sys.modules.pop("config", None)
