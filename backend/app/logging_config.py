"""Central logging setup. Writes to console and logs/quantifywealth.log so a
paper session leaves a readable, reviewable trail of every decision and fill."""
from __future__ import annotations

import logging
import sys

from app.config import REPO_ROOT

_configured = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    global _configured
    if not _configured:
        log_dir = REPO_ROOT / "logs"
        log_dir.mkdir(exist_ok=True)
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(log_dir / "quantifywealth.log"),
            ],
        )
        _configured = True
    return logging.getLogger("quantifywealth")
