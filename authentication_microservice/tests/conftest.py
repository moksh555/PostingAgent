"""Shared auth test setup.

The auth config object is created at import time, so tests must provide all
required settings before importing application modules.
"""

import os


os.environ.setdefault("VERSION", "test")
os.environ.setdefault(
    "AUTHENTICATION_SECRET_KEY",
    "test-access-secret-key-with-enough-length-for-hs256",
)
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault(
    "AUTHENTICATION_REFRESH_SECRET_KEY",
    "test-refresh-secret-key-with-enough-length-for-hs256",
)
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://user:pass@localhost:5432/test")
