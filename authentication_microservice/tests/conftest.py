"""Shared fixtures for authentication service tests.

The app config is instantiated at import time, so test environment defaults must
exist before importing modules that depend on ``configurations.config``.
"""

import os

os.environ.setdefault("VERSION", "test")
os.environ.setdefault("AUTHENTICATION_SECRET_KEY", "test-access-secret")
os.environ.setdefault("AUTHENTICATION_REFRESH_SECRET_KEY", "test-refresh-secret")
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "5")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://test:test@localhost:5432/test")
