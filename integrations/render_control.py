# integrations/render_control.py — optional pause/resume (best-effort)
from __future__ import annotations
import os, httpx

PAUSE_URL  = os.getenv("RENDER_PAUSE_URL")   # your webhook/script that suspends service
RESUME_URL = os.getenv("RENDER_RESUME_URL")  # your webhook/script that resumes service
AUTOPAUSE  = os.getenv("RENDER_AUTOPAUSE", "true").lower() == "true"

async def _hit(url: str) -> bool:
    try:
        if not url:
            return False
        async with httpx.AsyncClient(timeout=10) as cli:
            r = await cli.post(url)
            return r.status_code // 100 == 2
    except Exception:
        return False

async def pause_render_if_enabled() -> bool:
    if not AUTOPAUSE:
        return False
    return await _hit(PAUSE_URL)

async def resume_render_if_enabled() -> bool:
    if not AUTOPAUSE:
        return False
    return await _hit(RESUME_URL)
