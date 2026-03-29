from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.v1.router import router
from app.common.exceptions import register_exception_handlers
from app.common.logger import logger
from app.config.settings import settings
from app.services.similarity import SimilarityService
from app.services.backends.mock import MockStorageBackend, MockDatabaseBackend, MockGraphBackend


def _build_backends(app: FastAPI) -> None:
    if settings.backend_mode == "azure":
        # Azure backends wired here when MCP_BACKEND_MODE=azure
        # from app.services.backends.azure import AzureStorageBackend, AzureDBBackend, AzureGraphBackend
        # app.state.storage = AzureStorageBackend(...)
        # app.state.db      = AzureDBBackend(...)
        # app.state.graph   = AzureGraphBackend(...)
        raise NotImplementedError("Azure backend not yet implemented. Set MCP_BACKEND_MODE=mock.")
    else:
        app.state.storage = MockStorageBackend()
        app.state.db = MockDatabaseBackend()
        app.state.graph = MockGraphBackend()

    app.state.similarity = SimilarityService()
    logger.info("Backends initialised (mode=%s, stage=%d)", settings.backend_mode, settings.active_stage)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _build_backends(app)
    yield
    logger.info("MCP server shutting down.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

register_exception_handlers(app)
app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=settings.reload)
