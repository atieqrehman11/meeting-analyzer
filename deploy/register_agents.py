"""
Idempotent agent registration script.
Creates or updates all Foundry-native agents from their YAML definitions.

Usage:
    AZURE_AI_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project> \
    MCP_SERVER_URL=https://mcp.<env>.azurecontainerapps.io \
    python deploy/register_agents.py

Requires: pip install azure-ai-projects azure-ai-agents azure-identity pyyaml
"""
import json
import os
import pathlib

import yaml
from azure.ai.agents import AgentsClient
from azure.ai.projects.models import MCPTool
from azure.identity import DefaultAzureCredential

ENDPOINT = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "").rstrip("/")

client = AgentsClient(
    endpoint=ENDPOINT,
    credential=DefaultAzureCredential(),
)


def build_tools(tools_config: list) -> list:
    """Convert YAML tool entries to MCPTool definitions."""
    tools = []
    for entry in tools_config:
        if "mcp" not in entry:
            continue
        if not MCP_SERVER_URL:
            print(f"  [skip] MCP tool '{entry['mcp']}' — MCP_SERVER_URL not set")
            continue

        # server_label must match ^[a-zA-Z0-9_]+$ (no hyphens)
        label = entry["mcp"].replace("-", "_")
        allowed = entry.get("tools_filter", [])

        mcp = MCPTool(
            server_label=label,
            server_url=MCP_SERVER_URL,
            allowed_tools=allowed if allowed else None,
        )
        tools.append(mcp)

    return tools


def deploy_agent(definition_path: pathlib.Path) -> tuple[str, str]:
    defn = yaml.safe_load(definition_path.read_text())
    instructions = pathlib.Path(defn["instructions_file"]).read_text()
    tools = build_tools(defn.get("tools", []))

    existing = {a.name: a for a in client.list_agents()}

    params = {
        "model": defn["model"],
        "instructions": instructions,
        "temperature": defn.get("temperature", 0.2),
        "tools": tools,
    }

    if defn["name"] in existing:
        agent = client.update_agent(existing[defn["name"]].id, **params)
        print(f"Updated : {agent.name} ({agent.id})")
    else:
        agent = client.create_agent(
            name=defn["name"],
            description=defn.get("description", ""),
            **params,
        )
        print(f"Created : {agent.name} ({agent.id})")

    return defn["name"], agent.id


if __name__ == "__main__":
    agent_ids: dict[str, str] = {}
    for defn_file in sorted(pathlib.Path("agents/definitions").glob("*.yaml")):
        name, agent_id = deploy_agent(defn_file)
        agent_ids[name] = agent_id

    ids_path = pathlib.Path("orchestrator/agent_ids.json")
    ids_path.write_text(json.dumps(agent_ids, indent=2))
    print(f"\nAgent IDs written to {ids_path}")
