import asyncio
import json
import threading
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.models.domain import ScreeningConfig, ScreeningTask
from app.schemas.jobs import ScreeningRunRequest
from app.services.job_service import job_service
from app.services.task_scheduler import task_scheduler
from app.services.task_service import task_service
from app.services.task_state_manager import TaskState, task_state_manager
from app.services.task_storage import task_storage
from app.services.runtime_state_service import runtime_state_service

router = APIRouter()


def _run_screening_in_daemon(job_id: str, pages: int, skip_seen: bool = True) -> None:
    """Run legacy screening in a daemon thread so process shutdown is not blocked."""
    import logging
    from app.services.mock_data import store
    from app.services.runtime_state_service import runtime_state_service
    from app.services.task_storage import task_storage
    _logger = logging.getLogger(__name__)
    try:
        task_service.run_screening(job_id, pages, skip_seen=skip_seen)
    except Exception as exc:
        _logger.exception("Screening daemon thread died unexpectedly for job=%s: %s", job_id, exc)
        task = store.task
        if task.job_id == job_id and task.status == "running":
            task.status = "failed"
            task.message = f"筛选线程意外终止: {exc}"
            from datetime import datetime
            task.updated_at = datetime.now()
            try:
                runtime_state_service.save_task(task)
                task_storage.save_task(task)
            except Exception:
                pass


@router.get("/current")
def get_current_task():
    return task_service.get_task()


@router.get("/list")
def list_tasks(
    job_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    """List stored screening tasks."""
    tasks = task_storage.get_recent_tasks(limit)

    if job_id:
        tasks = [task for task in tasks if task.job_id == job_id]
    if status:
        tasks = [task for task in tasks if task.status == status]

    return {
        "items": tasks,
        "total": len(tasks),
        "running_count": len([task for task in tasks if task.status == "running"]),
    }


@router.post("/create")
def create_task(payload: ScreeningRunRequest):
    """Create a scheduler-driven task."""
    job = job_service.get_job(payload.job_id)
    profile = job_service.get_current_profile(payload.job_id)

    config = task_storage.get_config(payload.job_id)
    if not config:
        config = ScreeningConfig(
            job_id=payload.job_id,
            profile_version_id=profile.version_id,
            max_pages=payload.pages,
        )

    task = ScreeningTask(
        id=f"task-{payload.job_id}",
        job_id=payload.job_id,
        job_name=job.name,
        profile_version_id=profile.version_id,
        config=config,
        status="pending",
        progress_current=0,
        progress_total=config.max_pages,
        started_at=datetime.now(),
        updated_at=datetime.now(),
        message="Waiting to start...",
    )

    task_storage.save_task(task)
    return task


@router.post("/{task_id}/start")
async def start_task(task_id: str):
    """Start a scheduler-driven task."""
    task = task_storage.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status not in ["pending", "paused"]:
        raise HTTPException(status_code=400, detail=f"Cannot start task in status: {task.status}")

    success = await task_scheduler.submit(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to submit task")

    return task


@router.post("/run")
def run_screening(payload: ScreeningRunRequest):
    """Run screening for the current job using the live streaming flow."""
    task = task_service.start_screening(payload.job_id, payload.pages)
    worker = threading.Thread(
        target=_run_screening_in_daemon,
        args=(payload.job_id, 200, payload.skip_seen),  # pages capped internally; skip_seen controls dedup
        daemon=True,
        name=f"screening-{payload.job_id}",
    )
    worker.start()
    return task


@router.get("/stream")
async def stream_screening(
    task_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
):
    """Push task state or job candidate updates over SSE."""
    if not task_id and not job_id:
        raise HTTPException(status_code=400, detail="Either task_id or job_id is required")

    async def stream_task_state():
        try:
            state = await task_state_manager.get_state(task_id)
            if state:
                yield f"data: {json.dumps({'type': 'state', 'data': state.to_dict()}, ensure_ascii=False)}\n\n"

            queue: asyncio.Queue[TaskState] = asyncio.Queue()

            async def on_state_change(new_state: TaskState):
                await queue.put(new_state)

            await task_state_manager.subscribe(task_id, on_state_change)

            try:
                while True:
                    try:
                        new_state = await asyncio.wait_for(queue.get(), timeout=30)
                        yield f"data: {json.dumps({'type': 'state', 'data': new_state.to_dict()}, ensure_ascii=False)}\n\n"
                    except asyncio.TimeoutError:
                        yield f"data: {json.dumps({'type': 'heartbeat'}, ensure_ascii=False)}\n\n"
            finally:
                await task_state_manager.unsubscribe(task_id, on_state_change)
        except asyncio.CancelledError:
            return

    async def stream_job_updates():
        try:
            snapshot = task_service.get_stream_snapshot(job_id)
            last_seq = int(snapshot.get("seq", 0))
            yield f"data: {json.dumps(snapshot, ensure_ascii=False)}\n\n"

            idle_ticks = 0
            while True:
                events = task_service.get_stream_events(job_id, after_seq=last_seq)
                if events:
                    idle_ticks = 0
                    for event in events:
                        last_seq = max(last_seq, int(event.get("seq", 0)))
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                else:
                    idle_ticks += 1
                    if idle_ticks >= 30:
                        idle_ticks = 0
                        yield f"data: {json.dumps({'type': 'heartbeat'}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            return

    event_generator = stream_job_updates if job_id else stream_task_state

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/{task_id}")
def get_task(task_id: str):
    """Get a stored screening task."""
    task = task_storage.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/{task_id}/candidates")
def get_task_candidates(task_id: str):
    """Return persisted candidates for one task."""
    candidates = task_storage.get_candidates(task_id)
    if candidates:
        return candidates

    task = task_storage.get_task(task_id)
    if task is None:
        task = task_service.get_task() if task_service.get_task().id == task_id else None
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return runtime_state_service.load_candidates(task.job_id)


@router.post("/{task_id}/pause")
async def pause_task(task_id: str):
    """Pause a scheduler-driven task."""
    task = task_storage.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != "running":
        raise HTTPException(status_code=400, detail="Task is not running")

    from app.services.screening_executor import screening_executor

    screening_executor.pause(task_id)
    task.status = "paused"
    task.message = "Task paused"
    task.updated_at = datetime.now()
    task_storage.save_task(task)
    return task


@router.post("/{task_id}/resume")
async def resume_task(task_id: str):
    """Resume a scheduler-driven task."""
    task = task_storage.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != "paused":
        raise HTTPException(status_code=400, detail="Task is not paused")

    from app.services.screening_executor import screening_executor

    screening_executor.resume(task_id)
    task.status = "running"
    task.message = "Task resumed"
    task.updated_at = datetime.now()
    task_storage.save_task(task)
    return task


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Cancel a scheduler-driven task."""
    task = task_storage.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status not in ["pending", "running", "paused"]:
        raise HTTPException(status_code=400, detail="Task cannot be cancelled")

    from app.services.screening_executor import screening_executor

    screening_executor.cancel(task_id)
    task.status = "failed"
    task.message = "Task cancelled"
    task.updated_at = datetime.now()
    task_storage.save_task(task)
    return task


@router.post("/{task_id}/clear")
async def clear_task(task_id: str):
    """Clear persisted task results."""
    task = task_storage.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task_service.clear_task_results(task_id)


@router.get("/queue/state")
def get_queue_state():
    """Get scheduler queue state."""
    return {
        "max_concurrent": task_scheduler.max_concurrent,
        "running_count": 1 if task_scheduler.get_current_task() else 0,
        "queued_count": task_scheduler.get_queue_size(),
        "current_task": task_scheduler.get_current_task(),
    }
