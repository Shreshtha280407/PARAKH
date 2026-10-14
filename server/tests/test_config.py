"""Startup fail-fast checks -- see server/app/config.py's Settings
validators and docs/gates/P2_2.md sections 4 and 8. A real deployment
(anything other than APP_ENV=development) must refuse to start rather than
silently fall back to a dev-only default for any of: the report signing
key, the JWT secret, or a wildcard/localhost CORS origin.
"""
import pytest
from pydantic import ValidationError

from server.app.config import Settings

_REAL_KEY = "00" * 32
_REAL_SECRET = "a-real-jwt-secret"
_REAL_ORIGIN = "https://assess.kaushalpramaan.example"


def test_development_without_a_signing_key_fails_fast_too():
    """P7: a signing key that regenerates itself on every process restart
    would silently invalidate every previously-signed report -- see
    docs/gates/P7.md section 4. Unlike JWT_SECRET (still fine to
    auto-generate in development, see the test right below), this MUST
    fail fast in every environment, including development."""
    with pytest.raises(ValidationError, match="REPORT_SIGNING_PRIVATE_KEY"):
        Settings(app_env="development", report_signing_private_key=None)


def test_development_without_a_jwt_secret_auto_generates_one():
    s = Settings(app_env="development", jwt_secret=None)
    assert s.jwt_secret is not None


def test_production_without_a_signing_key_fails_fast():
    with pytest.raises(ValidationError, match="REPORT_SIGNING_PRIVATE_KEY"):
        Settings(app_env="production", report_signing_private_key=None, jwt_secret=_REAL_SECRET, cors_allow_origins=_REAL_ORIGIN)


def test_staging_without_a_signing_key_fails_fast():
    with pytest.raises(ValidationError, match="REPORT_SIGNING_PRIVATE_KEY"):
        Settings(app_env="staging", report_signing_private_key=None, jwt_secret=_REAL_SECRET, cors_allow_origins=_REAL_ORIGIN)


def test_production_without_a_jwt_secret_fails_fast():
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(app_env="production", report_signing_private_key=_REAL_KEY, jwt_secret=None, cors_allow_origins=_REAL_ORIGIN)


def test_wildcard_cors_origin_always_fails_fast_even_in_development():
    """Credentialed (cookie) requests + a wildcard origin are rejected by
    browsers outright -- this is never valid, not just a prod concern."""
    with pytest.raises(ValidationError, match="CORS_ALLOW_ORIGINS"):
        Settings(app_env="development", cors_allow_origins="*")


def test_localhost_cors_origin_outside_development_fails_fast():
    with pytest.raises(ValidationError, match="CORS_ALLOW_ORIGINS"):
        Settings(
            app_env="production", report_signing_private_key=_REAL_KEY, jwt_secret=_REAL_SECRET,
            cors_allow_origins="http://localhost:5173",
        )


def test_production_with_everything_set_starts_fine():
    s = Settings(
        app_env="production", report_signing_private_key=_REAL_KEY, jwt_secret=_REAL_SECRET,
        cors_allow_origins=_REAL_ORIGIN,
    )
    assert s.report_signing_private_key == _REAL_KEY
    assert s.jwt_secret == _REAL_SECRET
    assert s.cors_allow_origins == _REAL_ORIGIN
