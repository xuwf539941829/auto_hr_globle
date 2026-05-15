from fastapi import APIRouter, HTTPException, Query

from app.services.boss_launcher import BossLauncherError, boss_launcher
from app.services.boss_connector import BossConnectorError, boss_connector

router = APIRouter()


@router.get("/jobs/live")
def get_live_boss_jobs():
    try:
        return boss_connector.fetch_job_options()
    except BossConnectorError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/launch-login")
def launch_boss_login(browser_type: str = Query(default="auto")):
    try:
        return boss_launcher.launch_login_browser(browser_type)
    except BossLauncherError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/status")
def get_boss_status():
    try:
        return boss_connector.get_status()
    except BossConnectorError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
