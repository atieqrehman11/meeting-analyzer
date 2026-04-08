from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from team_bot.app.config.settings import settings

router = APIRouter()

_CONFIG_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>{app_name} — Configuration</title>
  <script src="https://res.cdn.office.net/teams-js/2.22.0/js/MicrosoftTeams.min.js"></script>
  <style>
    body {{ font-family: Segoe UI, sans-serif; padding: 2rem; background: #f3f2f1; }}
    .card {{ background: white; border-radius: 8px; padding: 2rem; max-width: 480px; margin: auto; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
    h2 {{ color: #0078d4; margin-top: 0; }}
    p {{ color: #444; }}
    button {{ background: #0078d4; color: white; border: none; padding: 0.6rem 1.4rem; border-radius: 4px; font-size: 1rem; cursor: pointer; }}
    button:hover {{ background: #106ebe; }}
  </style>
</head>
<body>
  <div class="card">
    <h2>&#x1F4CB; {app_name}</h2>
    <p>Add <strong>{app_name}</strong> to this meeting to automatically capture transcripts and generate AI-powered insights after the meeting ends.</p>
    <p>No additional configuration is required.</p>
    <button onclick="save()">Add to Meeting</button>
  </div>
  <script>
    microsoftTeams.app.initialize().then(() => {{
      microsoftTeams.pages.config.registerOnSaveHandler((saveEvent) => {{
        microsoftTeams.pages.config.setConfig({{
          suggestedDisplayName: "{app_name}",
          entityId: "meeting-assistant-tab",
          contentUrl: window.location.origin + "/tab/content",
          websiteUrl: window.location.origin
        }});
        saveEvent.notifySuccess();
      }});
      microsoftTeams.pages.config.setValidityState(true);
    }});

    function save() {{
      microsoftTeams.pages.config.setConfig({{
        suggestedDisplayName: "{app_name}",
        entityId: "meeting-assistant-tab",
        contentUrl: window.location.origin + "/tab/content",
        websiteUrl: window.location.origin
      }});
      microsoftTeams.pages.config.setValidityState(true);
    }}
  </script>
</body>
</html>"""

_CONTENT_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>{app_name}</title>
  <script src="https://res.cdn.office.net/teams-js/2.22.0/js/MicrosoftTeams.min.js"></script>
  <style>
    body {{ font-family: Segoe UI, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #f3f2f1; }}
    .card {{ background: white; border-radius: 8px; padding: 2rem; max-width: 480px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
    h2 {{ color: #0078d4; }}
    p {{ color: #444; }}
  </style>
</head>
<body>
  <div class="card">
    <h2>&#x1F4CB; {app_name}</h2>
    <p>Meeting Assistant is active and will automatically capture this meeting's transcript and generate insights when the meeting ends.</p>
  </div>
  <script>microsoftTeams.app.initialize();</script>
</body>
</html>"""


@router.get("/tab/config", response_class=HTMLResponse)
async def tab_config() -> HTMLResponse:
    """Configuration page shown when adding the app to a meeting from the calendar invite."""
    return HTMLResponse(_CONFIG_PAGE.format(app_name=settings.app_display_name))


@router.get("/tab/content", response_class=HTMLResponse)
async def tab_content() -> HTMLResponse:
    """Content page shown inside the meeting tab."""
    return HTMLResponse(_CONTENT_PAGE.format(app_name=settings.app_display_name))
