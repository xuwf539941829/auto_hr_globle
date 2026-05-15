from __future__ import annotations

from datetime import datetime
import json
import re
import threading
from typing import Any

from app.core.logging import get_logger
from app.core.paths import RUNTIME_STATE_PATH
from app.models.domain import CandidateDetail, JobProfileWorkbench, ScreeningTask

logger = get_logger(__name__)

LEGACY_DEMO_JOB_IDS = {"job-001"}


class RuntimeStateService:
    def __init__(self) -> None:
        self._path = RUNTIME_STATE_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()

    def load_state(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"workbenches": {}, "tasks": {}, "candidates": {}}

        raw: str | None = None
        for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
            try:
                raw = self._path.read_text(encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        if raw is None:
            try:
                raw = self._path.read_bytes().decode("utf-8", errors="replace")
                logger.warning("Runtime state file has encoding errors; loaded with replacement characters.")
            except Exception as exc:
                logger.exception("Cannot read runtime state file: %s", exc)
                return {"workbenches": {}, "tasks": {}, "candidates": {}}

        repaired = False
        try:
            payload = json.loads(raw)
        except Exception as exc:
            logger.exception("Failed to load runtime state file: %s", exc)
            repaired_raw = self._repair_legacy_state_text(raw)
            if repaired_raw == raw:
                return {"workbenches": {}, "tasks": {}, "candidates": {}}
            try:
                payload = json.loads(repaired_raw)
                repaired = True
            except Exception as repaired_exc:
                logger.exception("Failed to repair runtime state file: %s", repaired_exc)
                return {"workbenches": {}, "tasks": {}, "candidates": {}}

        if not isinstance(payload, dict):
            logger.warning("Runtime state root is not an object. Resetting to empty state.")
            return {"workbenches": {}, "tasks": {}, "candidates": {}}

        normalized = self._normalize_state(payload)
        normalized_repaired = self._repair_mojibake_in_state(normalized)
        sanitized = self._sanitize_legacy_state(normalized_repaired)
        if repaired or normalized_repaired != normalized or sanitized != normalized_repaired:
            self._write_state(sanitized, "Sanitized runtime state")
        return sanitized

    def save_workbench(self, job_id: str, workbench: JobProfileWorkbench) -> None:
        with self._write_lock:
            state = self.load_state()
            state["workbenches"][job_id] = workbench.model_dump(mode="json")
            self._write_state(state, f"Saved workbench for {job_id}")

    def load_workbench(self, job_id: str) -> JobProfileWorkbench | None:
        state = self.load_state()
        payload = state["workbenches"].get(job_id)
        if not payload:
            return None
        try:
            return JobProfileWorkbench(**payload)
        except Exception as exc:
            logger.exception("Failed to parse persisted workbench for %s: %s", job_id, exc)
            return None

    def save_task(self, task: ScreeningTask) -> None:
        with self._write_lock:
            state = self.load_state()
            state["tasks"][task.id] = task.model_dump(mode="json")
            state["tasks"]["current"] = task.id
            self._write_state(state, f"Saved task {task.id}")

    def load_current_task(self) -> ScreeningTask | None:
        state = self.load_state()
        current_id = state["tasks"].get("current")
        if not current_id:
            return None
        payload = state["tasks"].get(current_id)
        if not payload:
            return None
        try:
            return ScreeningTask(**payload)
        except Exception as exc:
            logger.exception("Failed to parse persisted task %s: %s", current_id, exc)
            return None

    def save_candidates(self, job_id: str, candidates: list[CandidateDetail]) -> None:
        with self._write_lock:
            state = self.load_state()
            state["candidates"][job_id] = [item.model_dump(mode="json") for item in candidates]
            self._write_state(state, f"Saved {len(candidates)} candidates for {job_id}")

    def load_candidates(self, job_id: str) -> list[CandidateDetail]:
        state = self.load_state()
        payload = state["candidates"].get(job_id) or []
        results: list[CandidateDetail] = []
        for item in payload:
            try:
                results.append(CandidateDetail(**item))
            except Exception as exc:
                logger.exception("Failed to parse persisted candidate for %s: %s", job_id, exc)
        return results

    def _write_state(self, state: dict[str, Any], context: str) -> None:
        try:
            self._path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("%s -> %s", context, self._path)
        except Exception as exc:
            logger.exception("Failed to write runtime state for %s: %s", context, exc)

    @staticmethod
    def _normalize_state(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "workbenches": payload.get("workbenches", {}) or {},
            "tasks": payload.get("tasks", {}) or {},
            "candidates": payload.get("candidates", {}) or {},
        }

    @classmethod
    def _repair_mojibake_in_state(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: cls._repair_mojibake_in_state(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._repair_mojibake_in_state(item) for item in value]
        if isinstance(value, str):
            return cls._repair_mojibake_text(value)
        return value

    @staticmethod
    def _repair_mojibake_text(value: str) -> str:
        current = value
        for _ in range(3):
            if re.search(r"[\u4e00-\u9fff]", current):
                break
            if not re.search(r"[ÃÂçæåéèêôöûîïóúíáàäüñ]", current):
                break
            try:
                repaired = current.encode("latin-1").decode("utf-8")
            except UnicodeError:
                break
            if repaired == current:
                break
            current = repaired
        return current

    @staticmethod
    def _repair_legacy_state_text(raw: str) -> str:
        repaired = raw
        repaired = re.sub(
            r'"message":\s*"[^"\r\n]*\?,\r?\n',
            '"message": "筛选任务因后端重启已中断，请重新开始筛选。",\n',
            repaired,
            count=1,
        )
        return repaired

    def _sanitize_legacy_state(self, state: dict[str, Any]) -> dict[str, Any]:
        workbenches = {
            job_id: payload
            for job_id, payload in state["workbenches"].items()
            if job_id not in LEGACY_DEMO_JOB_IDS
        }
        candidates = {
            job_id: payload
            for job_id, payload in state["candidates"].items()
            if job_id not in LEGACY_DEMO_JOB_IDS
        }

        raw_tasks = state["tasks"]
        current_id = raw_tasks.get("current")
        kept_tasks: dict[str, dict[str, Any]] = {}
        current_migrated_id: str | None = None

        for task_key, payload in raw_tasks.items():
            if task_key == "current" or not isinstance(payload, dict):
                continue

            job_id = payload.get("job_id")
            if job_id in LEGACY_DEMO_JOB_IDS:
                continue

            migrated_id = f"task-{job_id}" if job_id else str(payload.get("id") or task_key)
            migrated_payload = {**payload, "id": migrated_id}
            existing = kept_tasks.get(migrated_id)
            if existing is None or self._task_updated_at(migrated_payload) >= self._task_updated_at(existing):
                kept_tasks[migrated_id] = migrated_payload

            if current_id == task_key or current_id == payload.get("id"):
                current_migrated_id = migrated_id

        tasks: dict[str, Any] = dict(kept_tasks)
        if current_migrated_id and current_migrated_id in kept_tasks:
            tasks["current"] = current_migrated_id
        elif kept_tasks:
            latest_task = max(kept_tasks.values(), key=self._task_updated_at)
            tasks["current"] = str(latest_task.get("id"))

        return {
            "workbenches": workbenches,
            "tasks": tasks,
            "candidates": candidates,
        }

    @staticmethod
    def _task_updated_at(task_payload: dict[str, Any]) -> datetime:
        updated_at = task_payload.get("updated_at")
        if isinstance(updated_at, str):
            try:
                return datetime.fromisoformat(updated_at)
            except ValueError:
                return datetime.min
        return datetime.min


runtime_state_service = RuntimeStateService()
