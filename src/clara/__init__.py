"""Clara Vibe OS : premier parcours vocal Windows."""

import os

# Official ORT process-lifetime opt-out, before any native library import.
# https://github.com/microsoft/onnxruntime/blob/main/docs/Privacy.md
os.environ["ORT_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

__version__ = "0.3.0"
