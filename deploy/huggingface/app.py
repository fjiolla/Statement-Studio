"""Hugging Face Space entry point (Gradio SDK on ZeroGPU).

Serves the unchanged Statement Studio FastAPI backend (backend/app/main.py)
through Gradio's own server. Two platform requirements shape this file:

* ZeroGPU runs its startup check from inside ``gr.Blocks.launch()`` and needs at
  least one ``@spaces.GPU`` function, so Gradio must do the launching.
* The backend's routes and CORS middleware are handed to the FastAPI app that
  Gradio creates (``app_kwargs``), so ``/api/*`` behaves exactly as when the
  backend runs on its own. Nothing in the backend needs a GPU.
"""
import os

os.environ.setdefault("BEFREE_DATA_DIR", "/tmp/befree")
os.environ.setdefault("OMP_NUM_THREADS", "2")

import spaces  # noqa: E402  (must be imported before anything touches CUDA)
import gradio as gr  # noqa: E402

from app import main as backend  # noqa: E402  the real backend, unchanged


@spaces.GPU(duration=1)
def _gpu_probe() -> str:
    """ZeroGPU requires a GPU-decorated function at startup. The app never calls it."""
    return "ok"


FRONTEND = os.environ.get("FRONTEND_URL", "")

with gr.Blocks(title="Statement Studio API") as demo:
    gr.Markdown(
        "## Statement Studio API\n"
        "This Space hosts the backend for Statement Studio.  \n"
        + (f"Open the app: [{FRONTEND}]({FRONTEND})" if FRONTEND else "Health check: `/api/health`")
    )

# Normally a FastAPI startup event: database, model warm-up, 24-hour retention cleanup.
backend._startup()

demo.launch(
    server_name="0.0.0.0",
    # Spaces turn on SSR (GRADIO_SSR_MODE=true), which puts a Node proxy in front that
    # answers every path itself; /api/* must reach FastAPI, so render client-side instead.
    ssr_mode=False,
    app_kwargs={
        "routes": list(backend.app.routes),               # /api/* first, then Gradio's own routes
        "middleware": list(backend.app.user_middleware),  # CORS + gzip, as in the standalone backend
    },
)
