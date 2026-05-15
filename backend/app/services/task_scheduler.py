import asyncio
from typing import Optional

from app.core.logging import get_logger
from app.services.screening_executor import screening_executor
from app.services.task_storage import task_storage

logger = get_logger(__name__)


class TaskScheduler:
    """Single-task async scheduler for executor-driven tasks."""

    def __init__(self, max_concurrent: int = 1):
        self.max_concurrent = max_concurrent
        self._current_task: Optional[str] = None
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._shutdown = False

    async def start(self) -> None:
        logger.info("Task scheduler started")
        while not self._shutdown:
            try:
                task_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)

                if self._current_task:
                    logger.warning(
                        "Task %s is already running, requeue task %s",
                        self._current_task,
                        task_id,
                    )
                    await self._queue.put(task_id)
                    await asyncio.sleep(1)
                    continue

                self._current_task = task_id
                try:
                    await self._execute_task(task_id)
                finally:
                    self._current_task = None
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                logger.info("Task scheduler cancelled")
                break
            except Exception as exc:
                logger.exception("Task scheduler error: %s", exc)

    async def _execute_task(self, task_id: str) -> None:
        task = task_storage.get_task(task_id)
        if not task:
            logger.warning("Task %s not found", task_id)
            return

        try:
            await screening_executor.execute(task)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Task execution failed for %s: %s", task_id, exc)

    async def submit(self, task_id: str) -> bool:
        task = task_storage.get_task(task_id)
        if not task:
            return False

        if task.status not in ["pending", "paused"]:
            logger.warning("Task %s cannot be submitted in status %s", task_id, task.status)
            return False

        task.status = "queued"
        task.message = "Queued..."
        task_storage.save_task(task)
        await self._queue.put(task_id)
        logger.info("Task %s queued", task_id)
        return True

    def get_current_task(self) -> Optional[str]:
        return self._current_task

    def get_queue_size(self) -> int:
        return self._queue.qsize()

    async def shutdown(self) -> None:
        self._shutdown = True
        while self._current_task:
            await asyncio.sleep(0.5)


task_scheduler = TaskScheduler(max_concurrent=1)
