"""Factory dell'applicazione FastAPI."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.database import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Safety net per quando l'app gira da sola (es. `uvicorn app.api.app:create_app`);
    # in main.py il DB è già inizializzato prima dell'avvio dei task.
    await init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="WatchSniper API",
        description="Monitoraggio prezzi e deal sul mercato degli orologi di lusso",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Eccezione non gestita su %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Errore interno del server"})

    return app
