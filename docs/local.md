Terminal 1 — Start MCP:

./run-dev.sh mcp
Terminal 2 — Expose MCP via ngrok:

ngrok http 8080
Copy the URL e.g. https://aaaa.ngrok-free.app

Terminal 3 — Re-register agents with ngrok MCP URL:

source .venv/bin/activate
export AZURE_AI_PROJECT_ENDPOINT=https://aismeetingassistdevvds.cognitiveservices.azure.com/api/projects/proj-meetingassist-dev

export=MCP_SERVER_URL=https://9f22-2600-8804-83b6-5300-d379-4466-5b2-8ead.ngrok-free.app \
./deploy.sh agents

Terminal 4 — Start bot:

./run-dev.sh bot
Terminal 5 — Expose bot via ngrok:

ngrok http 3978
Copy the URL e.g. https://bbbb.ngrok-free.app

Update Bot Service endpoint:

az bot update \
  --name bot-meetingassist-dev-eastus-vds \
  --resource-group rg-meeting-assistant \
  --endpoint "https://d8d1-2600-8804-83b6-5300-d379-4466-5b2-8ead.ngrok-free.app/api/messages"