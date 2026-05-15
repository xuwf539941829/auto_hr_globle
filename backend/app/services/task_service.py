from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
import random
import time
from typing import Any

from app.core.logging import get_logger
from app.models.domain import CandidateDetail, ScreeningTask
from app.services.boss_connector import BossConnectorError, boss_connector
from app.services.candidate_service import candidate_service
from app.services.candidate_screening_service import candidate_screening_service
from app.services.job_service import job_service
from app.services.mock_data import store
from app.services.runtime_state_service import runtime_state_service
from app.services.task_storage import task_storage

logger = get_logger(__name__)


class TaskService:
    def __init__(self) -> None:
        self._stream_events: dict[str, list[dict[str, Any]]] = {}
        self._stream_seq = 0
        persisted = runtime_state_service.load_current_task()
        if persisted is not None:
            if persisted.status in {"running", "paused"}:
                persisted.status = "failed"
                persisted.updated_at = datetime.now()
                persisted.message = "筛选任务因后端重启已中断，请重新开始筛选。"
                runtime_state_service.save_task(persisted)
                task_storage.save_task(persisted)
            store.task = persisted
            store.candidates = runtime_state_service.load_candidates(persisted.job_id)
            if store.candidates:
                candidate_service.set_candidates(persisted.job_id, store.candidates)
            logger.info("Loaded persisted screening task: %s", persisted.id)

    def get_task(self) -> ScreeningTask:
        return store.task

    @staticmethod
    def _task_id_for_job(job_id: str) -> str:
        return f"task-{job_id}"

    def pause(self) -> ScreeningTask:
        store.task.status = "paused"
        store.task.updated_at = datetime.now()
        store.task.message = "Task paused. Waiting for manual resume."
        runtime_state_service.save_task(store.task)
        self._publish_task_event(store.task.job_id)
        logger.info("Paused task %s", store.task.id)
        return store.task

    def resume(self) -> ScreeningTask:
        store.task.status = "running"
        store.task.updated_at = datetime.now()
        store.task.message = "Task resumed. Continue fetching and screening."
        runtime_state_service.save_task(store.task)
        self._publish_task_event(store.task.job_id)
        logger.info("Resumed task %s", store.task.id)
        return store.task

    def clear_task_results(self, task_id: str) -> ScreeningTask:
        task_storage.clear_task_data(task_id)
        candidate_service.clear_candidates(store.task.job_id)
        if store.task.id == task_id:
            store.candidates = []
            store.task.candidate_count = 0
            store.task.auto_pass_count = 0
            store.task.grade_counts = {}
            store.task.progress_current = 0
            store.task.progress_total = max(1, store.task.progress_total)
            store.task.message = "Task data cleared"
            store.task.updated_at = datetime.now()
            runtime_state_service.save_task(store.task)
            self._reset_stream(store.task.job_id)
            self._publish_task_event(store.task.job_id)
        logger.info("Cleared screening results for task %s", task_id)
        return store.task

    def start_screening(self, job_id: str, pages: int = 1) -> ScreeningTask:
        profile = job_service.get_current_profile(job_id)
        job = job_service.get_job(job_id)
        now = datetime.now()
        candidate_service.clear_candidates(job_id)
        if store.task.job_id == job_id:
            store.candidates = []
        store.task.id = self._task_id_for_job(job_id)
        store.task.job_id = job_id
        store.task.job_name = job.name
        store.task.profile_version_id = profile.version_id
        store.task.status = "running"
        store.task.started_at = now
        store.task.updated_at = now
        store.task.progress_current = 0
        store.task.progress_total = max(1, pages)
        store.task.message = f"Scanning Boss candidates for {job_id}..."
        store.task.candidate_count = 0
        store.task.auto_pass_count = 0
        store.task.grade_counts = {}
        runtime_state_service.save_task(store.task)
        task_storage.save_task(store.task)
        self._reset_stream(job_id)
        self._publish_task_event(job_id)
        logger.info("Started screening task for job %s, pages=%s", job_id, pages)
        return store.task

    def run_screening(self, job_id: str, pages: int = 200, skip_seen: bool = True) -> ScreeningTask:
        profile = job_service.get_current_profile(job_id)
        if store.task.job_id != job_id or store.task.status not in {"running", "paused"}:
            self.start_screening(job_id, pages)

        # When skip_seen=True, restore previously screened candidates from disk so we
        # don't re-fetch or re-analyze them in this run.  When skip_seen=False (full
        # restart) the caller is responsible for clearing disk data beforehand via
        # clear_task_results(); we start with an empty collected list.
        if skip_seen:
            task_id = self._task_id_for_job(job_id)
            prev_candidates = task_storage.get_candidates(task_id)
            collected: list[CandidateDetail] = list(prev_candidates)
            seen_ids: set[str] = {c.card.id for c in collected}
            if collected:
                candidate_service.set_candidates(job_id, collected)
                store.candidates = collected
                store.task.candidate_count = len(collected)
                store.task.auto_pass_count = sum(1 for item in collected if item.analysis.pass_flag)
                store.task.grade_counts = {
                    "S": sum(1 for item in collected if item.analysis.grade == "S"),
                    "A": sum(1 for item in collected if item.analysis.grade == "A"),
                    "B": sum(1 for item in collected if item.analysis.grade == "B"),
                    "C": sum(1 for item in collected if item.analysis.grade == "C"),
                }
                store.task.message = f"已恢复 {len(collected)} 个历史候选人，继续扫描新简历..."
                runtime_state_service.save_task(store.task)
                self._publish_task_event(job_id)
                logger.info(
                    "skip_seen=True: restored %s previously screened candidates for job %s",
                    len(collected),
                    job_id,
                )
        else:
            collected = []
            seen_ids = set()
            logger.info("skip_seen=False: starting fresh for job %s", job_id)

        page = 0

        while True:
            page += 1
            if page > pages:
                logger.info("Reached safety page cap (%s), stopping.", pages)
                break

            self._wait_if_paused()
            try:
                logger.info("Calling Boss recommend list for job=%s page=%s", job_id, page)
                page_candidates = boss_connector.fetch_recommended_candidates(job_id, page=page)
                logger.info("Fetched %s candidates from Boss for job %s page %s", len(page_candidates), job_id, page)
            except BossConnectorError as exc:
                logger.exception("Boss screening failed for job %s page %s: %s", job_id, page, exc)
                if not collected:
                    store.task.status = "failed"
                    store.task.updated_at = datetime.now()
                    store.task.message = f"Boss screening failed: {exc}"
                    runtime_state_service.save_task(store.task)
                    task_storage.save_task(store.task)
                    self._publish_task_event(job_id)
                    return store.task
                break

            if not page_candidates:
                logger.info("Boss returned empty page %s, no more candidates.", page)
                break

            # De-dup: skip candidates already processed in this run
            new_candidates = [c for c in page_candidates if c.card.id not in seen_ids]
            seen_ids.update(c.card.id for c in new_candidates)

            if not new_candidates:
                logger.info("Page %s has no new candidates (all already seen), stopping.", page)
                break

            store.task.updated_at = datetime.now()
            store.task.message = f"第 {page} 页: {len(new_candidates)} 个新候选人，筛选中..."
            runtime_state_service.save_task(store.task)
            task_storage.save_task(store.task)
            self._publish_task_event(job_id)

            # Pipeline: pre-fetch next candidate's Boss detail while LLM analyzes current
            with ThreadPoolExecutor(max_workers=1) as executor:
                next_future: Future[CandidateDetail] = executor.submit(
                    self._fetch_detail_safe, job_id, new_candidates[0]
                )
                for i, candidate in enumerate(new_candidates):
                    # Retrieve result of background fetch (blocks if not ready yet)
                    try:
                        detail_candidate = next_future.result()
                    except Exception as exc:
                        logger.warning("Background Boss detail fetch raised unexpectedly for candidate %s: %s", candidate.card.id, exc)
                        detail_candidate = candidate

                    self._wait_if_paused()

                    # Immediately kick off fetch for next candidate — runs while LLM works below
                    if i + 1 < len(new_candidates):
                        next_future = executor.submit(
                            self._fetch_detail_safe, job_id, new_candidates[i + 1]
                        )

                    try:
                        detail_candidate.analysis = candidate_screening_service.analyze(profile, detail_candidate)
                    except Exception as exc:
                        logger.exception("Unexpected error analyzing candidate=%s, skipping: %s", detail_candidate.card.id, exc)
                        store.task.updated_at = datetime.now()
                        store.task.message = f"分析异常跳过: {detail_candidate.card.name}"
                        runtime_state_service.save_task(store.task)
                        task_storage.save_task(store.task)
                        self._publish_task_event(job_id)
                        continue
                    detail_candidate.card.score = detail_candidate.analysis.score
                    detail_candidate.card.grade = detail_candidate.analysis.grade
                    detail_candidate.card.summary = detail_candidate.analysis.summary
                    detail_candidate.card.risk_tags = list(
                        dict.fromkeys([*detail_candidate.analysis.risk_items[:2], *detail_candidate.analysis.timeline_risks[:1]])
                    )
                    if not self._is_publishable_candidate(detail_candidate):
                        logger.info(
                            "Skip candidate push for job=%s candidate=%s because detail/authorization is incomplete",
                            job_id,
                            detail_candidate.card.id,
                        )
                        store.task.updated_at = datetime.now()
                        store.task.message = f"Skipped incomplete resume: {detail_candidate.card.name}"
                        runtime_state_service.save_task(store.task)
                        task_storage.save_task(store.task)
                        self._publish_task_event(job_id)
                        continue

                    collected = self._upsert_candidate(collected, detail_candidate)
                    candidate_service.set_candidates(job_id, collected)
                    detail_candidate = self._apply_auto_actions(job_id, detail_candidate)
                    collected = self._upsert_candidate(collected, detail_candidate)
                    candidate_service.set_candidates(job_id, collected)
                    store.candidates = collected
                    store.task.candidate_count = len(collected)
                    store.task.auto_pass_count = sum(1 for item in collected if item.analysis.pass_flag)
                    store.task.grade_counts = {
                        "S": sum(1 for item in collected if item.analysis.grade == "S"),
                        "A": sum(1 for item in collected if item.analysis.grade == "A"),
                        "B": sum(1 for item in collected if item.analysis.grade == "B"),
                        "C": sum(1 for item in collected if item.analysis.grade == "C"),
                    }
                    store.task.updated_at = datetime.now()
                    store.task.message = f"已筛选 {len(collected)} 人，最新: {detail_candidate.card.name}"
                    runtime_state_service.save_task(store.task)
                    task_storage.save_task(store.task)
                    task_storage.save_candidates(store.task.id, collected)
                    self._publish_candidate_event(job_id, detail_candidate)
                    self._publish_task_event(job_id)

            store.task.progress_current = page
            store.task.updated_at = datetime.now()
            store.task.message = f"第 {page} 页完成，累计 {len(collected)} 人。继续抓取下一页..."
            store.task.candidate_count = len(collected)
            store.task.auto_pass_count = sum(1 for item in collected if item.analysis.pass_flag)
            store.task.grade_counts = {
                "S": sum(1 for item in collected if item.analysis.grade == "S"),
                "A": sum(1 for item in collected if item.analysis.grade == "A"),
                "B": sum(1 for item in collected if item.analysis.grade == "B"),
                "C": sum(1 for item in collected if item.analysis.grade == "C"),
            }
            runtime_state_service.save_task(store.task)
            task_storage.save_task(store.task)
            task_storage.save_candidates(store.task.id, collected)
            self._publish_task_event(job_id)

            # 页间随机延迟，模拟人工翻页
            time.sleep(random.uniform(1.0, 2.0))

        if collected:
            store.candidates = collected
            candidate_service.set_candidates(job_id, collected)
            store.task.status = "completed"
            store.task.updated_at = datetime.now()
            store.task.message = f"Completed screening. {len(collected)} candidates available for review."
            store.task.candidate_count = len(collected)
            store.task.auto_pass_count = sum(1 for item in collected if item.analysis.pass_flag)
            store.task.grade_counts = {
                "S": sum(1 for item in collected if item.analysis.grade == "S"),
                "A": sum(1 for item in collected if item.analysis.grade == "A"),
                "B": sum(1 for item in collected if item.analysis.grade == "B"),
                "C": sum(1 for item in collected if item.analysis.grade == "C"),
            }
            logger.info("Completed screening task for job %s with %s candidates", job_id, len(collected))
        else:
            store.task.status = "failed"
            store.task.updated_at = datetime.now()
            store.task.message = "No candidates were loaded from Boss."
            store.task.candidate_count = 0
            store.task.auto_pass_count = 0
            store.task.grade_counts = {}
            logger.warning("Screening task for job %s finished with no candidates", job_id)

        runtime_state_service.save_task(store.task)
        task_storage.save_task(store.task)
        task_storage.save_candidates(store.task.id, collected)
        self._publish_task_event(job_id)
        return store.task

    @staticmethod
    def _fetch_detail_safe(job_id: str, candidate: CandidateDetail) -> CandidateDetail:
        if not (candidate.card.security_id and candidate.card.lid):
            return candidate
        try:
            logger.info(
                "Calling Boss resume detail for job=%s candidate=%s security_id=%s lid=%s",
                job_id,
                candidate.card.id,
                candidate.card.security_id,
                candidate.card.lid,
            )
            detail = boss_connector.fetch_candidate_detail(
                job_id,
                candidate.card.security_id,
                candidate.card.lid,
            )
            detail = TaskService._merge_candidate_action_fields(candidate, detail)
            time.sleep(random.uniform(0.3, 0.8))
            return detail
        except Exception as exc:
            logger.warning(
                "Failed to fetch Boss detail for candidate %s job %s: %s",
                candidate.card.id,
                job_id,
                exc,
            )
            return candidate

    def _wait_if_paused(self) -> None:
        while store.task.status == "paused":
            store.task.updated_at = datetime.now()
            store.task.message = "Task paused. Waiting for manual resume."
            runtime_state_service.save_task(store.task)
            self._publish_task_event(store.task.job_id)
            time.sleep(1)

    @staticmethod
    def _upsert_candidate(candidates: list[CandidateDetail], candidate: CandidateDetail) -> list[CandidateDetail]:
        next_items = list(candidates)
        for index, item in enumerate(next_items):
            if item.card.id == candidate.card.id:
                next_items[index] = candidate
                return next_items
        next_items.append(candidate)
        return next_items

    @staticmethod
    def _is_publishable_candidate(candidate: CandidateDetail) -> bool:
        company = (candidate.card.current_company or "").strip().lower()
        position = (candidate.card.current_position or "").strip().lower()
        summary = (candidate.analysis.summary or "").strip().lower()
        resume_text = (candidate.original_resume or "").strip()

        if not resume_text:
            return False
        if company in {"", "unknown"}:
            return False
        if position in {"", "unknown"}:
            return False
        if "waiting for profile-based screening" in summary:
            return False
        return True

    @staticmethod
    def _merge_candidate_action_fields(base_candidate: CandidateDetail, detail_candidate: CandidateDetail) -> CandidateDetail:
        for field_name in ("security_id", "lid", "encrypt_geek_id", "encrypt_job_id", "expect_id"):
            if not getattr(detail_candidate.card, field_name):
                setattr(detail_candidate.card, field_name, getattr(base_candidate.card, field_name))
        return detail_candidate

    @staticmethod
    def _apply_auto_actions(job_id: str, candidate: CandidateDetail) -> CandidateDetail:
        actions: list[str] = []
        if candidate.analysis.pass_flag:
            score = candidate.analysis.score
            all_hard_passed = not candidate.analysis.hard_constraint_check or all(
                item.passed for item in candidate.analysis.hard_constraint_check
            )
            # 收藏：硬性全过 score>=75，或硬性未全过但 score>=80
            if not candidate.card.collected:
                if (all_hard_passed and score >= 75) or (not all_hard_passed and score >= 80):
                    actions.append("collect")
            # 打招呼：pass_flag=True AND score>=80
            if score >= 80 and not candidate.card.greeted:
                actions.append("greet")
        if not actions:
            return candidate

        updated = candidate
        for action in dict.fromkeys(actions):
            if action not in {"collect", "greet"}:
                continue
            if action == "collect" and updated.card.collected:
                continue
            if action == "greet" and updated.card.greeted:
                continue
            try:
                updated = candidate_service.mark_action(updated.card.id, action, job_id)
                logger.info(
                    "Applied automatic Boss action %s for candidate=%s job=%s",
                    action,
                    updated.card.id,
                    job_id,
                )
            except Exception as exc:
                logger.warning(
                    "Failed automatic Boss action %s for candidate=%s job=%s: %s",
                    action,
                    updated.card.id,
                    job_id,
                    exc,
                )
        return updated

    def get_stream_events(self, job_id: str, after_seq: int = 0) -> list[dict[str, Any]]:
        events = self._stream_events.get(job_id, [])
        return [event for event in events if int(event.get("seq", 0)) > after_seq]

    def get_stream_snapshot(self, job_id: str) -> dict[str, Any]:
        # Prefer in-memory candidates, but fall back to persisted runtime state after refresh/restart.
        if (
            store.task.job_id == job_id
            and store.candidates
            and all(
                (item.card.encrypt_job_id in {None, "", job_id}) or item.card.source != "boss"
                for item in store.candidates
            )
        ):
            candidates = store.candidates
        else:
            candidates = runtime_state_service.load_candidates(job_id)
            if candidates:
                candidate_service.set_candidates(job_id, candidates)
                if store.task.job_id == job_id:
                    store.candidates = candidates
            elif store.task.job_id == job_id:
                store.candidates = []
        return {
            "type": "snapshot",
            "seq": self._stream_seq,
            "task": store.task.model_dump(mode="json") if store.task.job_id == job_id else None,
            "candidates": [item.model_dump(mode="json") for item in candidates],
        }

    def _next_seq(self) -> int:
        self._stream_seq += 1
        return self._stream_seq

    def _reset_stream(self, job_id: str) -> None:
        self._stream_events[job_id] = []

    def _publish_task_event(self, job_id: str) -> None:
        if not job_id:
            return
        self._stream_events.setdefault(job_id, []).append(
            {
                "type": "task",
                "seq": self._next_seq(),
                "task": store.task.model_dump(mode="json"),
            }
        )

    def _publish_candidate_event(self, job_id: str, candidate: CandidateDetail) -> None:
        if not job_id:
            return
        self._stream_events.setdefault(job_id, []).append(
            {
                "type": "candidate_upsert",
                "seq": self._next_seq(),
                "candidate": candidate.model_dump(mode="json"),
            }
        )


task_service = TaskService()
