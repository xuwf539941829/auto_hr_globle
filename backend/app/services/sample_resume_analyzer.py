from __future__ import annotations

import json
import random
import re
import time
from collections import Counter
from typing import Any, Iterable
from urllib import error, request

from app.core.logging import get_logger
from app.models.domain import CompetencyWeight, JobProfile, ProfileRule
from app.services.jd_translator import LLMConfig, LLMTranslationError, RuleBasedJDTranslator
from app.services.llm_logging import log_llm_error, log_llm_request, log_llm_response, new_trace_id
from app.services.llm_trace_service import llm_trace_service

logger = get_logger(__name__)


class SampleResumeAnalyzer:
    COMPETENCY_LABEL_MAPPING = {
        "technical knowledge": "技术基础",
        "technical foundation": "技术基础",
        "technical skills": "技术基础",
        "field execution": "现场执行",
        "field service": "现场执行",
        "field operation": "现场执行",
        "fault resolution": "故障闭环",
        "problem solving": "故障闭环",
        "issue closure": "故障闭环",
        "service communication": "服务沟通",
        "customer communication": "服务沟通",
        "communication": "服务沟通",
        "independent operation": "独立操作",
        "onsite execution": "现场执行",
        "travel adaptability": "出差适应性",
        "adaptability": "出差适应性",
        "business development": "客户开拓",
        "complex deal": "复杂成交",
        "relationship management": "客户经营",
        "result orientation": "结果导向",
        "technical knowledge_cn": "技术基础",
        "技术知识": "技术基础",
        "技术技能": "技术基础",
        "现场操作": "现场执行",
        "问题解决": "故障闭环",
        "沟通能力": "服务沟通",
        "沟通服务": "服务沟通",
        "独立操作能力": "独立操作",
    }

    AFTER_SALES_SIGNALS = ["售后", "安装", "调试", "维护", "维修", "故障", "排障", "技术支持", "现场服务"]
    SALES_SIGNALS = ["大客户", "客户开发", "陌拜", "渠道", "招投标", "签约", "回款", "成交", "区域市场"]
    FIELD_SIGNALS = ["矿山", "工厂", "现场", "驻外", "出差", "偏远", "长期外出"]
    NUMBER_PATTERN = r"\d+(?:\.\d+)?\s*(?:万|万元|美金|美元|台|套|个|%|家|单|项)"
    EXPANSION_SIGNAL_MAPPINGS = {
        "工程机械": "工程机械售后",
        "矿山": "矿山设备售后",
        "矿山设备": "矿山设备售后",
        "破碎机": "矿山设备售后",
        "制砂机": "矿山设备售后",
        "路面机械": "工程机械售后",
        "电控": "设备安装调试与维护",
        "电气": "设备安装调试与维护",
        "安装调试": "设备安装调试与维护",
        "售后服务": "工业设备售后",
    }

    def analyze(
        self,
        job_id: str,
        job_name: str,
        base_profile: JobProfile,
        resumes: list[str],
        notes: str | None = None,
    ) -> JobProfile:
        config = LLMConfig.from_env()
        if config.enabled:
            try:
                logger.info("LLM sample resume analysis started for job %s model=%s", job_id, config.model)
                return self._analyze_with_llm(job_id, job_name, base_profile, resumes, notes, config)
            except Exception as exc:
                logger.warning("LLM sample resume analysis failed for job %s, fallback to rules: %s", job_id, exc)

        logger.info("Rule-based sample resume analysis started for job %s", job_id)
        return self._analyze_with_rules(job_id, job_name, base_profile, resumes, notes)

    def _analyze_with_llm(
        self,
        job_id: str,
        job_name: str,
        base_profile: JobProfile,
        resumes: list[str],
        notes: str | None,
        config: LLMConfig,
    ) -> JobProfile:
        trace_id = new_trace_id("sample")
        llm_trace_service.record_metadata(trace_id, kind="sample_resume_analysis", job_id=job_id)
        endpoint = f"{config.base_url}/responses" if config.api_style == "responses" else f"{config.base_url}/chat/completions"
        prompt = self._build_prompt(job_name, base_profile, resumes, notes)

        if config.api_style == "responses":
            body = {
                "model": config.model,
                "input": [
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": "你负责根据优秀样本简历增强岗位画像，只返回 JSON。"}],
                    },
                    {"role": "user", "content": [{"type": "input_text", "text": prompt}]},
                ],
            }
        else:
            body = {
                "model": config.model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": "你负责根据优秀样本简历增强岗位画像，只返回 JSON。"},
                    {"role": "user", "content": prompt},
                ],
            }

        log_llm_request(trace_id, endpoint, body)
        req = request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"},
            method="POST",
        )

        last_url_exc: Exception | None = None
        raw: str | None = None
        for attempt in range(3):
            try:
                with request.urlopen(req, timeout=config.timeout_seconds) as response:
                    raw = response.read().decode("utf-8")
                break  # 成功，退出重试循环
            except error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="ignore")
                log_llm_error(trace_id, f"HTTP {exc.code}: {detail}")
                raise LLMTranslationError(f"HTTP {exc.code}: {detail}") from exc
            except error.URLError as exc:
                last_url_exc = exc
                wait = 2 ** attempt + random.uniform(0, 1)  # 1-2s → 2-3s → 4-5s
                logger.warning(
                    "LLM sample analysis network error (attempt %s/3), retry in %.1fs: %s",
                    attempt + 1, wait, exc.reason,
                )
                if attempt < 2:
                    time.sleep(wait)
        else:
            log_llm_error(trace_id, f"URL error after 3 attempts: {last_url_exc}")
            raise LLMTranslationError(str(last_url_exc)) from last_url_exc

        log_llm_response(trace_id, raw)
        payload = self._extract_json(raw, config.api_style)
        insights = self._extract_resume_insights(resumes)

        competencies = self._merge_competencies(base_profile.competencies, payload.get("competencies"), insights)
        industries = self._normalize_industry_expansion(
            payload.get("industry_expansion"),
            base_profile.industry_expansion.items,
            insights,
        )
        hard_constraints, downgraded_hard_constraints = self._normalize_hard_constraints(
            payload.get("hard_constraints"),
            base_profile.hard_constraints.items,
        )
        exclude_rules, downgraded_exclude_rules = self._normalize_exclude_rules(
            payload.get("exclude_rules"),
            base_profile.exclude_rules.items,
        )
        private_notes = self._normalize_list(payload.get("private_notes"), base_profile.private_notes)
        private_notes.extend(downgraded_hard_constraints)
        private_notes.extend(downgraded_exclude_rules)
        private_notes = self._merge_private_notes(private_notes, notes, insights)
        impact_summary = str(payload.get("impact_summary") or "").strip() or self._build_sample_impact_summary(job_name, insights)

        return JobProfile(
            version_id=f"{job_id}-profile-v3-sample",
            version_name="V3 样本增强画像",
            job_id=job_id,
            hard_constraints=ProfileRule(title="硬性门槛", items=hard_constraints),
            competencies=competencies,
            industry_expansion=ProfileRule(title="可迁移行业", items=industries),
            exclude_rules=ProfileRule(title="排除项", items=exclude_rules),
            private_notes=private_notes,
            impact_summary=impact_summary,
            translation_source="llm",
            translation_notes=[
                f"模型：{config.model}",
                "当前画像已结合优秀样本简历做增强，不再只依赖 JD 初稿。",
                f"样本中高频信号：{self._summarize_insights(insights)}",
            ],
        )

    def _analyze_with_rules(
        self,
        job_id: str,
        job_name: str,
        base_profile: JobProfile,
        resumes: list[str],
        notes: str | None,
    ) -> JobProfile:
        insights = self._extract_resume_insights(resumes)
        competencies = self._merge_competencies(base_profile.competencies, None, insights)
        industries = self._normalize_industry_expansion(None, base_profile.industry_expansion.items, insights)
        hard_constraints, downgraded_hard_constraints = self._normalize_hard_constraints(
            None,
            base_profile.hard_constraints.items,
        )
        exclude_rules, downgraded_exclude_rules = self._normalize_exclude_rules(
            None,
            base_profile.exclude_rules.items,
        )
        private_notes = self._merge_private_notes(list(base_profile.private_notes), notes, insights)
        private_notes.extend(downgraded_hard_constraints)
        private_notes.extend(downgraded_exclude_rules)
        private_notes = self._unique(private_notes)

        return JobProfile(
            version_id=f"{job_id}-profile-v3-sample",
            version_name="V3 样本增强画像",
            job_id=job_id,
            hard_constraints=ProfileRule(title="硬性门槛", items=hard_constraints),
            competencies=competencies,
            industry_expansion=ProfileRule(title="可迁移行业", items=industries),
            exclude_rules=ProfileRule(title="排除项", items=exclude_rules),
            private_notes=private_notes,
            impact_summary=self._build_sample_impact_summary(job_name, insights),
            translation_source="rules",
            translation_notes=[
                "当前画像已基于优秀样本做规则增强。",
                f"样本中高频信号：{self._summarize_insights(insights)}",
            ],
        )

    @staticmethod
    def _build_prompt(job_name: str, base_profile: JobProfile, resumes: list[str], notes: str | None) -> str:
        prompt = {
            "task": "请根据优秀样本简历增强当前岗位画像。重点不是重写 JD，而是从样本里提炼真正的偏好信号，并把它们汇总成更适合筛人的标准。",
            "rules": [
                "优先提炼样本里重复出现的动作证据、数字证据、行业迁移和环境适应信号。",
                "不要推翻当前画像，而是在当前画像基础上做增强和纠偏。",
                "competencies 优先沿用当前画像已有维度；如需新增维度，必须是样本里反复出现且对筛人有实际价值的维度。",
                "hard_constraints 不要随意扩张，只保留样本明显支持且和 JD 初稿不冲突的硬门槛。",
                "private_notes 要体现：老板为什么会喜欢这类人、后续面试该追问什么、哪些伪匹配要警惕。",
                "industry_expansion 优先输出可迁移岗位场景，而不是空泛行业名。",
                "输出必须为 JSON 对象。",
            ],
            "job_name": job_name,
            "base_profile": base_profile.model_dump(),
            "sample_resumes": resumes,
            "notes": notes or "",
            "json_schema": {
                "hard_constraints": ["string"],
                "industry_expansion": ["string"],
                "exclude_rules": ["string"],
                "private_notes": ["string"],
                "impact_summary": "string",
                "competencies": [
                    {
                        "key": "string",
                        "label": "string",
                        "weight": 80,
                        "note": "string",
                        "definition": "string",
                        "look_for": ["string"],
                        "avoid_signals": ["string"],
                    }
                ],
            },
        }
        return json.dumps(prompt, ensure_ascii=False, indent=2)

    @staticmethod
    def _extract_json(raw: str, api_style: str) -> dict[str, Any]:
        payload = json.loads(raw)
        if api_style == "responses":
            texts: list[str] = []
            for item in payload.get("output", []):
                for content in item.get("content", []):
                    text = content.get("text")
                    if text:
                        texts.append(text)
            body = "\n".join(texts).strip()
        else:
            choices = payload.get("choices", [])
            body = choices[0].get("message", {}).get("content", "") if choices else ""

        try:
            return json.loads(body)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", body, re.DOTALL)
            if not match:
                raise LLMTranslationError("LLM 返回的样本分析结果不是合法 JSON。")
            return json.loads(match.group(0))

    def _extract_resume_insights(self, resumes: list[str]) -> dict[str, Any]:
        text = "\n".join(resumes)
        numbers = self._extract_numeric_evidence(text)
        signals = {
            "after_sales": self._mentions_any(text, self.AFTER_SALES_SIGNALS),
            "sales": self._mentions_any(text, self.SALES_SIGNALS),
            "field": self._mentions_any(text, self.FIELD_SIGNALS),
            "numbers": numbers,
            "keywords": self._top_keywords(text),
            "expansion_signals": self._extract_expansion_signals(text),
        }
        return signals

    def _merge_competencies(
        self,
        base: list[CompetencyWeight],
        incoming: object,
        insights: dict[str, Any],
    ) -> list[CompetencyWeight]:
        merged = {item.key: item.model_copy(deep=True) for item in base}

        if isinstance(incoming, list):
            for item in incoming:
                if not isinstance(item, dict):
                    continue
                raw_label = str(item.get("label") or "").strip()
                label = self._normalize_dimension_label(raw_label)
                raw_key = str(item.get("key") or label).strip()
                if not raw_key and not label:
                    continue
                key = RuleBasedJDTranslator._sanitize_key(raw_key or label)
                existing = merged.get(key)
                try:
                    weight = max(0, min(100, int(item.get("weight", existing.weight if existing else 70))))
                except (TypeError, ValueError):
                    weight = existing.weight if existing else 70

                note_parts = [str(item.get("note") or "").strip(), str(item.get("definition") or "").strip()]
                look_for = self._normalize_list(item.get("look_for"), [])
                avoid = self._normalize_list(item.get("avoid_signals"), [])
                if look_for:
                    note_parts.append(f"重点证据：{'、'.join(look_for[:4])}")
                if avoid:
                    note_parts.append(f"伪匹配警报：{'、'.join(avoid[:3])}")
                note = "；".join(part for part in note_parts if part) or (existing.note if existing else "请根据样本中的真实证据判断该维度。")
                merged[key] = CompetencyWeight(
                    key=key,
                    label=label or (existing.label if existing else raw_key),
                    weight=weight,
                    note=note,
                )

        for item in merged.values():
            label = item.label
            if label in {"技术基础", "现场执行", "故障闭环"} and insights["after_sales"]:
                item.weight = min(100, item.weight + 4)
            if label in {"现场执行", "出差适应性"} and insights["field"]:
                item.weight = min(100, item.weight + 4)
            if label in {"结果导向", "复杂成交", "客户开拓"} and insights["sales"]:
                item.weight = min(100, item.weight + 4)
            if insights["numbers"] and label in {"故障闭环", "结果导向", "客户开拓"}:
                item.note = f"{item.note}；样本中存在可量化结果或数字证据，后续筛选应优先看可量化证明。"

        return self._sort_competencies(list(merged.values()))

    def _normalize_hard_constraints(self, value: object, fallback: list[str]) -> tuple[list[str], list[str]]:
        items = self._normalize_list(value, fallback)
        banned = ["沟通", "服务意识", "主动性", "应变能力", "问题处理能力", "团队协作", "抗压"]
        certificate_markers = ["电工证", "焊工证", "证书", "资格证", "上岗证", "操作证"]

        filtered: list[str] = []
        downgraded: list[str] = []
        for item in items:
            if any(marker in item for marker in certificate_markers):
                downgraded.append(f"样本里出现了证书信号，可作为优先项而非硬门槛：{item}")
                continue
            if any(marker in item for marker in banned):
                downgraded.append(f"以下内容建议转为维度判断或面试追问，不计入硬门槛：{item}")
                continue
            filtered.append(item)

        final_constraints = self._unique(filtered) or list(fallback)
        return final_constraints, self._unique(downgraded)

    def _normalize_exclude_rules(self, value: object, fallback: list[str]) -> tuple[list[str], list[str]]:
        items = self._normalize_list(value, fallback)
        subjective_markers = ["团队协作", "协作精神", "责任心", "主动性", "态度", "抗压", "稳定性差", "性格"]

        filtered: list[str] = []
        downgraded: list[str] = []
        for item in items:
            if any(marker in item for marker in subjective_markers):
                downgraded.append(f"以下内容更适合作为面试警惕项，不建议直接作为排除项：{item}")
                continue
            filtered.append(item)

        return self._unique(filtered), self._unique(downgraded)

    def _normalize_industry_expansion(
        self,
        value: object,
        fallback: list[str],
        insights: dict[str, Any],
    ) -> list[str]:
        items = self._normalize_list(value, fallback)
        mapping = {
            "机械设备售后": "工业设备售后",
            "机械设备售后技术支持": "工业设备售后",
            "设备安装调试": "设备安装调试与维护",
            "设备维护": "设备安装调试与维护",
        }
        normalized = [mapping.get(item, item) for item in items]

        if insights["after_sales"]:
            normalized.append("工业设备售后")
            normalized.append("设备安装调试与维护")
        if insights["field"]:
            normalized.append("现场技术服务")
        if insights["sales"]:
            normalized.append("工业设备客户经营")
        normalized.extend(insights.get("expansion_signals", []))

        return self._unique(normalized)

    def _merge_private_notes(self, notes: list[str], user_notes: str | None, insights: dict[str, Any]) -> list[str]:
        merged = list(notes)
        if insights["after_sales"]:
            merged.append("优秀样本反复强调现场安装、调试、维护或排障经历，后续应优先核查真实单兵作业能力。")
        if insights["field"]:
            merged.append("优秀样本带有明显现场、矿山、工厂或长期出差信号，后续应重点看环境适应性。")
        if insights["numbers"]:
            merged.append(f"优秀样本里出现了数字证据：{'、'.join(insights['numbers'][:3])}，后续筛选应优先看可量化结果。")
        if insights["keywords"]:
            merged.append(f"样本里高频出现的关键词：{'、'.join(insights['keywords'][:5])}。")
        if user_notes:
            merged.append(f"样本备注：{user_notes}")
        return self._unique(merged)

    @staticmethod
    def _build_sample_impact_summary(job_name: str, insights: dict[str, Any]) -> str:
        summary_parts = [f"{job_name} 已结合优秀样本简历完成增强画像"]
        if insights["after_sales"]:
            summary_parts.append("当前更看重现场排障、安装调试和售后技术服务证据")
        if insights["field"]:
            summary_parts.append("样本明显偏现场型，后续筛选会更关注环境适应性")
        if insights["numbers"]:
            summary_parts.append("样本中出现可量化结果，后续会优先寻找数字证据")
        return "，".join(summary_parts) + "。"

    @staticmethod
    def _summarize_insights(insights: dict[str, Any]) -> str:
        parts: list[str] = []
        if insights["after_sales"]:
            parts.append("售后/调试/维护")
        if insights["field"]:
            parts.append("现场/矿山/工厂")
        if insights["sales"]:
            parts.append("客户推进/业务结果")
        if insights["numbers"]:
            parts.append(f"数字证据 {len(insights['numbers'])} 处")
        if insights.get("expansion_signals"):
            parts.append(f"扩展场景 {len(insights['expansion_signals'])} 个")
        return "、".join(parts) if parts else "暂无显著高频信号"

    def _extract_numeric_evidence(self, text: str) -> list[str]:
        raw_matches = re.findall(self.NUMBER_PATTERN, text)
        cleaned: list[str] = []
        for item in raw_matches:
            value = str(item).strip()
            if re.fullmatch(r"\d{4}年", value):
                continue
            if re.fullmatch(r"\d+年", value):
                continue
            cleaned.append(value)
        return self._unique(cleaned)

    def _extract_expansion_signals(self, text: str) -> list[str]:
        found: list[str] = []
        for keyword, mapped in self.EXPANSION_SIGNAL_MAPPINGS.items():
            if keyword in text:
                found.append(mapped)
        return self._unique(found)

    @staticmethod
    def _normalize_list(value: object, fallback: list[str]) -> list[str]:
        if isinstance(value, list):
            cleaned = [str(item).strip() for item in value if str(item).strip()]
            if cleaned:
                return cleaned
        if isinstance(value, str) and value.strip():
            cleaned = [item.strip() for item in re.split(r"[，。；\n]+", value) if item.strip()]
            if cleaned:
                return cleaned
        return list(fallback)

    def _normalize_dimension_label(self, label: str) -> str:
        normalized = self.COMPETENCY_LABEL_MAPPING.get(label.lower(), label)
        return self.COMPETENCY_LABEL_MAPPING.get(normalized, normalized)

    @staticmethod
    def _sort_competencies(items: list[CompetencyWeight]) -> list[CompetencyWeight]:
        priority = {
            "技术基础": 1,
            "现场执行": 2,
            "故障闭环": 3,
            "独立操作": 4,
            "服务沟通": 5,
            "出差适应性": 6,
            "客户开拓": 7,
            "复杂成交": 8,
            "客户经营": 9,
            "结果导向": 10,
        }
        return sorted(items, key=lambda item: (priority.get(item.label, 50), -item.weight, item.label))

    @staticmethod
    def _top_keywords(text: str) -> list[str]:
        keywords = re.findall(r"[\u4e00-\u9fff]{2,8}", text)
        stopwords = {
            "负责",
            "能够",
            "进行",
            "相关",
            "工作",
            "岗位",
            "要求",
            "具有",
            "以及",
            "提供",
            "客户",
            "经验",
        }
        filtered = [word for word in keywords if word not in stopwords]
        return [word for word, _ in Counter(filtered).most_common(8)]

    @staticmethod
    def _mentions_any(text: str, keywords: Iterable[str]) -> bool:
        lowered = text.lower()
        return any(keyword.lower() in lowered for keyword in keywords)

    @staticmethod
    def _unique(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            cleaned = str(item).strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                result.append(cleaned)
        return result


sample_resume_analyzer = SampleResumeAnalyzer()
