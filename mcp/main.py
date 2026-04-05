from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.v1.router import router
from app.common.exceptions import register_exception_handlers
from app.common.logger import logger
from app.config.settings import settings
from app.services.similarity import SimilarityService
from app.services.backends.mock import MockStorageBackend, MockDatabaseBackend, MockGraphBackend
from app.services.backends.graph import AzureGraphBackend


def _build_backends(app: FastAPI) -> None:
    if settings.backend_mode == "azure":
        # Storage and DB backends still pending full Azure implementation.
        # Graph backend is now real.
        app.state.storage = MockStorageBackend()
        app.state.db = MockDatabaseBackend()
        app.state.graph = AzureGraphBackend(
            tenant_id=settings.graph_tenant_id,
            client_id=settings.graph_client_id,
            client_secret=settings.graph_client_secret,
        )
    else:
        app.state.storage = MockStorageBackend()
        app.state.db = MockDatabaseBackend()
        app.state.graph = MockGraphBackend()

    app.state.similarity = SimilarityService()
    logger.info("Backends initialised (mode=%s)", settings.backend_mode)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _build_backends(app)
    yield
    if hasattr(app.state, "graph") and hasattr(app.state.graph, "close"):
        await app.state.graph.close()
    logger.info("MCP server shutting down.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    openapi_version="3.0.3",  # Azure AI Foundry OpenApiTool requires 3.0.x
)

register_exception_handlers(app)
app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=settings.reload)
