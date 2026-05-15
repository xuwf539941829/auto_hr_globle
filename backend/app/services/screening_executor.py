import asyncio
import random
import uuid
from datetime import datetime
from typing import List, Optional
from app.models.domain import ScreeningTask, CandidateDetail
from app.services.task_state_manager import task_state_manager, TaskState, TaskStatus
from app.services.task_storage import task_storage
from app.services.boss_connector import boss_connector
from app.services.candidate_service import candidate_service
from app.services.candidate_screening_service import candidate_screening_service
from app.services.job_service import job_service
from app.core.logging import get_logger

logger = get_logger(__name__)


class ScreeningExecutor:
    """任务执行器 - Boss串行 + LLM串行限流"""

    def __init__(self):
        self._cancelled: set[str] = set()
        self._paused: set[str] = set()
        self._running: set[str] = set()  # 当前正在执行的任务ID（线程安全读写）
        
    async def execute(self, task: ScreeningTask) -> None:
        """执行任务"""
        worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        task_id = task.id
        
        # 注册状态
        initial_state = TaskState(
            status=TaskStatus.QUEUED,
            progress_current=0,
            progress_total=task.config.max_pages * 20 if hasattr(task, 'config') else 200,
            message="等待执行...",
            worker_id=worker_id,
        )
        await task_state_manager.register_state(task_id, initial_state)
        
        self._running.add(task_id)
        try:
            # 开始执行
            await self._update_state(task_id, TaskStatus.RUNNING, "开始筛选...", "init")
            
            # Phase 1: Boss列表获取（串行 + 随机延迟）
            candidates = await self._fetch_list_serial(task_id, task)
            
            # Phase 2: Boss详情获取（串行 + 随机延迟）
            enriched = await self._enrich_serial(task_id, task, candidates)
            
            # Phase 3: LLM筛选（串行限流）
            screened = await self._screen_serial(task_id, task, enriched)
            
            # 完成
            await self._update_state(
                task_id, 
                TaskStatus.COMPLETED,
                f"完成！共筛选 {len(screened)} 人",
                "completed",
                (len(screened), len(screened))
            )
            
        except asyncio.CancelledError:
            await self._update_state(task_id, TaskStatus.CANCELLED, "已取消", "cancelled")
            
        except Exception as exc:
            logger.exception("任务 %s 失败: %s", task_id, exc)
            await self._update_state(task_id, TaskStatus.FAILED, f"失败: {str(exc)}", "failed")
            
        finally:
            self._running.discard(task_id)
            await task_state_manager.cleanup(task_id)
            
    async def _fetch_list_serial(self, task_id: str, task: ScreeningTask) -> List[CandidateDetail]:
        """获取候选人列表（串行 + 随机延迟）"""
        all_candidates = []
        max_pages = getattr(task.config, 'max_pages', 10) if hasattr(task, 'config') else 10
        
        round_num = 1
        no_new_count = 0
        
        while True:
            await self._check_control_signals(task_id)
            
            round_candidates = []
            for page in range(1, max_pages + 1):
                await self._check_control_signals(task_id)
                
                # 串行获取
                try:
                    page_candidates = boss_connector.fetch_recommended_candidates(task.job_id, page=page)
                except Exception as exc:
                    logger.warning("获取第 %s 页失败: %s", page, exc)
                    break
                
                if not page_candidates:
                    break
                    
                round_candidates.extend(page_candidates)
                
                await self._update_state(
                    task_id,
                    TaskStatus.RUNNING,
                    f"第{round_num}轮 - 第 {page} 页: {len(page_candidates)} 人",
                    "fetching",
                    (len(all_candidates) + len(round_candidates), max_pages * 20)
                )
                
                # 随机延迟 0.5-1.5秒
                delay = random.uniform(0.5, 1.5)
                await asyncio.sleep(delay)
            
            # 去重：同时按 card.id 和 security_id 过滤，避免同一人多次投递
            new_candidates = []
            existing_ids = {c.card.id for c in all_candidates}
            existing_sids = {c.card.security_id for c in all_candidates if c.card.security_id}
            for c in round_candidates:
                sid = c.card.security_id
                if c.card.id not in existing_ids and (not sid or sid not in existing_sids):
                    existing_ids.add(c.card.id)
                    if sid:
                        existing_sids.add(sid)
                    new_candidates.append(c)
            
            if not new_candidates:
                no_new_count += 1
                if no_new_count >= 3:
                    logger.info("连续 %s 轮无新候选人，停止", no_new_count)
                    break
            else:
                no_new_count = 0
                all_candidates.extend(new_candidates)
                
            await self._update_state(
                task_id,
                TaskStatus.RUNNING,
                f"第{round_num}轮完成，新增 {len(new_candidates)} 人，总计 {len(all_candidates)} 人",
                "fetching",
                (len(all_candidates), len(all_candidates) + 50)
            )
            
            round_num += 1
            
            # 随机停顿 2-4秒，模拟人工操作
            await asyncio.sleep(random.uniform(2, 4))
        
        return all_candidates
    
    async def _enrich_serial(self, task_id: str, task: ScreeningTask, candidates: List[CandidateDetail]) -> List[CandidateDetail]:
        """获取详情（2路并发，随机延迟防封）"""
        total = len(candidates)
        enriched = [None] * total
        sem = asyncio.Semaphore(1)
        completed = 0

        async def enrich_one(i: int, candidate: CandidateDetail) -> None:
            nonlocal completed
            async with sem:
                await self._check_control_signals(task_id)
                detail = await self._get_detail_safe(task.job_id, candidate)
                enriched[i] = detail
                completed += 1
                await self._update_state(
                    task_id,
                    TaskStatus.RUNNING,
                    f"获取详情 {completed}/{total}: {candidate.card.name}",
                    "enriching",
                    (completed, total),
                )
                await asyncio.sleep(random.uniform(0.2, 0.5))

        await asyncio.gather(*[enrich_one(i, c) for i, c in enumerate(candidates)])
        return [e for e in enriched if e is not None]
    
    async def _get_detail_safe(self, job_id: str, candidate: CandidateDetail) -> CandidateDetail:
        """安全获取详情（带重试）"""
        if not candidate.card.security_id or not candidate.card.lid:
            return candidate
            
        for attempt in range(3):
            try:
                return boss_connector.fetch_candidate_detail(
                    job_id,
                    candidate.card.security_id,
                    candidate.card.lid
                )
            except Exception as exc:
                if attempt < 2:
                    # 随机重试间隔 1-3秒
                    await asyncio.sleep(random.uniform(1, 3))
                else:
                    logger.error("获取 %s 详情最终失败: %s", candidate.card.id, exc)
                    
        return candidate
    
    async def _screen_serial(self, task_id: str, task: ScreeningTask, candidates: List[CandidateDetail]) -> List[CandidateDetail]:
        """LLM筛选（2路并发限流）- 兼顾速度与GLM速率限制"""
        profile = job_service.get_current_profile(task.job_id)
        await self._update_state(task_id, TaskStatus.RUNNING, "LLM 筛选中...", "screening")

        loop = asyncio.get_event_loop()
        sem = asyncio.Semaphore(1)
        total = len(candidates)
        results = [None] * total
        completed = 0

        async def screen_one(i: int, candidate: CandidateDetail) -> None:
            nonlocal completed
            async with sem:
                await self._check_control_signals(task_id)
                try:
                    candidate.analysis = await loop.run_in_executor(
                        None, candidate_screening_service.analyze, profile, candidate
                    )
                    candidate.card.score = candidate.analysis.score
                    candidate.card.grade = candidate.analysis.grade
                    candidate.card.summary = candidate.analysis.summary
                    candidate.card.risk_tags = list(
                        dict.fromkeys([*candidate.analysis.risk_items[:2], *candidate.analysis.timeline_risks[:1]])
                    )
                    candidate = self._apply_auto_actions(task.job_id, candidate)
                except Exception as exc:
                    logger.exception("筛选 %s 失败: %s", candidate.card.id, exc)
                    candidate.card.score = 0
                    candidate.card.grade = "C"

                results[i] = candidate
                completed += 1
                grade = candidate.analysis.grade if candidate.analysis else "C"
                await self._update_state(
                    task_id,
                    TaskStatus.RUNNING,
                    f"筛选 {completed}/{total}: {candidate.card.name} - {grade}级",
                    "screening",
                    (completed, total),
                )
                # 限流间隔（最后一批不等待）
                if completed < total:
                    await asyncio.sleep(1)

        await asyncio.gather(*[screen_one(i, c) for i, c in enumerate(candidates)])

        final = [r for r in results if r is not None]
        task.candidate_count = len(final)
        task.grade_counts = self._calculate_grade_counts(final)
        task.auto_pass_count = sum(1 for c in final if c.analysis and c.analysis.pass_flag)
        task_storage.save_candidates(task_id, final)
        # Sync screened results into candidate_service so the candidates page
        # and greet/collect actions can find them by job_id.
        candidate_service.set_candidates(task.job_id, final)
        return final
    
    async def _update_state(self, task_id: str, status: TaskStatus, message: str, phase: str, progress: Optional[tuple[int, int]] = None) -> None:
        """更新状态"""
        if progress:
            await task_state_manager.update_state(task_id, status, message, phase, progress)
        else:
            await task_state_manager.update_state(task_id, status, message, phase)
        await task_state_manager.heartbeat(task_id, "worker")
        
    async def _check_control_signals(self, task_id: str) -> None:
        """检查控制信号"""
        if task_id in self._cancelled:
            raise asyncio.CancelledError()
            
        while task_id in self._paused:
            await self._update_state(task_id, TaskStatus.PAUSED, "已暂停", "paused")
            await asyncio.sleep(1)
            if task_id in self._cancelled:
                raise asyncio.CancelledError()
                
    def pause(self, task_id: str) -> None:
        self._paused.add(task_id)

    def resume(self, task_id: str) -> None:
        self._paused.discard(task_id)

    def cancel(self, task_id: str) -> None:
        self._cancelled.add(task_id)

    def pause_all(self) -> list[str]:
        """暂停所有正在运行的任务，返回被暂停的任务ID列表"""
        task_ids = list(self._running - self._paused)
        for task_id in task_ids:
            self._paused.add(task_id)
        return task_ids

    def resume_all(self) -> list[str]:
        """恢复所有已暂停的任务，返回被恢复的任务ID列表"""
        task_ids = list(self._paused)
        self._paused.clear()
        return task_ids
        
    def _calculate_grade_counts(self, candidates: List[CandidateDetail]) -> dict[str, int]:
        counts = {"S": 0, "A": 0, "B": 0, "C": 0}
        for c in candidates:
            if c.analysis.grade in counts:
                counts[c.analysis.grade] += 1
        return counts

    @staticmethod
    def _apply_auto_actions(job_id: str, candidate: CandidateDetail) -> CandidateDetail:
        analysis = candidate.analysis
        if not analysis:
            return candidate
        score = analysis.score
        all_hard_passed = all(item.passed for item in (analysis.hard_constraint_check or []))

        actions: list[str] = []
        if analysis.pass_flag:
            # 收藏：硬性全过 score>=75，或硬性未全过但 score>=80（高分值得人工复核）
            if not candidate.card.collected:
                if (all_hard_passed and score >= 75) or (not all_hard_passed and score >= 80):
                    actions.append("collect")
            # 打招呼：pass_flag=True AND score>=80（不额外要求硬性全过）
            if score >= 80 and not candidate.card.greeted:
                actions.append("greet")
        if not actions:
            return candidate

        updated = candidate
        for action in actions:
            if action == "collect" and updated.card.collected:
                continue
            if action == "greet" and updated.card.greeted:
                continue
            try:
                updated = candidate_service.apply_action_to_detail(updated, action, job_id)
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


# 全局实例
screening_executor = ScreeningExecutor()
