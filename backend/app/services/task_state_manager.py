from enum import Enum
from datetime import datetime
from typing import Optional, Callable, Dict, List, Any
import asyncio
from app.core.logging import get_logger

logger = get_logger(__name__)


class TaskStatus(str, Enum):
    """精准的任务状态"""
    PENDING = "pending"      # 等待执行
    QUEUED = "queued"        # 已进入队列
    RUNNING = "running"      # 正在执行
    PAUSING = "pausing"      # 暂停中（等待当前操作完成）
    PAUSED = "paused"        # 已暂停
    RESUMING = "resuming"    # 恢复中
    CANCELLING = "cancelling"  # 取消中（等待当前操作完成）
    CANCELLED = "cancelled"   # 已取消
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"         # 失败


class TaskState:
    """任务状态快照"""
    def __init__(
        self,
        status: TaskStatus,
        progress_current: int = 0,
        progress_total: int = 0,
        message: str = "",
        worker_id: Optional[str] = None,
        phase: Optional[str] = None
    ):
        self.status = status
        self.progress_current = progress_current
        self.progress_total = progress_total
        self.message = message
        self.worker_id = worker_id
        self.phase = phase
        self.updated_at = datetime.now()
        self.heartbeat_at: Optional[datetime] = None
        
    @property
    def is_active(self) -> bool:
        """是否处于活跃状态"""
        return self.status in {
            TaskStatus.QUEUED, TaskStatus.RUNNING, 
            TaskStatus.PAUSING, TaskStatus.RESUMING
        }
    
    @property
    def is_terminal(self) -> bool:
        """是否已结束"""
        return self.status in {
            TaskStatus.COMPLETED, TaskStatus.CANCELLED, 
            TaskStatus.FAILED, TaskStatus.PAUSED
        }
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "progress_current": self.progress_current,
            "progress_total": self.progress_total,
            "message": self.message,
            "worker_id": self.worker_id,
            "phase": self.phase,
            "updated_at": self.updated_at.isoformat(),
            "heartbeat_at": self.heartbeat_at.isoformat() if self.heartbeat_at else None
        }


