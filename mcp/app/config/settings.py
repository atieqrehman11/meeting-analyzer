from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # App
    app_name: str = "Meeting Bot MCP Server"
    app_version: str = "1.0.0"
    log_level: str = "INFO"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False

    # Backend: "mock" uses in-memory stubs, "azure" uses real Azure services
    backend_mode: str = "mock"

    # Azure Blob Storage
    azure_storage_account_url: str = ""
    blob_container_transcripts: str = "transcripts"
    blob_container_reports: str = "reports"

    # Azure Cosmos DB
    cosmos_endpoint: str = ""
    cosmos_database: str = "meeting-analysis"

    # Microsoft Graph
    graph_tenant_id: str = ""
    graph_client_id: str = ""

    # Data residency
    azure_region: str = "eastus"

    model_config = {"env_prefix": "MCP_", "case_sensitive": False}


settings = Settings()
