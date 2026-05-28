"""Test configuration for authentication service modules.

Application modules instantiate settings at import time, so these defaults must
exist before tests import anything under ``app`` or ``configurations``.
"""

import os

os.environ.setdefault("VERSION", "test")
os.environ.setdefault("AUTHENTICATION_SECRET_KEY", "test-access-secret-with-32-plus-bytes")
os.environ.setdefault("AUTHENTICATION_REFRESH_SECRET_KEY", "test-refresh-secret-with-32-plus-bytes")
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://test:test@localhost:5432/test")
