# utils/host.py — identify this host
from __future__ import annotations
import os, socket, uuid

def host_id() -> str:
    return os.getenv("HOST_ID") or (socket.gethostname()[:12] + "-" + uuid.uuid4().hex[:6])

def host_kind() -> str:
    # Allow explicit override
    kind = os.getenv("HOST_KIND", "").strip().lower()
    if kind in {"local", "render"}:
        return kind
    # Heuristic: if Render env present
    if os.getenv("RENDER_SERVICE_ID") or os.getenv("RENDER") or os.getenv("RENDER_INSTANCE_ID"):
        return "render"
    return "local"
