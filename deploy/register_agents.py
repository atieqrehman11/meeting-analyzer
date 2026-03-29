"""
Idempotent agent registration script.
Creates or updates all Foundry-native agents from their YAML definitions.

Usage:
    AZURE_AI_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project> \
    MCP_SERVER_URL=https://mcp.<env>.azurecontainerapps.io \
    python deploy/register_agents.py

Requires: pip install azure-ai-projects azure-identity pyyaml
"""
import os
import pathlib
import yaml
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import McpTool

# Single endpoint URL — new SDK format (v2+)
# Form: https://<ai-services-account>.services.ai.azure.com/api/projects/<project-name>
ENDPOINT = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
MCP_SERVER_URL = os.environ["MCP_SERVER_URL"]

client = AIProjectClient(
    endpoint=ENDPOINT,
    credential=DefaultAzureCredential(),
)


def build_tools(tools_config: list) -> list:
    """
    Convert YAML tool entries to SDK tool definitions.
    MCP tools use McpTool from azure.ai.agents.models.
    """
    definitions = []
    for entry in tools_config:
        if "mcp" in entry:
            mcp = McpTool(
                server_label=entry["mcp"],          # logical name, e.g. "meeting-bot-mcp-server"
                server_url=MCP_SERVER_URL,
                allowed_tools=entry.get("tools_filter", []),
            )
            definitions.extend(mcp.definitions)
    return definitions


def deploy_agent(definition_path: pathlib.Path) -> None:
    defn = yaml.safe_load(definition_path.read_text())
    instructions = pathlib.Path(defn["instructions_file"]).read_text()
    tools = build_tools(defn.get("tools", []))

    existing = {a.name: a for a in client.agents.list_agents()}

    params = {
        "model": defn["model"],
        "instructions": instructions,
        "temperature": defn.get("temperature", 0.2),
        "tools": tools,
    }

    if defn["name"] in existing:
        agent = client.agents.update_agent(existing[defn["name"]].id, **params)
        print(f"Updated : {agent.name} ({agent.id})")
    else:
        agent = client.agents.create_agent(
            name=defn["name"],
            description=defn.get("description", ""),
            **params,
        )
        print(f"Created : {agent.name} ({agent.id})")

    # Persist agent ID so the Orchestrator resolves it at runtime
    id_path = pathlib.Path(f"deploy/agent_ids/{defn['name']}.txt")
    id_path.parent.mkdir(exist_ok=True)
    id_path.write_text(agent.id)


if __name__ == "__main__":
    for defn_file in sorted(pathlib.Path("agents/definitions").glob("*.yaml")):
        deploy_agent(defn_file)
