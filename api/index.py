"""
Vercel serverless entrypoint.

The @vercel/python runtime detects the ASGI `app` object exported here and
serves the whole FastAPI application (API routes + static UI) as one function.
"""

from app.main import app  # noqa: F401  (re-exported for the Vercel runtime)
