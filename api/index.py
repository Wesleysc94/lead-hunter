"""Vercel serverless adapter for the Lead Hunter dashboard."""
import sys
from pathlib import Path

# Add project root to Python path so dashboard.app and lead_hunter can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard.app import app  # noqa: E402  (Flask WSGI app)
