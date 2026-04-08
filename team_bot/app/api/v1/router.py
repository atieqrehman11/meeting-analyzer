from fastapi import APIRouter

from team_bot.app.api.v1.teams import router as teams_router
from team_bot.app.api.v1.tab import router as tab_router

router = APIRouter()
router.include_router(teams_router)
router.include_router(tab_router)
