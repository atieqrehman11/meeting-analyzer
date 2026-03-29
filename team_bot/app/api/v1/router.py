from fastapi import APIRouter

from team_bot.app.api.v1.teams import router as teams_router

router = APIRouter()
router.include_router(teams_router)
