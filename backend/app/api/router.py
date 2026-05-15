from fastapi import APIRouter

from app.api.routes import boss, candidates, dashboard, feedback, jobs, settings, tasks

api_router = APIRouter()
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(boss.router, prefix="/boss", tags=["boss"])
api_router.include_router(tasks.router, prefix="/screening-tasks", tags=["screening-tasks"])
api_router.include_router(candidates.router, prefix="/candidates", tags=["candidates"])
api_router.include_router(feedback.router, prefix="/feedback", tags=["feedback"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
