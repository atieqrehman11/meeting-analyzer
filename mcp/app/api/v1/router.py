from fastapi import APIRouter
from .tools import meeting, transcript, consent, analysis, similarity, realtime, poll

router = APIRouter(prefix="/v1/tools")

for _r in (meeting.router, transcript.router, consent.router,
           analysis.router, similarity.router, realtime.router, poll.router):
    router.include_router(_r)
