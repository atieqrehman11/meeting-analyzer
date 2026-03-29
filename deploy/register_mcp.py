"""
MCP server registration — verification script.

With the current azure-ai-projects SDK (v2+), MCP servers are NOT registered
as standalone connections. Instead, the MCP server URL is passed directly as
a McpTool definition when creating or updating each agent in register_agents.py.

This script verifies that the MCP server URL is reachable before deployment,
acting as a pre-flight check rather than a registration step.

Usage:
    MCP_SERVER_URL=https://mcp.<env>.azurecontainerapps.io python deploy/register_mcp.py
"""
import os
import sys
import urllib.request
import urllib.error

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "").rstrip("/")

if not MCP_SERVER_URL:
    print("ERROR: MCP_SERVER_URL environment variable is not set.")
    sys.exit(1)

health_url = f"{MCP_SERVER_URL}/docs"

print(f"Checking MCP server reachability: {health_url}")

try:
    with urllib.request.urlopen(health_url, timeout=10) as resp:
        if resp.status == 200:
            print(f"MCP server is reachable (HTTP {resp.status}).")
            print(f"MCP_SERVER_URL={MCP_SERVER_URL} — set this in your deployment environment.")
            print("Agents will pick up this URL from the MCP_SERVER_URL env var during register_agents.py.")
        else:
            print(f"WARNING: MCP server returned HTTP {resp.status}. Verify the server is healthy.")
            sys.exit(1)
except urllib.error.URLError as e:
    print(f"ERROR: Could not reach MCP server at {health_url}: {e.reason}")
    print("Ensure the Container App is deployed and the URL is correct before registering agents.")
    sys.exit(1)