class TaskStateManager:
    """任务状态管理器 - 确保状态精准同步"""
    
    HEARTBEAT_TIMEOUT = 10  # 心跳超时时间（秒）
    STATE_CHECK_INTERVAL = 5  # 状态检查间隔（秒）
    
    def __init__(self):
        self._states: Dict[str, TaskState] = {}  # task_id -> state
        self._callbacks: Dict[str, List[Callable]] = {}  # task_id -> callbacks
        self._lock = asyncio.Lock()
        self._monitor_task: Optional[asyncio.Task] = None
        
    async def start_monitor(self) -> None:
        """启动状态监控"""
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        
    async def stop_monitor(self) -> None:
        """停止状态监控"""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
                
    async def _monitor_loop(self) -> None:
        """监控循环 - 检测超时任务"""
        while True:
            try:
                await asyncio.sleep(self.STATE_CHECK_INTERVAL)
                await self._check_timeouts()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Monitor error: %s", exc)
                
    async def _check_timeouts(self) -> None:
        """检查心跳超时"""
        now = datetime.now()
        async with self._lock:
            for task_id, state in list(self._states.items()):
                if state.status in {TaskStatus.RUNNING, TaskStatus.PAUSING, TaskStatus.CANCELLING}:
                    # 检查心跳
                    if state.heartbeat_at:
                        elapsed = (now - state.heartbeat_at).total_seconds()
                        if elapsed > self.HEARTBEAT_TIMEOUT:
                            logger.warning(
                                "Task %s heartbeat timeout (%.1fs), marking as failed",
                                task_id, elapsed
                            )
                            await self._update_state(
                                task_id,
                                TaskStatus.FAILED,
                                f"Worker timeout (no heartbeat for {elapsed:.1f}s)"
                            )
                            
    async def register_state(self, task_id: str, initial_state: TaskState) -> None:
        """注册任务状态"""
        async with self._lock:
            self._states[task_id] = initial_state
            self._callbacks[task_id] = []
        logger.info("Task %s state registered: %s", task_id, initial_state.status.value)
        
    async def update_state(
        self,
        task_id: str,
        status: TaskStatus,
        message: Optional[str] = None,
        phase: Optional[str] = None,
        progress: Optional[tuple[int, int]] = None,
        worker_id: Optional[str] = None
    ) -> TaskState:
        """更新状态（带校验）"""
        async with self._lock:
            if task_id not in self._states:
                raise ValueError(f"Task {task_id} not registered")
                
            current = self._states[task_id]
            
            # 状态流转校验
            if not self._is_valid_transition(current.status, status):
                logger.warning(
                    "Invalid state transition: %s -> %s for task %s",
                    current.status.value, status.value, task_id
                )
                # 强制更新为失败状态
                status = TaskStatus.FAILED
                message = message or f"Invalid state transition from {current.status.value}"
                
            # 更新状态
            current.status = status
            if message is not None:
                current.message = message
            if phase is not None:
                current.phase = phase
            if progress is not None:
                current.progress_current, current.progress_total = progress
            if worker_id is not None:
                current.worker_id = worker_id
            current.updated_at = datetime.now()
            
            # 如果是活跃状态，更新心跳
            if status in {TaskStatus.RUNNING, TaskStatus.PAUSING, TaskStatus.CANCELLING}:
                current.heartbeat_at = datetime.now()
                
            self._states[task_id] = current
            
            # 触发回调
            callbacks = self._callbacks.get(task_id, []).copy()
            
        # 在锁外执行回调
        for callback in callbacks:
            try:
                await callback(current)
            except Exception as exc:
                logger.exception("State callback error: %s", exc)
                
        logger.debug("Task %s state updated: %s", task_id, status.value)
        return current
        
    async def heartbeat(self, task_id: str, worker_id: str) -> bool:
        """心跳更新"""
        async with self._lock:
            if task_id not in self._states:
                return False
                
            state = self._states[task_id]
            
            # 校验 worker_id
            if state.worker_id and state.worker_id != worker_id:
                logger.warning(
                    "Worker mismatch for task %s: expected %s, got %s",
                    task_id, state.worker_id, worker_id
                )
                return False
                
            state.heartbeat_at = datetime.now()
            state.updated_at = datetime.now()
            self._states[task_id] = state
            
        return True
        
    async def get_state(self, task_id: str) -> Optional[TaskState]:
        """获取当前状态"""
        async with self._lock:
            return self._states.get(task_id)
            
    async def subscribe(self, task_id: str, callback: Callable[[TaskState], None]) -> None:
        """订阅状态变更"""
        async with self._lock:
            if task_id not in self._callbacks:
                self._callbacks[task_id] = []
            self._callbacks[task_id].append(callback)
            
    async def unsubscribe(self, task_id: str, callback: Callable[[TaskState], None]) -> None:
        """取消订阅"""
        async with self._lock:
            if task_id in self._callbacks:
                self._callbacks[task_id] = [c for c in self._callbacks[task_id] if c != callback]
                
    def _is_valid_transition(self, from_status: TaskStatus, to_status: TaskStatus) -> bool:
        """校验状态流转是否合法"""
        valid_transitions = {
            TaskStatus.PENDING: {TaskStatus.QUEUED, TaskStatus.CANCELLED},
            TaskStatus.QUEUED: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
            TaskStatus.RUNNING: {TaskStatus.PAUSING, TaskStatus.CANCELLING, TaskStatus.COMPLETED, TaskStatus.FAILED},
            TaskStatus.PAUSING: {TaskStatus.PAUSED, TaskStatus.CANCELLING, TaskStatus.FAILED},
            TaskStatus.PAUSED: {TaskStatus.RESUMING, TaskStatus.CANCELLED},
            TaskStatus.RESUMING: {TaskStatus.RUNNING, TaskStatus.CANCELLING, TaskStatus.FAILED},
            TaskStatus.CANCELLING: {TaskStatus.CANCELLED, TaskStatus.FAILED},
            TaskStatus.CANCELLED: set(),  # 终态
            TaskStatus.COMPLETED: set(),  # 终态
            TaskStatus.FAILED: set(),     # 终态
        }
        return to_status in valid_transitions.get(from_status, set())
        
    async def cleanup(self, task_id: str) -> None:
        """清理任务状态"""
        async with self._lock:
            self._states.pop(task_id, None)
            self._callbacks.pop(task_id, None)


# 全局实例
task_state_manager = TaskStateManager()
