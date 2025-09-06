# utils/logging_setup.py
from __future__ import annotations
import os, logging
from logging.handlers import RotatingFileHandler

def setup_logging(app_logger: logging.Logger | None = None,
                  file_path: str = "/tmp/ktw_app.log",
                  max_bytes: int = 5_000_000,
                  backups: int = 3,
                  level: int = logging.INFO) -> None:
    """
    Rotating file logs (Render fs is ephemeral but useful for short DR triage).
    Keeps stdout logs unchanged.
    """
    logger = app_logger or logging.getLogger()
    logger.setLevel(level)
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        fh = RotatingFileHandler(file_path, maxBytes=max_bytes, backupCount=backups)
        fh.setLevel(level)
        fh.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(fh)
    except Exception:
        # file handler optional — continue with stdout only
        pass
