from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException

from app.core.logging import get_logger
from app.models.domain import CandidateDetail
from app.services.boss_connector import BossConnectorError, boss_connector
from app.services.candidate_screening_service import candidate_screening_service
from app.services.job_service import job_service
from app.services.mock_data import build_candidates, store
from app.services.runtime_state_service import runtime_state_service

logger = get_logger(__name__)


class CandidateService:
    def __init__(self) -> None:
        self._live_cache: dict[str, dict[str, CandidateDetail]] = {}
        persisted = runtime_state_service.load_candidates(store.job.id)
        if persisted:
            self._live_cache[store.job.id] = {item.card.id: item for item in persisted}
            logger.info("Loaded %s persisted candidates for job %s", len(persisted), store.job.id)

    def list_candidates(self, job_id: str = "job-001") -> list[CandidateDetail]:
        candidates = list(self._live_cache.get(job_id, {}).values())
        if not candidates:
            persisted = runtime_state_service.load_candidates(job_id)
            if persisted:
                candidates = persisted
                self._live_cache[job_id] = {item.card.id: item for item in persisted}
                logger.info("Restored %s persisted candidates for job %s", len(persisted), job_id)
        if not candidates:
            candidates = self._load_live_candidates(job_id)

        candidates = self._backfill_boss_action_fields(job_id, candidates)

        # Only re-analyze candidates that don't have analysis yet
        analyzed = []
        for item in candidates:
            if item.analysis and item.analysis.score > 0:
                analyzed.append(item)
            else:
                analyzed.append(self._with_fresh_analysis(item, job_id))

        self._live_cache[job_id] = {item.card.id: item for item in analyzed}
        runtime_state_service.save_candidates(job_id, analyzed)
        logger.info("Saved analyzed candidates for job %s: %s items", job_id, len(analyzed))

        return analyzed

    def set_candidates(self, job_id: str, candidates: list[CandidateDetail]) -> None:
        self._live_cache[job_id] = {item.card.id: item for item in candidates}
        runtime_state_service.save_candidates(job_id, candidates)
        logger.info("Updated candidate cache for job %s: %s items", job_id, len(candidates))

    def clear_candidates(self, job_id: str) -> None:
        self._live_cache[job_id] = {}
        runtime_state_service.save_candidates(job_id, [])
        logger.info("Cleared candidate cache for job %s", job_id)

    def get_candidate_detail(self, candidate_id: str, job_id: str = "job-001") -> CandidateDetail:
        cached = self._live_cache.get(job_id, {})
        if candidate_id in cached:
            detail = cached[candidate_id]
            card = detail.card
            if card.source == "boss" and card.security_id and card.lid and self._needs_live_detail_refresh(detail):
                try:
                    live_detail = boss_connector.fetch_candidate_detail(job_id, card.security_id, card.lid)
                    live_detail = self._merge_boss_detail(detail, live_detail)
                    self._live_cache.setdefault(job_id, {})[candidate_id] = live_detail
                    runtime_state_service.save_candidates(job_id, list(self._live_cache[job_id].values()))
                    detail = live_detail
                    logger.info("Refreshed Boss detail for candidate %s job %s", candidate_id, job_id)
                except BossConnectorError as exc:
                    logger.warning("Failed to refresh Boss detail for candidate %s job %s: %s", candidate_id, job_id, exc)
            return self._with_fresh_analysis(detail, job_id)
        raise HTTPException(status_code=404, detail="Candidate not found")

    @staticmethod
    def _needs_live_detail_refresh(detail: CandidateDetail) -> bool:
        if detail.parsed_resume is not None:
            return False
        if len(detail.timeline) == 1 and "Boss card only" in detail.timeline[0]:
            return True
        if detail.original_resume.strip() == "Boss card summary only.":
            return True
        return False

    def mark_action(self, candidate_id: str, action: str, job_id: str = "job-001") -> CandidateDetail:
        cached = self._live_cache.get(job_id, {})
        if candidate_id in cached:
            detail = cached[candidate_id]
            if detail.card.source == "boss":
                detail = self.apply_action_to_detail(detail, action, job_id)
                self._live_cache[job_id][candidate_id] = detail
                runtime_state_service.save_candidates(job_id, list(self._live_cache[job_id].values()))
                logger.info("Completed Boss action %s for candidate %s job %s", action, candidate_id, job_id)
                return detail
        raise HTTPException(status_code=404, detail="Candidate not found")

    def apply_action_to_detail(self, detail: CandidateDetail, action: str, job_id: str = "job-001") -> CandidateDetail:
        updated = CandidateDetail(**detail.model_dump())
        if updated.card.source != "boss":
            return updated

        updated = self._refresh_boss_fields_for_action(updated, job_id, action)
        self._run_live_action(updated, action, job_id)
        now = datetime.now().isoformat()
        if action == "collect":
            updated.card.collected = True
            updated.card.collected_at = now
            print(f"[收藏] {updated.card.name}  job={job_id}  at={now}")
        if action == "greet":
            updated.card.greeted = True
            updated.card.greeted_at = now
            print(f"[打招呼] {updated.card.name}  job={job_id}  at={now}")
        return updated

    def _load_live_candidates(self, job_id: str) -> list[CandidateDetail]:
        try:
            live_candidates = boss_connector.fetch_recommended_candidates(job_id)
        except BossConnectorError as exc:
            logger.warning("Failed to load live Boss candidates for job %s: %s, using mock data", job_id, exc)
            live_candidates = build_candidates()

        job_cache: dict[str, CandidateDetail] = {}
        for item in live_candidates:
            job_cache[item.card.id] = item
        self._live_cache[job_id] = job_cache
        runtime_state_service.save_candidates(job_id, list(job_cache.values()))
        logger.info("Loaded and persisted %s live Boss candidates for job %s", len(job_cache), job_id)
        return list(job_cache.values())

    def _with_fresh_analysis(self, detail: CandidateDetail, job_id: str) -> CandidateDetail:
        refreshed = CandidateDetail(**detail.model_dump())
        profile = job_service.get_current_profile(job_id)
        blueprint = candidate_screening_service.build_screening_blueprint(profile)
        parsed_resume = candidate_screening_service.parse_resume(refreshed)
        analysis = candidate_screening_service.analyze(
            profile,
            refreshed,
            parsed_resume=parsed_resume,
            blueprint=blueprint,
        )
        refreshed.screening_blueprint = blueprint
        refreshed.parsed_resume = parsed_resume
        refreshed.analysis = analysis
        refreshed.card.score = analysis.score
        refreshed.card.grade = analysis.grade
        refreshed.card.summary = analysis.summary
        refreshed.card.risk_tags = list(dict.fromkeys([*analysis.risk_items[:2], *analysis.timeline_risks[:1]]))
        return refreshed

    def _backfill_boss_action_fields(self, job_id: str, candidates: list[CandidateDetail]) -> list[CandidateDetail]:
        missing_candidates = [
            item
            for item in candidates
            if item.card.source == "boss" and self._missing_boss_action_fields(item, "greet")
        ]
        if not missing_candidates:
            return candidates

        field_index = boss_connector.build_candidate_card_field_index(job_id)
        if not field_index:
            return candidates

        updated_candidates: list[CandidateDetail] = []
        changed = False
        for item in candidates:
            if item.card.source != "boss" or not item.card.security_id:
                updated_candidates.append(item)
                continue

            fields = field_index.get(item.card.security_id)
            if not fields:
                updated_candidates.append(item)
                continue

            updated = CandidateDetail(**item.model_dump())
            item_changed = False
            for field_name, value in fields.items():
                if value and not getattr(updated.card, field_name):
                    setattr(updated.card, field_name, value)
                    item_changed = True
            updated_candidates.append(updated)
            changed = changed or item_changed

        if changed:
            logger.info("Backfilled Boss action fields for job %s", job_id)
        return updated_candidates

    @staticmethod
    def _merge_boss_detail(current: CandidateDetail, live: CandidateDetail) -> CandidateDetail:
        for field_name in ("security_id", "lid", "encrypt_geek_id", "encrypt_job_id", "expect_id", "design_greeting"):
            if not getattr(live.card, field_name):
                setattr(live.card, field_name, getattr(current.card, field_name))

        if not live.card.current_company or live.card.current_company == "Unknown":
            live.card.current_company = current.card.current_company
        if not live.card.current_position or live.card.current_position == "Unknown":
            live.card.current_position = current.card.current_position

        live.card.collected = current.card.collected
        live.card.collected_at = current.card.collected_at
        live.card.greeted = current.card.greeted
        live.card.greeted_at = current.card.greeted_at
        return live

    def _refresh_boss_fields_for_action(self, detail: CandidateDetail, job_id: str, action: str) -> CandidateDetail:
        if detail.card.source != "boss" or not detail.card.security_id or not detail.card.lid:
            return detail

        missing_before = self._missing_boss_action_fields(detail, action)
        if not missing_before:
            return detail

        logger.info(
            "Refreshing Boss action fields for candidate=%s job=%s action=%s missing=%s current_fields=%s",
            detail.card.id,
            job_id,
            action,
            ",".join(missing_before),
            {
                "security_id": detail.card.security_id,
                "lid": detail.card.lid,
                "encrypt_geek_id": detail.card.encrypt_geek_id,
                "encrypt_job_id": detail.card.encrypt_job_id,
                "expect_id": detail.card.expect_id,
            },
        )

        list_fields = boss_connector.find_candidate_card_fields(job_id, detail.card.security_id, detail.card.lid)
        updated = CandidateDetail(**detail.model_dump())
        for field_name, value in list_fields.items():
            if value and not getattr(updated.card, field_name):
                setattr(updated.card, field_name, value)

        if not self._missing_boss_action_fields(updated, action):
            logger.info(
                "Recovered Boss action fields from recommend list for candidate=%s job=%s fields=%s",
                detail.card.id,
                job_id,
                {
                    "security_id": updated.card.security_id,
                    "lid": updated.card.lid,
                    "encrypt_geek_id": updated.card.encrypt_geek_id,
                    "encrypt_job_id": updated.card.encrypt_job_id,
                    "expect_id": updated.card.expect_id,
                },
            )
            self._live_cache.setdefault(job_id, {})[detail.card.id] = updated
            runtime_state_service.save_candidates(job_id, list(self._live_cache[job_id].values()))
            return updated

        try:
            live_detail = boss_connector.fetch_candidate_detail(job_id, detail.card.security_id, detail.card.lid)
        except BossConnectorError as exc:
            logger.warning(
                "Failed to refresh Boss action fields for candidate %s job %s: %s",
                detail.card.id,
                job_id,
                exc,
            )
            return detail

        merged = self._merge_boss_detail(detail, live_detail)
        logger.info(
            "Recovered Boss action fields from detail refresh for candidate=%s job=%s fields=%s",
            detail.card.id,
            job_id,
            {
                "security_id": merged.card.security_id,
                "lid": merged.card.lid,
                "encrypt_geek_id": merged.card.encrypt_geek_id,
                "encrypt_job_id": merged.card.encrypt_job_id,
                "expect_id": merged.card.expect_id,
            },
        )
        self._live_cache.setdefault(job_id, {})[detail.card.id] = merged
        runtime_state_service.save_candidates(job_id, list(self._live_cache[job_id].values()))
        return merged

    @staticmethod
    def _missing_boss_action_fields(detail: CandidateDetail, action: str) -> list[str]:
        card = detail.card
        required_fields = {
            "collect": {
                "security_id": card.security_id,
                "encrypt_geek_id": card.encrypt_geek_id,
            },
            "greet": {
                "lid": card.lid,
                "encrypt_geek_id": card.encrypt_geek_id,
                "encrypt_job_id": card.encrypt_job_id,
                "expect_id": card.expect_id,
                "security_id": card.security_id,
            },
        }.get(action, {})
        return [name for name, value in required_fields.items() if not value]

    @staticmethod
    def _run_live_action(detail: CandidateDetail, action: str, job_id: str) -> None:
        card = detail.card
        if not card.security_id:
            raise HTTPException(status_code=400, detail="Candidate is missing Boss security_id.")

        if action == "collect":
            if not card.encrypt_geek_id:
                raise HTTPException(status_code=400, detail="Candidate is missing Boss encrypt_geek_id.")
            try:
                boss_connector.collect_candidate(job_id, security_id=card.security_id, encrypt_geek_id=card.encrypt_geek_id)
            except BossConnectorError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            return

        if action == "greet":
            missing = CandidateService._missing_boss_action_fields(detail, action)
            if missing:
                logger.warning(
                    "Boss greet blocked for candidate=%s job=%s missing=%s fields=%s",
                    detail.card.id,
                    job_id,
                    ",".join(missing),
                    {
                        "security_id": card.security_id,
                        "lid": card.lid,
                        "encrypt_geek_id": card.encrypt_geek_id,
                        "encrypt_job_id": card.encrypt_job_id,
                        "expect_id": card.expect_id,
                    },
                )
                raise HTTPException(status_code=400, detail=f"Candidate is missing Boss fields: {', '.join(missing)}")
            try:
                boss_connector.greet_candidate(
                    job_id,
                    lid=card.lid or "",
                    security_id=card.security_id,
                    encrypt_geek_id=card.encrypt_geek_id or "",
                    encrypt_job_id=card.encrypt_job_id or "",
                    expect_id=card.expect_id or "",
                    design_greeting=card.design_greeting,
                )
            except BossConnectorError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc


candidate_service = CandidateService()
