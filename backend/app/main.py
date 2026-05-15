import asyncio
import sys
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.logging import get_logger, setup_logging
from app.services.task_scheduler import task_scheduler
from app.services.task_state_manager import task_state_manager


if sys.platform.startswith("win") and hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

setup_logging()
logger = get_logger(__name__)


def _keyboard_listener(stop_event: threading.Event) -> None:
    """后台线程：P=暂停筛选任务  S=继续筛选任务（不区分大小写）"""
    try:
        import msvcrt
    except ImportError:
        return  # 非 Windows 平台跳过

    import _thread

    from app.services.task_service import task_service
    from app.services.mock_data import store

    while not stop_event.is_set():
        try:
            if msvcrt.kbhit():
                char = msvcrt.getwch()
                if char in ("\x00", "\xe0"):
                    # 扩展键前缀（方向键等），消费掉紧随的扫描码字节，不处理
                    msvcrt.getwch()
                    continue
                if char == "\x03":
                    # Ctrl+C：msvcrt 已将其从缓冲区取走，用 _thread.interrupt_main()
                    # 在主线程触发 KeyboardInterrupt，让 uvicorn 正常退出
                    _thread.interrupt_main()
                    break
                char = char.lower()
                if char == "p":
                    if store.task.status == "running":
                        task_service.pause()
                        logger.info("⏸  键盘指令 P — 已暂停任务: %s", store.task.id)
                    else:
                        logger.info("⏸  键盘指令 P — 当前没有正在运行的任务（状态: %s）", store.task.status)
                elif char == "s":
                    if store.task.status == "paused":
                        task_service.resume()
                        logger.info("▶  键盘指令 S — 已恢复任务: %s", store.task.id)
                    else:
                        logger.info("▶  键盘指令 S — 当前没有已暂停的任务（状态: %s）", store.task.status)
        except Exception:
            pass
        time.sleep(0.05)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await task_state_manager.start_monitor()
    scheduler_task = asyncio.create_task(task_scheduler.start())
    logger.info("Task scheduler and monitor started")

    _kb_stop = threading.Event()
    _kb_thread = threading.Thread(
        target=_keyboard_listener,
        args=(_kb_stop,),
        daemon=True,
        name="keyboard-listener",
    )
    _kb_thread.start()
    logger.info("键盘控制已启用：P = 暂停筛选  S = 继续筛选")

    try:
        yield
    finally:
        _kb_stop.set()
        await task_scheduler.shutdown()
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        await task_state_manager.stop_monitor()
        logger.info("Task scheduler and monitor stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Auto HR API",
        version="0.1.0",
        description="Automatic recruiting copilot API scaffold.",
        lifespan=lifespan,
    )

    import os
    allowed_origins = os.getenv("CORS_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router, prefix="/api")
    logger.info("Auto HR API app created.")
    return app


app = create_app()
