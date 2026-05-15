from __future__ import annotations

import json
import re
import time
from typing import Any

import requests as http_requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.core.logging import get_logger
from app.models.domain import (
    CandidateAnalysis,
    CandidateCard,
    CandidateConstraintCheck,
    CandidateDetail,
    CandidateDimensionCheck,
    CandidateEvidence,
    JobProfile,
    MetricCard,
    ParsedResume,
    ResumeEducationEntry,
    ResumeWorkEntry,
    ScreeningBlueprint,
)
from app.services.jd_translator import LLMConfig, LLMTranslationError
from app.services.llm_logging import log_llm_error, log_llm_request, log_llm_response, new_trace_id
from app.services.llm_trace_service import llm_trace_service

logger = get_logger(__name__)


class CandidateScreeningService:
    ACTION_TERMS = [
        "安装",
        "调试",
        "维护",
        "维修",
        "排障",
        "巡检",
        "保养",
        "培训",
        "交付",
        "实施",
        "接线",
        "配电",
        "联调",
        "恢复生产",
        "售后",
        "support",
        "install",
        "commission",
        "maintain",
        "repair",
        "troubleshoot",
        "train",
        "deliver",
        "implement",
    ]
    FIELD_TERMS = [
        "现场",
        "工厂",
        "矿山",
        "驻外",
        "出差",
        "长期在外",
        "现场服务",
        "onsite",
        "field",
        "factory",
        "mine",
        "travel",
    ]
    EDUCATION_TERMS = [
        "大学",
        "学院",
        "学校",
        "本科",
        "大专",
        "中专",
        "硕士",
        "博士",
        "college",
        "university",
        "bachelor",
        "master",
        "phd",
    ]
    RETAIL_TERMS = ["零售", "门店", "retail", "store"]
    SUPPORT_TERMS = ["内勤", "跟单", "协助", "support", "assistant", "follow-up"]

    def build_screening_blueprint(self, profile: JobProfile) -> ScreeningBlueprint:
        return ScreeningBlueprint(
            profile_version_id=profile.version_id,
            hard_filters=list(profile.hard_constraints.items),
            scoring_dimensions=[item.model_copy(deep=True) for item in profile.competencies],
            industry_targets=list(profile.industry_expansion.items),
            exclude_rules=list(profile.exclude_rules.items),
            private_notes=list(profile.private_notes),
            age_min=profile.age_min,
            age_max=profile.age_max,
        )

    def parse_resume(self, candidate: CandidateDetail) -> ParsedResume:
        timeline = [item.strip() for item in candidate.timeline if item and item.strip()]
        resume_text = "\n".join([candidate.original_resume, *timeline]).strip()
        return ParsedResume(
            work_experiences=self._parse_work_experiences(timeline),
            education_experiences=self._parse_education_experiences(timeline),
            action_terms=self._extract_action_terms(resume_text),
            numeric_evidence=self._extract_numeric_evidence(resume_text),
            timeline_summary=timeline,
            risk_signals=self._extract_risk_signals(resume_text, timeline),
        )

    def analyze(
        self,
        profile: JobProfile,
        candidate: CandidateDetail,
        parsed_resume: ParsedResume | None = None,
        blueprint: ScreeningBlueprint | None = None,
    ) -> CandidateAnalysis:
        parsed_resume = parsed_resume or self.parse_resume(candidate)
        blueprint = blueprint or self.build_screening_blueprint(profile)
        config = LLMConfig.from_env()

        candidate.parsed_resume = parsed_resume
        candidate.screening_blueprint = blueprint

        if config.enabled:
            try:
                logger.info("Running LLM screening for candidate=%s profile=%s", candidate.card.id, profile.version_id)
                result = self._analyze_with_llm(candidate, parsed_resume, blueprint, config)
                result = self._apply_hard_age_gate(result, blueprint, candidate.card)
                result = self._apply_hard_constraint_grade_cap(result)
                return self._apply_pass_flag_sanity_check(result)
            except LLMTranslationError as exc:
                logger.warning("LLM screening failed for candidate=%s: %s. Falling back to rules.", candidate.card.id, exc)

        return self._apply_hard_constraint_grade_cap(
            self._analyze_with_rules(candidate, parsed_resume, blueprint)
        )

    def _analyze_with_llm(
        self,
        candidate: CandidateDetail,
        parsed_resume: ParsedResume,
        blueprint: ScreeningBlueprint,
        config: LLMConfig,
    ) -> CandidateAnalysis:
        trace_id = new_trace_id("screen")
        llm_trace_service.record_metadata(
            trace_id,
            kind="candidate_screening",
            candidate_id=candidate.card.id,
            profile_version_id=blueprint.profile_version_id,
        )

        endpoint = f"{config.base_url}/responses" if config.api_style == "responses" else f"{config.base_url}/chat/completions"
        prompt = self._build_prompt(candidate, parsed_resume, blueprint)

        if config.api_style == "responses":
            body = {
                "model": config.model,
                "input": [
                    {"role": "system", "content": [{"type": "input_text", "text": "你是简历证据审计引擎。只返回 JSON。"}]},
                    {"role": "user", "content": [{"type": "input_text", "text": prompt}]},
                ],
            }
        else:
            body = {
                "model": config.model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": "你是简历证据审计引擎。只返回 JSON。"},
                    {"role": "user", "content": prompt},
                ],
            }

        log_llm_request(trace_id, endpoint, body)
        raw = self._http_post(trace_id, endpoint, body, config.api_key, config.timeout_seconds)
        log_llm_response(trace_id, raw)

        try:
            payload = self._extract_json(raw, config.api_style)
        except LLMTranslationError as exc:
            llm_trace_service.record_error(trace_id, f"json_parse_failed: {exc}")
            raise

        # If model returned no dimension_checks but blueprint has dimensions, retry once
        has_dims = isinstance(payload.get("dimension_checks"), list) and len(payload["dimension_checks"]) > 0
        if not has_dims and blueprint.scoring_dimensions:
            logger.warning(
                "LLM response missing dimension_checks, retrying with focused prompt: candidate=%s trace=%s",
                candidate.card.id, trace_id,
            )
            retry_payload = self._retry_missing_arrays(candidate, parsed_resume, blueprint, payload, endpoint, config)
            if retry_payload:
                if isinstance(retry_payload.get("dimension_checks"), list) and retry_payload["dimension_checks"]:
                    payload["dimension_checks"] = retry_payload["dimension_checks"]
                if isinstance(retry_payload.get("hard_constraint_check"), list) and retry_payload["hard_constraint_check"]:
                    payload["hard_constraint_check"] = retry_payload["hard_constraint_check"]

        return self._normalize_analysis(payload, candidate, trace_id)

    def _retry_missing_arrays(
        self,
        candidate: CandidateDetail,
        parsed_resume: ParsedResume,
        blueprint: ScreeningBlueprint,
        first_payload: dict[str, Any],
        endpoint: str,
        config: LLMConfig,
    ) -> dict[str, Any] | None:
        """One-shot retry to fill in missing dimension_checks / hard_constraint_check."""
        dim_keys = [
            {"key": d.key, "label": d.label, "weight": d.weight}
            for d in blueprint.scoring_dimensions
        ]
        retry_prompt = {
            "task": "上一次审计输出缺少 dimension_checks 和 hard_constraint_check。请根据以下信息补全这两个数组。",
            "existing_summary": first_payload.get("reasoning_summary") or first_payload.get("summary", ""),
            "existing_score": first_payload.get("score", 0),
            "hard_filters": blueprint.hard_filters,
            "scoring_dimensions": dim_keys,
            "candidate_summary": self._build_resume_audit_text(candidate, parsed_resume)[:800],
            "json_schema": {
                "dimension_checks": [{"key": "string", "label": "string", "weight": 0, "score": 0, "reason": "string"}],
                "hard_constraint_check": [{"item": "string", "passed": True, "reason": "string"}],
            },
        }
        retry_trace_id = new_trace_id("screen")
        llm_trace_service.record_metadata(
            retry_trace_id,
            kind="candidate_screening_retry",
            candidate_id=candidate.card.id,
            profile_version_id=blueprint.profile_version_id,
        )
        if config.api_style == "responses":
            body = {
                "model": config.model,
                "input": [
                    {"role": "system", "content": [{"type": "input_text", "text": "你是简历证据审计引擎。只返回 JSON。"}]},
                    {"role": "user", "content": [{"type": "input_text", "text": json.dumps(retry_prompt, ensure_ascii=False)}]},
                ],
            }
        else:
            body = {
                "model": config.model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": "你是简历证据审计引擎。只返回 JSON。"},
                    {"role": "user", "content": json.dumps(retry_prompt, ensure_ascii=False)},
                ],
            }
        try:
            log_llm_request(retry_trace_id, endpoint, body)
            raw = self._http_post(retry_trace_id, endpoint, body, config.api_key, config.timeout_seconds)
            log_llm_response(retry_trace_id, raw)
            return self._extract_json(raw, config.api_style)
        except Exception as exc:
            logger.warning("Retry for missing arrays also failed: %s candidate=%s", exc, candidate.card.id)
            return None

    def _analyze_with_rules(
        self,
        candidate: CandidateDetail,
        parsed_resume: ParsedResume,
        blueprint: ScreeningBlueprint,
    ) -> CandidateAnalysis:
        checks = self._build_constraint_checks(blueprint, candidate.card, parsed_resume, candidate.original_resume)
        dimension_checks = self._build_dimension_checks(blueprint, parsed_resume, candidate.original_resume)
        evidence_items = self._build_evidence_items(parsed_resume)
        risk_items = self._build_risk_items(blueprint, parsed_resume, candidate.original_resume)
        value_signals = self._build_value_signals(parsed_resume, candidate.original_resume)
        uncertainties = self._build_uncertainties(parsed_resume, dimension_checks)
        interview_focus = self._build_interview_focus(blueprint, risk_items, uncertainties)

        hard_pass_count = sum(1 for item in checks if item.passed)
        hard_score = round(20 * hard_pass_count / max(1, len(checks)))
        dimension_score = round(self._weighted_dimension_score(dimension_checks) * 0.5)
        evidence_score = min(15, len(parsed_resume.action_terms) * 2 + min(5, len(parsed_resume.numeric_evidence) * 2))
        field_score = self._field_fit_score(parsed_resume, blueprint, candidate.original_resume)
        stability_score = self._stability_score(parsed_resume)
        total_score = max(0, min(100, hard_score + dimension_score + evidence_score + field_score + stability_score))

        grade = self._score_to_grade(total_score)
        pass_flag = total_score >= 75 and all(item.passed for item in checks)

        summary = (
            "证据相对完整，能看到较明确的岗位匹配信号。"
            if pass_flag
            else "当前证据不足或关键要求不匹配，建议谨慎推进。"
        )

        return CandidateAnalysis(
            score=total_score,
            grade=grade,
            pass_flag=pass_flag,
            summary=summary,
            reasoning_summary="系统先判断硬门槛，再按核心维度、动作证据、数字证据和场景适配度综合给分。",
            llm_trace_id=None,
            hard_constraint_check=checks,
            dimension_checks=dimension_checks,
            score_breakdown=[
                MetricCard(label="硬性门槛", value=f"{hard_score}/20"),
                MetricCard(label="核心维度", value=f"{dimension_score}/50"),
                MetricCard(label="动作与数字证据", value=f"{evidence_score}/15"),
                MetricCard(label="场景适配", value=f"{field_score}/10"),
                MetricCard(label="稳定性", value=f"{stability_score}/5"),
            ],
            evidence_items=evidence_items,
            timeline_risks=list(parsed_resume.risk_signals),
            risk_items=risk_items,
            value_signals=value_signals,
            uncertainties=uncertainties,
            interview_focus=interview_focus,
            recommended_actions=["collect", "greet"] if pass_flag else (["collect"] if total_score >= 65 else []),
        )

    def _build_prompt(self, candidate: CandidateDetail, parsed_resume: ParsedResume, blueprint: ScreeningBlueprint) -> str:
        payload = {
            "task": "请根据最终执行画像对这份简历做证据审计。不要按固定销售模板评分，要按当前动态维度逐项判断。",
            "rules": [
                "⚠️ 必须输出完整 JSON：dimension_checks 数组必须包含 scoring_dimensions 中每一个 key 的记录；hard_constraint_check 数组必须包含 hard_filters 中每一条规则的记录。缺少这两个数组将导致本次审计结果无效。",
                "先看硬性门槛，再看动态能力维度。",
                "不要把没有用的工程字段当证据，只根据简历原文、时间线和结构化信号判断。",
                "不找词，只找事。优先判断候选人是否真的做过安装、调试、维护、排障、培训、现场支持等动作。",
                "每个维度都要输出 score 和 reason。",
                "如果没有足够证据，不要脑补，放进 uncertainties。",
                "工作年限字段来自Boss系统，表示候选人自称的总工作年限，不代表特定专业经验年限。判断'X年以上某类经验'的硬性门槛时，只采信简历中有具体时间线和职责描述的工作段，未记录的工作经历不得推断认定。",
                "grade必须与score严格对应：score>=90→S，score>=80→A，score>=65→B，score<65→C。",
                "行业背景必须与 industry_targets 匹配才能得高分。如果候选人的核心经验来自半导体、IT、软件、消费电子等行业，而 industry_targets 是工程机械、矿山设备、重型设备等，则即使候选人做过「调试」「安装」等动作，相关维度也须明显扣分——动作词相同不代表行业经验可以直接迁移。",
                "输出 JSON 对象。",
            ],
            "screening_blueprint": self._build_compact_blueprint(blueprint),
            "candidate_resume": self._build_resume_audit_text(candidate, parsed_resume),
            "json_schema": {
                "score": 0,
                "grade": "S|A|B|C",
                "pass_flag": True,
                "summary": "string",
                "reasoning_summary": "string",
                "hard_constraint_check": [{"item": "string", "passed": True, "reason": "string"}],
                "dimension_checks": [{"key": "string", "label": "string", "weight": 0, "score": 0, "reason": "string"}],
                "score_breakdown": [{"label": "string", "value": "string"}],
                "evidence_items": [{"type": "action", "title": "string", "content": "string", "impact": "string", "confidence": 0.0}],
                "timeline_risks": ["string"],
                "risk_items": ["string"],
                "value_signals": ["string"],
                "uncertainties": ["string"],
                "interview_focus": ["string"],
                "recommended_actions": ["collect"],
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _build_compact_blueprint(self, blueprint: ScreeningBlueprint) -> dict[str, Any]:
        result: dict[str, Any] = {
            "profile_version_id": blueprint.profile_version_id,
            "hard_filters": self._unique_strings(self._string_list(blueprint.hard_filters)),
            "scoring_dimensions": [
                {
                    "key": item.key,
                    "label": item.label,
                    "weight": item.weight,
                    "focus": self._compact_focus(item.note),
                }
                for item in blueprint.scoring_dimensions
            ],
            "industry_targets": self._unique_strings(self._string_list(blueprint.industry_targets)),
            "exclude_rules": self._unique_strings(self._string_list(blueprint.exclude_rules)),
            "private_notes": self._unique_strings(self._string_list(blueprint.private_notes))[:4],
        }
        if blueprint.age_min or blueprint.age_max:
            if blueprint.age_min and blueprint.age_max:
                result["age_requirement"] = f"{blueprint.age_min}-{blueprint.age_max}岁（硬性门槛，不符合直接不通过）"
            elif blueprint.age_max:
                result["age_requirement"] = f"{blueprint.age_max}岁以下（硬性门槛，不符合直接不通过）"
            else:
                result["age_requirement"] = f"{blueprint.age_min}岁以上（硬性门槛，不符合直接不通过）"
        return result

    def _build_resume_audit_text(self, candidate: CandidateDetail, parsed_resume: ParsedResume) -> str:
        lines = [
            f"候选人：{candidate.card.name or '未知'}",
            f"年龄：{candidate.card.age}岁" if candidate.card.age else "年龄：未知",
            f"学历：{candidate.card.education or '未知'}",
            f"工作年限：{candidate.card.work_years:.1f}年",
        ]
        if candidate.card.current_company or candidate.card.current_position:
            lines.append(
                f"当前岗位：{candidate.card.current_company or '未知公司'} | {candidate.card.current_position or '未知岗位'}"
            )

        lines.append("")
        lines.append("一、工作经历时间线")
        if parsed_resume.work_experiences:
            for item in parsed_resume.work_experiences:
                summary = f"：{item.summary}" if item.summary else ""
                lines.append(f"- {item.start}-{item.end or '至今'} {item.company} | {item.position}{summary}")
        else:
            lines.append("- 暂无清晰工作经历")

        lines.append("")
        lines.append("二、教育经历")
        if parsed_resume.education_experiences:
            for item in parsed_resume.education_experiences:
                degree = self._sanitize_education_degree(item.degree)
                lines.append(f"- {item.start}-{item.end or ''} {item.school} | {degree}".strip())
        else:
            lines.append("- 暂无明确教育信息")

        lines.append("")
        lines.append("三、结构化信号")
        lines.append(f"- 动作词：{'、'.join(parsed_resume.action_terms) if parsed_resume.action_terms else '暂无'}")
        lines.append(f"- 数字证据：{'、'.join(parsed_resume.numeric_evidence) if parsed_resume.numeric_evidence else '暂无'}")
        lines.append(f"- 风险信号：{'、'.join(parsed_resume.risk_signals) if parsed_resume.risk_signals else '暂无'}")

        lines.append("")
        lines.append("四、简历原文")
        lines.append(self._clean_resume_text(candidate.original_resume))
        return "\n".join(lines)

    def _normalize_analysis(self, payload: dict[str, Any], candidate: CandidateDetail, trace_id: str) -> CandidateAnalysis:
        raw_grade = str(payload.get("grade", "C")).upper().strip()
        grade = raw_grade if raw_grade in {"S", "A", "B", "C"} else "C"

        # Parse LLM's stated score as reference only
        raw_score = payload.get("score", 0)
        try:
            _s = float(raw_score)
            if 0 < _s <= 1:  # LLM 偶尔返回 0-1 小数
                _s *= 100
            llm_score = max(0, min(100, round(_s)))
        except (TypeError, ValueError):
            llm_score = 0

        # Parse dimension_checks first — used as primary score source
        raw_dims = self._string_or_list_of_dict(payload.get("dimension_checks"))
        dimension_checks_parsed = [
            CandidateDimensionCheck(
                key=str(item.get("key", "")),
                label=str(item.get("label", "")),
                weight=max(0, min(100, int(item.get("weight", 0) or 0))),
                score=max(0, min(100, int(item.get("score", 0) or 0))),
                reason=str(item.get("reason", "")),
            )
            for item in raw_dims
        ]

        # Always compute score from dimension_checks for consistency.
        # LLM's holistic score is unreliable — dimension scores are explicit and auditable.
        score = 0
        if dimension_checks_parsed:
            total_weight = sum(max(dc.weight, 1) for dc in dimension_checks_parsed)
            if total_weight > 0:
                weighted = sum(dc.score * max(dc.weight, 1) for dc in dimension_checks_parsed)
                score = max(0, min(100, round(weighted / total_weight)))
                if score != llm_score:
                    logger.info(
                        "Score recomputed from dimension_checks: llm=%s → computed=%s candidate=%s",
                        llm_score, score, candidate.card.id,
                    )

        # Fall back to LLM score only when no dimension data is available
        if score == 0 and llm_score > 0:
            score = llm_score
            logger.info("Using LLM score (no dimension_checks): score=%s candidate=%s", score, candidate.card.id)

        # Enforce grade/score consistency
        correct_grade = self._score_to_grade(score)
        if grade != correct_grade:
            logger.info(
                "Grade corrected: llm=%s → %s (score=%s) candidate=%s",
                grade, correct_grade, score, candidate.card.id,
            )
            grade = correct_grade

        # Build score_breakdown from actual dimension scores (replaces LLM's self-reported breakdown)
        if dimension_checks_parsed:
            score_breakdown = [
                MetricCard(label=dc.label, value=f"{dc.score} (权重{dc.weight})")
                for dc in dimension_checks_parsed
            ]
        else:
            score_breakdown = [
                MetricCard(label=str(item.get("label", "")), value=str(item.get("value", "")))
                for item in self._string_or_list_of_dict(payload.get("score_breakdown"))
            ]

        return CandidateAnalysis(
            score=score,
            grade=grade,
            pass_flag=bool(payload.get("pass_flag", False)),
            summary=str(payload.get("summary", "")),
            reasoning_summary=str(payload.get("reasoning_summary", "")),
            llm_trace_id=trace_id,
            hard_constraint_check=[
                CandidateConstraintCheck(
                    item=str(item.get("item", "")),
                    passed=bool(item.get("passed", False)),
                    reason=str(item.get("reason", "")),
                )
                for item in self._string_or_list_of_dict(payload.get("hard_constraint_check"))
            ],
            dimension_checks=dimension_checks_parsed,
            score_breakdown=score_breakdown,
            evidence_items=[
                CandidateEvidence(
                    type=self._normalize_evidence_type(str(item.get("type", "action"))),
                    title=str(item.get("title", "")),
                    content=str(item.get("content", "")),
                    impact=str(item.get("impact", "")),
                    confidence=max(0.0, min(1.0, float(item.get("confidence", 0.0) or 0.0))),
                )
                for item in self._string_or_list_of_dict(payload.get("evidence_items"))
            ],
            timeline_risks=self._string_list(payload.get("timeline_risks")),
            risk_items=self._string_list(payload.get("risk_items")),
            value_signals=self._string_list(payload.get("value_signals")),
            uncertainties=self._string_list(payload.get("uncertainties")),
            interview_focus=self._string_list(payload.get("interview_focus")),
            recommended_actions=self._string_list(payload.get("recommended_actions")),
        )

    @staticmethod
    def _make_session() -> http_requests.Session:
        session = http_requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
        session.mount("https://", HTTPAdapter(max_retries=retry))
        session.mount("http://", HTTPAdapter(max_retries=retry))
        return session

    def _http_post(self, trace_id: str, endpoint: str, body: dict, api_key: str, timeout: int) -> str:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Connection": "close",
        }
        last_conn_exc: Exception | None = None
        for attempt in range(2):
            try:
                session = http_requests.Session()
                session.mount("https://", HTTPAdapter(max_retries=Retry(total=0)))
                session.mount("http://", HTTPAdapter(max_retries=Retry(total=0)))
                resp = session.post(endpoint, json=body, headers=headers, timeout=timeout, verify=False)
                resp.raise_for_status()
                return resp.text
            except http_requests.exceptions.Timeout as exc:
                # 超时不重试：DeepSeek 无响应时再试一次也没用，直接回落规则
                log_llm_error(trace_id, f"Timeout: {exc}")
                raise LLMTranslationError("LLM 请求超时") from exc
            except http_requests.exceptions.ConnectionError as exc:
                last_conn_exc = exc
                wait = 2 ** attempt  # 1s → 2s
                logger.warning("LLM connection error (attempt %s/2), retry in %ss: %s", attempt + 1, wait, exc)
                if attempt < 1:
                    time.sleep(wait)
            except http_requests.exceptions.HTTPError as exc:
                detail = exc.response.text if exc.response is not None else str(exc)
                log_llm_error(trace_id, f"HTTP {exc.response.status_code if exc.response is not None else '?'}: {detail}")
                raise LLMTranslationError(f"LLM 请求失败: {detail}") from exc
            except http_requests.exceptions.RequestException as exc:
                log_llm_error(trace_id, f"Request error: {exc}")
                raise LLMTranslationError(f"LLM 请求异常: {exc}") from exc
        log_llm_error(trace_id, f"Connection error after 2 attempts: {last_conn_exc}")
        raise LLMTranslationError(f"LLM 连接异常（已重试2次）: {last_conn_exc}") from last_conn_exc

    def _extract_json(self, raw: str, api_style: str) -> dict[str, Any]:
        if not raw.strip():
            raise LLMTranslationError("LLM returned empty response for candidate screening.")

        payload = json.loads(raw)
        text = self._extract_response_text(payload) if api_style == "responses" else payload["choices"][0]["message"]["content"]
        if not isinstance(text, str) or not text.strip():
            raise LLMTranslationError("LLM returned empty content for candidate screening.")

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.S)
            if match:
                return json.loads(match.group(0))
            raise LLMTranslationError("LLM response is not valid JSON.")

    def _extract_response_text(self, payload: dict[str, Any]) -> str:
        output = payload.get("output", [])
        if not isinstance(output, list):
            raise LLMTranslationError("Unexpected responses payload.")
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") in {"output_text", "text"}:
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
        return "\n".join(parts)

    @staticmethod
    def _apply_hard_age_gate(
        analysis: CandidateAnalysis,
        blueprint: ScreeningBlueprint,
        card: CandidateCard,
    ) -> CandidateAnalysis:
        """Override pass_flag to False when candidate age violates a hard age requirement."""
        age_min, age_max = blueprint.age_min, blueprint.age_max
        if not (age_min or age_max):
            return analysis
        candidate_age = card.age if card.age and card.age > 0 else None
        if candidate_age is None:
            return analysis
        age_ok = (not age_min or candidate_age >= age_min) and (not age_max or candidate_age <= age_max)
        if not age_ok and analysis.pass_flag:
            logger.info(
                "Age gate override: candidate=%s age=%s requirement=[%s, %s] — forcing pass_flag=False",
                card.id, candidate_age, age_min, age_max,
            )
            return analysis.model_copy(update={"pass_flag": False})
        return analysis

    @staticmethod
    def _apply_hard_constraint_grade_cap(analysis: CandidateAnalysis) -> CandidateAnalysis:
        """硬性条件未全部满足时，评级最高封顶为 B。"""
        if not analysis.hard_constraint_check:
            return analysis
        all_passed = all(item.passed for item in analysis.hard_constraint_check)
        if not all_passed and analysis.grade in ("S", "A"):
            logger.info("Hard constraint grade cap: %s → B", analysis.grade)
            return analysis.model_copy(update={"grade": "B"})
        return analysis

    @staticmethod
    def _apply_pass_flag_sanity_check(analysis: CandidateAnalysis) -> CandidateAnalysis:
        """
        LLM 可能错误地将 pass_flag 设为 True。允许 True 的合法条件：
          - score >= 75 且硬性全过（标准通过）
          - score >= 80（高分候选人，即使硬性未全过也值得收藏/跟进）
        其余情况强制置 False。
        """
        if not analysis.pass_flag:
            return analysis
        score = analysis.score
        all_hard_passed = not analysis.hard_constraint_check or all(
            item.passed for item in analysis.hard_constraint_check
        )
        if (all_hard_passed and score >= 75) or score >= 80:
            return analysis
        logger.info(
            "pass_flag sanity override: LLM said True but score=%s all_hard=%s — forcing False",
            score,
            all_hard_passed,
        )
        return analysis.model_copy(update={"pass_flag": False})

    def _build_constraint_checks(
        self,
        blueprint: ScreeningBlueprint,
        card: CandidateCard,
        parsed_resume: ParsedResume,
        original_resume: str,
    ) -> list[CandidateConstraintCheck]:
        text = self._combined_text(card, parsed_resume, original_resume)
        checks: list[CandidateConstraintCheck] = []
        for item in self._string_list(blueprint.hard_filters):
            normalized = item.replace(" ", "")
            if any(keyword in normalized for keyword in ["图纸", "读图"]):
                passed = any(term in text for term in ["图纸", "电气图", "布线"])
                reason = "简历里能看到图纸或布线相关表述。" if passed else "没有明确看到图纸理解能力。"
            elif any(keyword in normalized for keyword in ["出差", "驻外"]):
                passed = any(term in text for term in ["出差", "驻外", "现场", "工厂", "矿山", "travel"])
                reason = "简历里存在出差或现场场景信号。" if passed else "没有明确看到出差或长期现场信号。"
            elif "现场技术操作" in normalized or "独立完成现场技术操作" in normalized:
                passed = any(term in text for term in ["安装", "调试", "现场", "维修", "维护", "排障"])
                reason = "简历里能看到安装、调试、维护或排障动作。" if passed else "没有明确看到独立现场操作证据。"
            elif "机械设备相关基础知识" in normalized:
                passed = any(term in text for term in ["机械", "设备", "电气", "液压", "机电", "装配"])
                reason = "简历里有机械设备相关背景。" if passed else "没有明确看到机械设备相关背景。"
            elif any(edu in normalized for edu in ["博士", "硕士", "本科", "大专", "中专", "高中"]):
                passed, reason = self._check_education_constraint(normalized, card.education, text)
            elif "年龄要求" in normalized:
                continue  # 年龄由下方 age gate 统一评估，避免重复
            elif re.search(r"\d+年以上", normalized):
                passed, reason = self._check_experience_constraint(normalized, card.work_years)
            else:
                passed = normalized.lower() in text
                reason = "简历里存在对应证据。" if passed else "简历里没有看到对应证据。"
            checks.append(CandidateConstraintCheck(item=item, passed=passed, reason=reason))

        # Age hard constraint
        age_min, age_max = blueprint.age_min, blueprint.age_max
        if age_min or age_max:
            if age_min and age_max:
                label = f"年龄要求：{age_min}-{age_max}岁"
            elif age_max:
                label = f"年龄要求：{age_max}岁以下"
            else:
                label = f"年龄要求：{age_min}岁以上"

            candidate_age = card.age if card.age and card.age > 0 else None
            if candidate_age is None:
                checks.append(CandidateConstraintCheck(
                    item=label, passed=False,
                    reason="简历未提供年龄信息，无法验证是否满足年龄要求。",
                ))
            elif age_min and candidate_age < age_min:
                checks.append(CandidateConstraintCheck(
                    item=label, passed=False,
                    reason=f"候选人年龄 {candidate_age} 岁，低于要求的最小年龄 {age_min} 岁。",
                ))
            elif age_max and candidate_age > age_max:
                checks.append(CandidateConstraintCheck(
                    item=label, passed=False,
                    reason=f"候选人年龄 {candidate_age} 岁，超过要求的最大年龄 {age_max} 岁。",
                ))
            else:
                checks.append(CandidateConstraintCheck(
                    item=label, passed=True,
                    reason=f"候选人年龄 {candidate_age} 岁，符合年龄要求。",
                ))

        return checks

    _EDUCATION_RANK = {"博士": 5, "硕士": 4, "本科": 3, "大专": 2, "中专": 1, "高中": 0}

    def _check_experience_constraint(self, normalized: str, work_years: float) -> tuple[bool, str]:
        m = re.search(r"(\d+)年以上", normalized)
        if not m:
            return False, "无法解析经验年限要求。"
        required = int(m.group(1))
        actual = work_years or 0
        passed = actual >= required
        actual_str = f"{actual:.0f}" if actual == int(actual) else f"{actual:.1f}"
        if passed:
            return True, f"候选人工作年限约 {actual_str} 年，满足「{required} 年以上」要求。"
        return False, f"候选人工作年限约 {actual_str} 年，不满足「{required} 年以上」要求。"

    def _check_education_constraint(self, normalized: str, card_education: str, text: str) -> tuple[bool, str]:
        required_level = next((edu for edu in self._EDUCATION_RANK if edu in normalized), None)
        if required_level is None:
            passed = normalized.lower() in text
            return passed, ("简历里存在对应证据。" if passed else "简历里没有看到对应证据。")
        required_rank = self._EDUCATION_RANK[required_level]
        sources = [card_education or "", text]
        candidate_rank = max(
            (rank for edu, rank in self._EDUCATION_RANK.items() if any(edu in s for s in sources)),
            default=-1,
        )
        if candidate_rank >= required_rank:
            actual = card_education or "简历所示学历"
            return True, f"候选人学历「{actual}」满足「{required_level}及以上」要求。"
        if candidate_rank >= 0:
            actual = card_education or "简历所示学历"
            return False, f"候选人学历「{actual}」低于要求的「{required_level}及以上」。"
        return False, f"简历中未找到明确学历信息，无法确认是否达到「{required_level}及以上」要求。"

    def _build_dimension_checks(
        self,
        blueprint: ScreeningBlueprint,
        parsed_resume: ParsedResume,
        original_resume: str,
    ) -> list[CandidateDimensionCheck]:
        text = self._combined_text(None, parsed_resume, original_resume)
        checks: list[CandidateDimensionCheck] = []
        for item in blueprint.scoring_dimensions:
            score = self._score_dimension(item.label, item.note, text)
            checks.append(
                CandidateDimensionCheck(
                    key=item.key,
                    label=item.label,
                    weight=item.weight,
                    score=score,
                    reason=self._dimension_reason(item.label, score),
                )
            )
        return checks

    def _score_dimension(self, label: str, note: str, text: str) -> int:
        haystack = f"{label} {note} {text}".lower()
        if "技术" in label:
            return 92 if any(term in haystack for term in ["机械", "设备", "电气", "液压", "图纸", "装配"]) else 55
        if "现场" in label:
            return 90 if any(term in haystack for term in ["现场", "安装", "调试", "实施", "交付"]) else 50
        if "故障" in label:
            return 88 if any(term in haystack for term in ["故障", "排障", "维修", "维护", "异常"]) else 45
        if "独立" in label:
            return 80 if any(term in haystack for term in ["独立", "单兵", "自主"]) else 50
        if "沟通" in label or "服务" in label:
            return 75 if any(term in haystack for term in ["客户", "培训", "服务", "沟通", "支持"]) else 45
        if "出差" in label:
            return 72 if any(term in haystack for term in ["出差", "驻外", "现场", "矿山", "工厂"]) else 40
        return 55

    def _dimension_reason(self, label: str, score: int) -> str:
        if score >= 85:
            return f"简历里能看到与“{label}”直接相关的强证据。"
        if score >= 65:
            return f"简历里有一定“{label}”信号，但还缺少更具体的案例或结果。"
        return f"简历里缺少足够的“{label}”直接证据。"

    def _build_evidence_items(self, parsed_resume: ParsedResume) -> list[CandidateEvidence]:
        items: list[CandidateEvidence] = []
        for action in parsed_resume.action_terms[:5]:
            items.append(
                CandidateEvidence(
                    type="action",
                    title=action,
                    content=f"简历中出现与“{action}”相关的动作描述。",
                    impact="说明候选人做过相关实操。",
                    confidence=0.7,
                )
            )
        for number in parsed_resume.numeric_evidence[:3]:
            items.append(
                CandidateEvidence(
                    type="number",
                    title=f"数字证据 {number}",
                    content=f"简历中出现数字信息：{number}",
                    impact="可作为规模、结果或工作量的辅助证据。",
                    confidence=0.6,
                )
            )
        return items

    def _build_risk_items(self, blueprint: ScreeningBlueprint, parsed_resume: ParsedResume, original_resume: str) -> list[str]:
        risks = list(parsed_resume.risk_signals)
        text = self._combined_text(None, parsed_resume, original_resume)
        if any(term in text for term in self.RETAIL_TERMS):
            risks.append("履历偏零售或门店场景，需要确认是否具备工业设备现场能力。")
        if any(term in text for term in self.SUPPORT_TERMS):
            risks.append("履历里有协助/支持型表述，需要确认是否真正独立承担过任务。")
        if blueprint.exclude_rules and not risks:
            risks.append("仍需继续核查是否触发最终画像中的排除项。")
        return self._unique_strings(risks)

    def _build_value_signals(self, parsed_resume: ParsedResume, original_resume: str) -> list[str]:
        signals: list[str] = []
        text = self._combined_text(None, parsed_resume, original_resume)
        if any(term in text for term in ["安装", "调试", "维护", "维修", "排障"]):
            signals.append("具备安装调试和售后维护相关动作证据。")
        if any(term in text for term in ["现场", "工厂", "矿山", "出差"]):
            signals.append("具备现场或长期出差相关场景信号。")
        if parsed_resume.numeric_evidence:
            signals.append("简历里存在数字证据，可继续核查其真实性与业务价值。")
        return self._unique_strings(signals)

    def _build_uncertainties(
        self,
        parsed_resume: ParsedResume,
        dimension_checks: list[CandidateDimensionCheck],
    ) -> list[str]:
        uncertainties: list[str] = []
        if not parsed_resume.numeric_evidence:
            uncertainties.append("缺少可量化结果，建议面试追问项目规模、效率提升或处理成果。")
        if len(parsed_resume.work_experiences) <= 1:
            uncertainties.append("工作经历拆解较少，建议继续核查真实职责边界。")
        for item in dimension_checks:
            if item.score < max(60, int(item.weight * 0.75)):
                uncertainties.append(f"{item.label}证据偏弱，建议在面试中重点追问。")
        return self._unique_strings(uncertainties)

    def _build_interview_focus(
        self,
        blueprint: ScreeningBlueprint,
        risk_items: list[str],
        uncertainties: list[str],
    ) -> list[str]:
        focus: list[str] = []
        focus.extend(blueprint.private_notes[:3])
        focus.extend(risk_items[:2])
        focus.extend(uncertainties[:3])
        return self._unique_strings(focus)[:6]

    def _parse_work_experiences(self, timeline: list[str]) -> list[ResumeWorkEntry]:
        items: list[ResumeWorkEntry] = []
        for line in timeline:
            if not self._looks_like_work_line(line):
                continue
            match = re.match(r"^\s*(.+?)-(.+?)\s+(.+?)\s+\|\s+(.+?)(?:：|\|)?\s*(.*)$", line)
            if not match:
                continue
            start, end, company, position, summary = match.groups()
            items.append(
                ResumeWorkEntry(
                    company=company.strip(),
                    position=position.strip(),
                    start=start.strip(),
                    end=end.strip(),
                    summary=summary.strip(),
                )
            )
        return items

    def _parse_education_experiences(self, timeline: list[str]) -> list[ResumeEducationEntry]:
        items: list[ResumeEducationEntry] = []
        for line in timeline:
            if not any(term in line for term in self.EDUCATION_TERMS):
                continue
            match = re.match(r"^\s*(.+?)-(.+?)\s+(.+?)\s+\|\s+(.+?)(?:：|\|)?\s*(.*)$", line)
            if not match:
                continue
            start, end, school, degree, summary = match.groups()
            items.append(
                ResumeEducationEntry(
                    school=school.strip(),
                    degree=self._sanitize_education_degree(degree.strip()),
                    start=start.strip(),
                    end=end.strip(),
                    summary=summary.strip(),
                )
            )
        return items

    def _extract_action_terms(self, resume_text: str) -> list[str]:
        lower = resume_text.lower()
        found = [term for term in self.ACTION_TERMS if term.lower() in lower]
        return self._unique_strings(found)

    def _extract_numeric_evidence(self, resume_text: str) -> list[str]:
        raw = re.findall(r"\d+(?:\.\d+)?(?:万|元|台|套|家|次|项|天|小时|%|年)?", resume_text)
        values = [item for item in raw if not re.fullmatch(r"\d{4}年?", item)]
        return self._unique_strings(values)

    def _extract_risk_signals(self, resume_text: str, timeline: list[str]) -> list[str]:
        risks: list[str] = []
        if len(timeline) >= 4:
            risks.append("检测到多段履历，建议面试时逐段核查变动原因。")
        if "负责" in resume_text and not re.search(r"\d+(?:万|元|台|套|家|次|项|天|小时|%)", resume_text):
            risks.append("简历里职责描述较多，但缺少数字或结果证明。")
        return risks

    def _field_fit_score(self, parsed_resume: ParsedResume, blueprint: ScreeningBlueprint, original_resume: str) -> int:
        text = self._combined_text(None, parsed_resume, original_resume)
        matches = 0
        for target in blueprint.industry_targets:
            tokens = [token for token in re.split(r"[\s/、，,]+", target.lower()) if token]
            if any(token in text for token in tokens):
                matches += 1
        return min(10, matches * 2 + (2 if any(term in text for term in self.FIELD_TERMS) else 0))

    def _stability_score(self, parsed_resume: ParsedResume) -> int:
        jobs = parsed_resume.work_experiences
        if len(jobs) <= 1:
            return 4
        return max(2, 5 - max(0, len(jobs) - 2))

    def _weighted_dimension_score(self, checks: list[CandidateDimensionCheck]) -> float:
        total_weight = sum(max(item.weight, 1) for item in checks)
        if total_weight <= 0:
            return 0.0
        weighted = sum(item.score * max(item.weight, 1) for item in checks)
        return weighted / total_weight

    def _compact_focus(self, note: str) -> str:
        if not note:
            return ""
        parts = [part.strip("；。 ") for part in re.split(r"[；。]\s*", note) if part.strip()]
        return "；".join(parts[:3])

    def _combined_text(self, card: CandidateCard | None, parsed_resume: ParsedResume, original_resume: str) -> str:
        parts = [
            original_resume or "",
            "\n".join(parsed_resume.timeline_summary),
            " ".join(parsed_resume.action_terms),
            " ".join(parsed_resume.numeric_evidence),
        ]
        if card is not None:
            parts.extend([card.summary, card.current_company, card.current_position, card.education])
        return self._clean_resume_text("\n".join(part for part in parts if part)).lower()

    def _looks_like_work_line(self, line: str) -> bool:
        return bool(re.search(r"\|\s+", line)) and not any(term in line for term in self.EDUCATION_TERMS)

    def _sanitize_education_degree(self, degree: str) -> str:
        if not degree or re.fullmatch(r"\d+", degree):
            return "未知学历"
        return degree

    def _clean_resume_text(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text or "").strip()
        return cleaned[:2200]

    def _normalize_evidence_type(self, value: str) -> str:
        return value if value in {"action", "number", "timeline", "value", "risk"} else "action"

    def _string_or_list_of_dict(self, value: Any) -> list[dict[str, Any]]:
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    def _string_list(self, value: Any) -> list[str]:
        return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []

    def _unique_strings(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    def _score_to_grade(self, score: int) -> str:
        if score >= 90:
            return "S"
        if score >= 80:
            return "A"
        if score >= 65:
            return "B"
        return "C"


candidate_screening_service = CandidateScreeningService()
