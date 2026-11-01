# Vercel entry point (zero-config FastAPI): serves the API and UI from the bundled read-only memory snapshot.
from crag.api import app  # noqa: F401
