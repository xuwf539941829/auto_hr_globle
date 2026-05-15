from datetime import datetime
from typing import Optional, Dict, List
import json
import os
from app.models.domain import ScreeningTask, ScreeningConfig, CandidateDetail
from app.core.logging import get_logger
from app.core.paths import DATA_DIR

logger = get_logger(__name__)

_DEFAULT_STORAGE_DIR = str(DATA_DIR / "tasks")


class TaskStorage:
    """任务持久化存储"""

    def __init__(self, storage_dir: str = _DEFAULT_STORAGE_DIR):
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)
        
        self._tasks: Dict[str, ScreeningTask] = {}  # task_id -> task
        self._configs: Dict[str, ScreeningConfig] = {}  # job_id -> config
        
    def _get_task_dir(self, task_id: str) -> str:
        """获取任务存储目录"""
        return os.path.join(self.storage_dir, task_id)
    
    def _save_task_file(self, task_id: str, filename: str, data: dict) -> None:
        """保存任务文件"""
        task_dir = self._get_task_dir(task_id)
        os.makedirs(task_dir, exist_ok=True)
        filepath = os.path.join(task_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, default=str)
    
    def _load_task_file(self, task_id: str, filename: str) -> Optional[dict]:
        """加载任务文件"""
        filepath = os.path.join(self._get_task_dir(task_id), filename)
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def save_task(self, task: ScreeningTask) -> None:
        """保存任务"""
        self._tasks[task.id] = task
        self._save_task_file(task.id, "task_info.json", task.model_dump())
        logger.info("Task saved: %s", task.id)
    
    def get_task(self, task_id: str) -> Optional[ScreeningTask]:
        """获取任务"""
        cached = self._tasks.get(task_id)
        if cached is not None:
            return cached

        data = self._load_task_file(task_id, "task_info.json")
        if not data:
            return None

        try:
            if data.get("status") == "queued":
                data = {**data, "status": "pending"}
            task = ScreeningTask(**data)
        except Exception as exc:
            logger.exception("Failed to parse task %s from storage: %s", task_id, exc)
            return None

        self._tasks[task_id] = task
        return task
    
    def save_candidates(self, task_id: str, candidates: List[CandidateDetail]) -> None:
        """保存候选人列表"""
        data = [c.model_dump() for c in candidates]
        self._save_task_file(task_id, "candidates.json", data)
        logger.info("Saved %s candidates for task %s", len(candidates), task_id)
    
    def get_candidates(self, task_id: str) -> List[CandidateDetail]:
        """获取候选人列表"""
        data = self._load_task_file(task_id, "candidates.json")
        if not data:
            return []
        return [CandidateDetail(**item) for item in data]
    
    def save_config(self, config: ScreeningConfig) -> None:
        """保存配置"""
        self._configs[config.job_id] = config
        logger.info("Config saved for job %s", config.job_id)
    
    def get_config(self, job_id: str) -> Optional[ScreeningConfig]:
        """获取配置"""
        return self._configs.get(job_id)
    
    def get_recent_tasks(self, limit: int = 20) -> List[ScreeningTask]:
        """获取最近任务"""
        for entry in os.listdir(self.storage_dir):
            self.get_task(entry)

        tasks = sorted(
            self._tasks.values(),
            key=lambda t: t.updated_at if hasattr(t, 'updated_at') else datetime.now(),
            reverse=True
        )
        unique_by_job: Dict[str, ScreeningTask] = {}
        for task in tasks:
            if task.job_id not in unique_by_job:
                unique_by_job[task.job_id] = task
        return list(unique_by_job.values())[:limit]
    
    def get_running_tasks(self) -> List[ScreeningTask]:
        """获取运行中的任务"""
        return [t for t in self._tasks.values() if t.status == "running"]
    
    def clear_task_data(self, task_id: str) -> None:
        """清空任务数据"""
        task_dir = self._get_task_dir(task_id)
        if os.path.exists(task_dir):
            for file in os.listdir(task_dir):
                os.remove(os.path.join(task_dir, file))
        logger.info("Task data cleared: %s", task_id)


# 全局实例
task_storage = TaskStorage()
