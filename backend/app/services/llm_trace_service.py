from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.core.paths import DATA_DIR

logger = get_logger(__name__)


class LLMTraceService:
    def __init__(self) -> None:
        self.base_dir = DATA_DIR / "llm_traces"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def record_request(self, trace_id: str, endpoint: str, payload: dict[str, Any]) -> None:
        trace = self._read_trace(trace_id)
        trace.update(
            {
                "trace_id": trace_id,
                "updated_at": self._now(),
                "endpoint": endpoint,
                "request": payload,
            }
        )
        self._write_trace(trace_id, trace)

    def record_response(self, trace_id: str, body: str) -> None:
        trace = self._read_trace(trace_id)
        trace.update(
            {
                "trace_id": trace_id,
                "updated_at": self._now(),
                "response": body,
            }
        )
        self._write_trace(trace_id, trace)

    def record_error(self, trace_id: str, message: str) -> None:
        trace = self._read_trace(trace_id)
        errors = trace.get("errors", [])
        if not isinstance(errors, list):
            errors = []
        errors.append({"at": self._now(), "message": message})
        trace.update(
            {
                "trace_id": trace_id,
                "updated_at": self._now(),
                "errors": errors,
            }
        )
        self._write_trace(trace_id, trace)

    def record_metadata(self, trace_id: str, **metadata: Any) -> None:
        trace = self._read_trace(trace_id)
        existing = trace.get("metadata", {})
        if not isinstance(existing, dict):
            existing = {}
        existing.update(metadata)
        trace.update(
            {
                "trace_id": trace_id,
                "updated_at": self._now(),
                "metadata": existing,
            }
        )
        self._write_trace(trace_id, trace)

    def list_traces(self, limit: int = 30) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        files = sorted(self.base_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        for path in files[:limit]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                items.append(
                    {
                        "trace_id": payload.get("trace_id", path.stem),
                        "updated_at": payload.get("updated_at"),
                        "endpoint": payload.get("endpoint"),
                        "metadata": payload.get("metadata", {}),
                        "has_response": bool(payload.get("response")),
                        "error_count": len(payload.get("errors", [])) if isinstance(payload.get("errors"), list) else 0,
                    }
                )
            except Exception as exc:
                logger.exception("Failed to read LLM trace summary from %s: %s", path, exc)
        return items

    def get_trace(self, trace_id: str) -> dict[str, Any]:
        path = self._trace_path(trace_id)
        if not path.exists():
            raise FileNotFoundError(trace_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def _read_trace(self, trace_id: str) -> dict[str, Any]:
        path = self._trace_path(trace_id)
        if not path.exists():
            return {"trace_id": trace_id, "created_at": self._now()}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.exception("Failed to parse LLM trace %s: %s", trace_id, exc)
            return {"trace_id": trace_id, "created_at": self._now()}

    def _write_trace(self, trace_id: str, payload: dict[str, Any]) -> None:
        path = self._trace_path(trace_id)
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.exception("Failed to write LLM trace %s: %s", trace_id, exc)

    def _trace_path(self, trace_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in trace_id)
        return self.base_dir / f"{safe}.json"

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")


llm_trace_service = LLMTraceService()
