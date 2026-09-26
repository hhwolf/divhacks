"""Vercel Python entry: exposes the FastAPI ASGI app from apps/api. All routes are rewritten here by vercel.json."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.main import app  # noqa: E402  (import after sys.path tweak)

__all__ = ["app"]
