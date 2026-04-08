# Teams App Registration Guide

This guide covers everything needed to register the Meeting Analyzer bot as a Teams app and make it available to users.

The Azure AD identity and Bot Service are provisioned automatically by Terraform (`infra/teams.tf`). What Terraform cannot do is create the Teams App Manifest package — that must be done manually and uploaded to Teams.

---

## Prerequisites

- `terraform apply` has been run successfully (see `infra/README.md`)
- You have the bot App ID from Terraform output:
  ```bash
  terraform -chdir=infra output -raw bot_app_id
  ```
- Teams Admin Center access (for org-wide deployment), or Teams Developer Portal access (for sideloading/testing)

---

## Part 1 — Verify Bot Service is Wired Up

After `terraform apply`, confirm the Bot Service endpoint is registered correctly:

```bash
# Should print your bot Container App URL + /api/messages
terraform -chdir=infra output -raw bot_messaging_endpoint
```

Test the endpoint responds (it will return 405 on GET, which is correct — it only accepts POST from Bot Framework):

```bash
curl -o /dev/null -s -w "%{http_code}" \
  "$(terraform -chdir=infra output -raw bot_base_url)/api/messages"
# Expected: 405
```

---

## Part 2 — Create the App Manifest

### 1. Get the required values

```bash
BOT_APP_ID=$(terraform -chdir=infra output -raw bot_app_id)
BOT_URL=$(terraform -chdir=infra output -raw bot_base_url)
echo "App ID : $BOT_APP_ID"
echo "Bot URL: $BOT_URL"
```

### 2. Create the manifest directory

```bash
mkdir -p teams-app
```

### 3. Create `manifest.json`

Create `teams-app/manifest.json` with the following content, substituting `<BOT_APP_ID>` with the value from step 1:

```json
{
  "$schema": "https://developer.microsoft.com/en-us/json-schemas/teams/v1.17/MicrosoftTeams.schema.json",
  "manifestVersion": "1.17",
  "version": "1.0.0",
  "id": "<BOT_APP_ID>",
  "developer": {
    "name": "Your Organisation",
    "websiteUrl": "https://your-org.example.com",
    "privacyUrl": "https://your-org.example.com/privacy",
    "termsOfUseUrl": "https://your-org.example.com/terms"
  },
  "name": {
    "short": "Meeting Analyzer",
    "full": "Meeting Analyzer Bot"
  },
  "description": {
    "short": "AI-powered meeting analysis and insights.",
    "full": "Meeting Analyzer joins your Teams meetings, captures transcripts, and delivers post-meeting analysis including agenda adherence, action items, and sentiment insights."
  },
  "icons": {
    "color": "color.png",
    "outline": "outline.png"
  },
  "accentColor": "#0078D4",
  "bots": [
    {
      "botId": "<BOT_APP_ID>",
      "scopes": ["team", "groupChat"],
      "supportsFiles": false,
      "isNotificationOnly": false,
      "commandLists": [
        {
          "scopes": ["team", "groupChat"],
          "commands": [
            {
              "title": "help",
              "description": "Show available commands"
            },
            {
              "title": "status",
              "description": "Show current meeting analysis status"
            }
          ]
        }
      ]
    }
  ],
  "permissions": [
    "identity",
    "messageTeamMembers"
  ],
  "validDomains": []
}
```

> `id` and `bots[0].botId` must both be set to the same value — your bot's Azure AD App ID.

### 4. Add app icons

Teams requires two PNG icons in the same directory as `manifest.json`:

| File | Size | Purpose |
|------|------|---------|
| `color.png` | 192×192 px | Full colour icon shown in app listings |
| `outline.png` | 32×32 px | Monochrome (white + transparent) icon for the Teams sidebar |

Place both files in `teams-app/`.

If you don't have icons yet, create simple placeholders:

```bash
# Requires ImageMagick
convert -size 192x192 xc:#0078D4 teams-app/color.png
convert -size 32x32 xc:white teams-app/outline.png
```

### 5. Package the app

```bash
cd teams-app
zip ../teams.zip manifest.json color.png outline.png
cd ..
```

Verify the zip contains exactly three files:

```bash
unzip -l teams-app.zip
```

---

## Part 3 — Upload to Teams

Choose the method that fits your situation.

### Option A — Sideload for testing (single user / team)

Use this for development and testing. Does not require admin access.

1. Open Microsoft Teams
2. Go to Apps → Manage your apps → Upload an app
3. Select "Upload a custom app"
4. Choose `teams-app.zip`
5. Select the team or chat to install it into
6. Click Add

> Sideloading must be enabled in your tenant. If the option is greyed out, ask your Teams admin to enable "Upload custom apps" in the Teams Admin Center under `Teams apps → Setup policies`.

### Option B — Org-wide deployment via Teams Admin Center

Use this for production rollout to your organisation.

1. Go to [Teams Admin Center](https://admin.teams.microsoft.com)
2. Navigate to Teams apps → Manage apps
3. Click Upload new app
4. Upload `teams-app.zip`
5. Once uploaded, find the app in the list and set its status to Allowed
6. To push it to specific users or groups: go to Teams apps → Setup policies → Add the app under Installed apps

### Option C — Teams Developer Portal

Useful if you want to edit the manifest visually before publishing.

1. Go to [Teams Developer Portal](https://dev.teams.microsoft.com)
2. Apps → Import app → upload `teams-app.zip`
3. Edit any fields as needed
4. Publish → Publish to your org

---

## Part 4 — Test the Bot in a Meeting

1. Create or join a Teams meeting
2. In the meeting chat, add the Meeting Analyzer app:
   - Click the + (Add an app) button in the meeting toolbar
   - Search for "Meeting Analyzer"
   - Click Add
3. The bot will join and begin capturing the meeting
4. After the meeting ends, the bot posts the analysis report in the meeting chat

---

## Rotating the Client Secret

The bot client secret expires after `bot_secret_expiry_years` (default: 1 year). To rotate it:

```bash
terraform -chdir=infra taint azuread_application_password.bot
terraform -chdir=infra apply -var-file=terraform.tfvars
```

The Container App is automatically updated with the new secret — no manual steps needed.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Bot doesn't respond in meeting | Messaging endpoint not reachable | Check Container App is running: `az containerapp show --name <bot-app> --resource-group <rg> --query properties.runningStatus` |
| 401 Unauthorized from bot | Wrong `BOT_APP_ID` or `BOT_APP_PASSWORD` | Verify env vars in Container App: `az containerapp show ... --query properties.template.containers[0].env` |
| "Upload custom app" option missing | Sideloading disabled in tenant | Enable in Teams Admin Center → Teams apps → Setup policies |
| Manifest validation error on upload | Schema mismatch or missing fields | Validate at [Teams Developer Portal] 
