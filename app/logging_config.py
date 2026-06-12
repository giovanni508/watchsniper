"""Setup del logging nativo per tutta l'applicazione."""

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()
    root.addHandler(handler)

    # Riduce il rumore delle librerie più verbose.
    for noisy in ("aiogram.event", "httpx", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
