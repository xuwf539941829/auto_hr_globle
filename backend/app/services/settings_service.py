from __future__ import annotations

import json

from app.core.logging import get_logger
from app.core.paths import DATA_DIR
from app.models.domain import LLMSettings
from app.schemas.settings import LLMSettingsUpdateRequest

logger = get_logger(__name__)


class SettingsService:
    def __init__(self) -> None:
        self._settings_path = DATA_DIR / "llm_settings.json"
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)

    def get_llm_settings(self) -> LLMSettings:
        if not self._settings_path.exists():
            logger.info("LLM settings file not found, returning defaults: %s", self._settings_path)
            return LLMSettings()

        try:
            payload = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.exception("Failed to read LLM settings from %s: %s", self._settings_path, exc)
            return LLMSettings()

        api_key = str(payload.get("api_key") or "")
        return LLMSettings(
            provider_label="OpenAI Compatible",
            enabled=bool(payload.get("enabled", False)),
            has_api_key=bool(api_key),
            api_key=api_key,
            base_url=str(payload.get("base_url") or "https://api.openai.com/v1"),
            model=str(payload.get("model") or "gpt-4.1-mini"),
            api_style=str(payload.get("api_style") or "chat_completions"),
            timeout_seconds=int(payload.get("timeout_seconds") or 45),
        )

    def update_llm_settings(self, payload: LLMSettingsUpdateRequest) -> LLMSettings:
        settings = {
            "enabled": payload.enabled,
            "api_key": payload.api_key.strip(),
            "base_url": payload.base_url.strip().rstrip("/"),
            "model": payload.model.strip(),
            "api_style": payload.api_style.strip(),
            "timeout_seconds": payload.timeout_seconds,
        }
        self._settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Updated LLM settings file: %s", self._settings_path)
        return self.get_llm_settings()


settings_service = SettingsService()
