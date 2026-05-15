from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

import requests as http_requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.core.logging import get_logger
from app.models.domain import CompetencyWeight, JobProfile, ProfileRule
from app.services.llm_logging import log_llm_error, log_llm_request, log_llm_response, new_trace_id
from app.services.llm_trace_service import llm_trace_service
from app.services.settings_service import settings_service

logger = get_logger(__name__)


class LLMTranslationError(RuntimeError):
    pass


@dataclass(slots=True)
class LLMConfig:
    api_key: str | None
    base_url: str
    model: str
    timeout_seconds: int
    api_style: str

    @classmethod
    def from_env(cls) -> "LLMConfig":
        settings = settings_service.get_llm_settings()
        return cls(
            api_key=settings.api_key,
            base_url=settings.base_url.rstrip("/"),
            model=settings.model,
            timeout_seconds=settings.timeout_seconds,
            api_style=settings.api_style.strip().lower(),
        )

    @property
    def enabled(self) -> bool:
        settings = settings_service.get_llm_settings()
        return bool(settings.enabled and self.api_key)


class RuleBasedJDTranslator:
    SALES_TERMS = ["销售", "客户开发", "开拓", "渠道", "KA", "大客户", "成交", "签约", "回款", "招投标"]
    AFTER_SALES_TERMS = ["售后", "安装", "调试", "维护", "维修", "故障", "排障", "技术支持", "现场服务"]
    PROJECT_TERMS = ["项目", "交付", "实施", "上线", "推进", "方案", "协调"]
    FIELD_TERMS = ["出差", "驻外", "矿山", "工厂", "现场", "驻点", "偏远", "长期外出"]
    PROCUREMENT_TERMS = ["采购经理", "采购主管", "采购总监", "采购工程师", "供应链管理", "供应商管理", "询价", "比价", "原材料采购", "零部件采购", "物料采购", "采购战略", "降本"]
    EDUCATION_ORDER = ["博士", "硕士", "本科", "大专", "中专", "高中"]

    def translate(self, job_id: str, job_name: str, raw_jd_text: str, notes: str | None = None) -> JobProfile:
        logger.info("Rule-based JD translation started for job %s", job_id)
        full_text = f"{job_name}\n{raw_jd_text or ''}".strip()
        job_understanding = self._infer_job_understanding(job_name, full_text)
        competencies = self._build_dynamic_competencies(job_understanding, full_text)
        age_min, age_max = self._extract_age_range(full_text)
        hard_constraints = self._build_hard_constraints(full_text, age_min, age_max)
        industry_expansion = self._build_industry_expansion(job_understanding, full_text)
        exclude_rules = self._build_exclude_rules(job_understanding, full_text)
        private_notes = self._build_private_notes(job_understanding, full_text, notes)
        impact_summary = self._build_summary(job_name, job_understanding, competencies)

        return JobProfile(
            version_id=f"{job_id}-profile-v2",
            version_name="V2 画像初稿",
            job_id=job_id,
            hard_constraints=ProfileRule(title="硬性门槛", items=hard_constraints),
            competencies=competencies,
            industry_expansion=ProfileRule(title="可迁移行业", items=industry_expansion),
            exclude_rules=ProfileRule(title="排除项", items=exclude_rules),
            private_notes=private_notes,
            impact_summary=impact_summary,
            translation_source="rules",
            translation_notes=[
                f"岗位判断：{job_understanding['name']}",
                "当前为规则引擎动态转译结果，会根据职位名称和 JD 内容自动生成维度。",
            ],
            age_min=age_min,
            age_max=age_max,
        )

    def _infer_job_understanding(self, job_name: str, full_text: str) -> dict[str, str]:
        text = f"{job_name}\n{full_text}"
        if self._mentions_any(text, self.AFTER_SALES_TERMS):
            return {
                "key": "after_sales_service",
                "name": "售后技术服务岗",
                "goal": "保障设备正常运行，完成安装、调试、维护和故障闭环。",
            }
        if self._mentions_any(text, self.SALES_TERMS):
            return {
                "key": "b2b_sales",
                "name": "工业设备销售岗",
                "goal": "开发客户、推进成交并完成项目和回款闭环。",
            }
        if self._mentions_any(text, self.PROJECT_TERMS):
            return {
                "key": "project_delivery",
                "name": "项目交付推进岗",
                "goal": "协调资源推进交付实施与项目落地。",
            }
        if self._mentions_any(text, self.PROCUREMENT_TERMS):
            return {
                "key": "procurement",
                "name": "采购管理岗",
                "goal": "建立供应商体系，控制采购成本，保障供应链稳定运转。",
            }
        return {
            "key": "general_industrial_role",
            "name": "工业场景综合岗位",
            "goal": "根据 JD 要求完成现场执行、客户沟通与业务闭环。",
        }

    def _build_hard_constraints(self, full_text: str, age_min: int | None = None, age_max: int | None = None) -> list[str]:
        constraints: list[str] = []
        education = self._extract_education(full_text)
        if education:
            constraints.append(education)

        experience = self._extract_min_experience_years(full_text)
        if experience > 0:
            constraints.append(f"{experience}年以上相关经验")

        if age_min and age_max:
            constraints.append(f"年龄要求：{age_min}-{age_max}岁")
        elif age_max:
            constraints.append(f"年龄要求：{age_max}岁以下")
        elif age_min:
            constraints.append(f"年龄要求：{age_min}岁以上")

        if self._mentions_any(full_text, self.FIELD_TERMS):
            constraints.append("接受出差、驻外或现场工作")

        if self._mentions_any(full_text, ["图纸", "机械基础", "设备原理", "电气图", "技术图纸"]):
            constraints.append("能看懂技术图纸并具备机械设备基础知识")

        return self._unique(constraints)

    def _build_industry_expansion(self, understanding: dict[str, str], full_text: str) -> list[str]:
        items: list[str] = []

        if understanding["key"] == "procurement":
            items.extend(["机械制造/工业品原材料与零部件采购", "工贸一体化供应链管理", "制造业供应商开发与管理"])
            return self._unique(items)

        mappings = {
            "机械": ["工业设备售后", "工程机械支持"],
            "设备": ["工业设备售后", "设备安装调试与维护"],
            "矿山": ["矿山设备售后", "现场技术服务"],
            "工厂": ["制造业现场服务", "工业设备运维"],
            "起重": ["起重设备售后", "重工设备服务"],
            "挖机": ["工程机械售后", "重工设备服务"],
            "售后": ["设备售后技术支持", "现场技术服务", "设备安装调试与维护"],
            "调试": ["设备安装调试与维护", "现场技术服务"],
        }
        for keyword, expanded in mappings.items():
            if keyword in full_text:
                items.extend(expanded)

        if understanding["key"] == "after_sales_service":
            items.extend(["设备售后技术支持", "故障排查与维护", "现场技术服务"])
        elif understanding["key"] == "b2b_sales":
            items.extend(["工业设备销售", "工程机械销售", "长决策周期 B 端销售"])
        elif understanding["key"] == "project_delivery":
            items.extend(["项目交付", "现场实施", "工业项目推进"])

        return self._unique(items) or ["工业场景相关岗位"]

    def _build_exclude_rules(self, understanding: dict[str, str], full_text: str) -> list[str]:
        rules: list[str] = []
        if understanding["key"] == "after_sales_service":
            rules.extend(
                [
                    "纯销售背景且没有安装、调试、维修或现场服务经历",
                    "不能接受出差或现场环境",
                    "只会协调外包资源，缺少亲自排障和动手操作经历",
                ]
            )
        elif understanding["key"] == "b2b_sales":
            rules.extend(
                [
                    "只有内勤跟单且无独立成交",
                    "纯零售或快消背景，缺少复杂 B 端决策链经验",
                    "连续短期跳槽且没有结果证明",
                ]
            )
        elif understanding["key"] == "procurement":
            rules.extend(
                [
                    "采购经验全部来自工程/建筑/幕墙/装饰行业，缺乏机械制造原材料或零部件采购背景",
                    "只有内部跟单或辅助采购经历，没有独立完成询价、比价、谈判和合同签订的全流程经验",
                    "供应商资源集中在建材、装饰材料领域，与机械工贸行业供应链无重叠",
                    "连续短期跳槽且无法提供具体降本数据或供应商优化成果",
                ]
            )
        else:
            rules.extend(
                [
                    "履历只有职责描述，没有动作证据或结果证明",
                    "明显不接受岗位要求的现场、协作或推进场景",
                ]
            )

        if self._mentions_any(full_text, ["服务意识", "沟通能力"]):
            rules.append("技术不错但服务意识弱、沟通配合差")

        return self._unique(rules)

    def _build_private_notes(self, understanding: dict[str, str], full_text: str, notes: str | None) -> list[str]:
        items = [f"岗位本质判断：{understanding['goal']}"]

        if understanding["key"] == "after_sales_service":
            items.append("面试时优先核查动手能力、现场排障能力和客户服务意识。")
        elif understanding["key"] == "b2b_sales":
            items.append("不要只看行业词，要追问其是否真正独立开发、推进项目并完成回款。")
        elif understanding["key"] == "project_delivery":
            items.append("重点看项目推进、跨部门协同和现场落地闭环，而不是泛泛协调。")
        elif understanding["key"] == "procurement":
            items.append("首要追问：历史采购的物料类型是什么？机械零部件/原材料 vs 建材/装饰/幕墙材料——两者不可迁移，后者直接排除。")
            items.append("核实方式：要求候选人现场列举 3-5 个机械工贸领域核心供应商名称及合作物料，含糊作答视为行业不符。")
            items.append("警惕信号：采购经理/主管头衔年限达标，但公司背景全为房建、装饰、幕墙、EPC——行业经验无法迁移。")

        if self._mentions_any(full_text, self.FIELD_TERMS):
            items.append("岗位含明显现场属性，能否适应矿山、工厂、驻外环境是关键。")

        if notes:
            items.append(f"补充备注：{notes}")

        return self._unique(items)

    def _build_dynamic_competencies(self, understanding: dict[str, str], full_text: str) -> list[CompetencyWeight]:
        if understanding["key"] == "after_sales_service":
            dimensions = [
                ("technical_foundation", "技术基础", 90, "是否具备机械设备基础知识、识图能力和原理理解能力"),
                ("onsite_execution", "现场执行", 88, "是否能独立完成安装、调试、巡检和现场处理"),
                ("troubleshooting", "故障闭环", 92, "是否能快速定位问题并推动形成有效闭环"),
                ("independent_operation", "独立操作", 80, "是否能在无人协助时独立完成技术操作和现场处理"),
                ("service_communication", "服务沟通", 76, "是否能把技术问题讲清楚、稳住客户并推进处理"),
                ("travel_adaptability", "出差适应性", 68, "是否能适应出差、驻外、矿山、工厂等复杂环境"),
            ]
        elif understanding["key"] == "b2b_sales":
            dimensions = [
                ("business_development", "客户开拓", 88, "是否能主动找线索、陌拜、挖需求并打开新客户"),
                ("complex_deal", "复杂成交", 92, "是否具备长决策周期、多角色推进和项目成交能力"),
                ("relationship_management", "客户经营", 82, "是否能持续跟进关键客户并维护决策链关系"),
                ("result_orientation", "结果导向", 84, "是否有签约、回款、项目落地等明确结果证明"),
                ("field_adaptation", "场景适应性", 76, "是否适应工厂、矿山、驻外或区域奔波场景"),
                ("stability", "稳定性", 60, "关注经历连续性，但更看重每段经历是否产出结果"),
            ]
        elif understanding["key"] == "project_delivery":
            dimensions = [
                ("project_planning", "项目规划", 84, "是否能拆解任务、排计划并把节点压实"),
                ("cross_functional_coordination", "跨部门协同", 88, "是否能调动客户、内部团队和供应商协同推进"),
                ("onsite_execution", "现场推进", 86, "是否具备现场实施、安装、交付或验收推进能力"),
                ("issue_closure", "问题闭环", 84, "是否能识别风险、处理异常并推动闭环"),
                ("communication_alignment", "沟通对齐", 80, "是否能在多方之间稳定传递信息并形成共识"),
                ("stability", "稳定性", 62, "看项目跨度和履历连贯性"),
            ]
        elif understanding["key"] == "procurement":
            dimensions = [
                ("industry_fit", "行业匹配", 95, "采购物料是否为机械制造原材料/零部件/工业品，而非工程建材或装饰材料；供应商资源是否在机械工贸领域"),
                ("procurement_management", "采购管理", 90, "是否能建立制度、优化流程、管控执行，具备团队管理经验"),
                ("supplier_management", "供应商管理", 88, "是否能独立开发、评估、淘汰供应商并维护战略供应商关系"),
                ("cost_control", "成本控制", 85, "是否具备询价比价、商务谈判、降本方案制定能力，能提供具体降本数据"),
                ("supply_chain_stability", "供应链保障", 80, "是否能预判风险、管控库存节奏、确保供应连续性"),
                ("team_leadership", "团队管理", 72, "是否有采购团队组建、绩效考核和人才培养经验"),
            ]
        else:
            dimensions = [
                ("role_understanding", "岗位理解", 80, "是否真正理解岗位目标和交付结果"),
                ("execution", "执行能力", 84, "是否能把任务推进到落地"),
                ("problem_solving", "问题处理", 82, "是否面对异常时有判断与处理能力"),
                ("communication", "沟通协作", 78, "是否能与客户或团队有效沟通协作"),
                ("adaptability", "场景适应", 76, "是否适应岗位要求的行业和现场场景"),
                ("stability", "稳定性", 60, "关注经历连续性和结果闭环"),
            ]

        boosted: list[CompetencyWeight] = []
        for key, label, weight, note in dimensions:
            current = weight
            current_note = note
            if key in {"travel_adaptability", "onsite_execution"} and self._mentions_any(full_text, self.FIELD_TERMS):
                current = min(100, current + 4)
                current_note = f"{note}，该 JD 对现场或出差适应性要求更强"
            if key in {"troubleshooting", "problem_solving", "issue_closure"} and self._mentions_any(full_text, ["故障", "异常", "问题处理", "维修", "排障"]):
                current = min(100, current + 4)
                current_note = f"{note}，该 JD 明确强调故障与问题闭环"
            if key in {"technical_foundation", "onsite_execution", "independent_operation"} and self._mentions_any(full_text, ["图纸", "设备原理", "调试", "安装"]):
                current = min(100, current + 4)
                current_note = f"{note}，该 JD 对技术基础和现场单兵作业要求更高"
            boosted.append(CompetencyWeight(key=key, label=label, weight=current, note=current_note))
        return boosted

    @staticmethod
    def _build_summary(job_name: str, understanding: dict[str, str], competencies: list[CompetencyWeight]) -> str:
        top_dimensions = "、".join(item.label for item in sorted(competencies, key=lambda item: item.weight, reverse=True)[:3])
        return f"{job_name} 被理解为“{understanding['name']}”，当前最关键的筛选维度是 {top_dimensions}。"

    @classmethod
    def _extract_education(cls, full_text: str) -> str | None:
        for education in cls.EDUCATION_ORDER:
            if education in full_text:
                return f"{education}及以上"
        if "学历不限" in full_text:
            return "学历不限"
        return None

    @staticmethod
    def _extract_min_experience_years(full_text: str) -> int:
        patterns = [r"(\d+)\s*年以上", r"(\d+)\s*年经验", r"(\d+)\s*-\s*\d+\s*年"]
        values: list[int] = []
        for pattern in patterns:
            for match in re.findall(pattern, full_text):
                try:
                    values.append(int(match))
                except ValueError:
                    continue
        if values:
            return min(values)
        if "应届" in full_text or "不限经验" in full_text:
            return 0
        return 0

    @staticmethod
    def _extract_age_range(full_text: str) -> tuple[int | None, int | None]:
        """Extract explicit age requirement from JD. Returns (min, max); either may be None."""
        # Range: 25-35岁 / 25岁~35岁 / 25至35岁 / 25—35岁
        range_patterns = [
            r"(\d{2})\s*[-~—至]\s*(\d{2})\s*[周]?岁",
            r"(\d{2})\s*[周]?岁\s*[-~—至]\s*(\d{2})\s*[周]?岁",
            r"年龄[：:]\s*(\d{2})\s*[-~—至]\s*(\d{2})",
        ]
        for pattern in range_patterns:
            m = re.search(pattern, full_text)
            if m:
                lo, hi = int(m.group(1)), int(m.group(2))
                if 15 <= lo <= 65 and 15 <= hi <= 65 and lo < hi:
                    return lo, hi

        # Max only: 35岁以下 / 不超过35岁
        for pattern in [r"(\d{2})\s*[周]?岁(?:及)?以下", r"不超过\s*(\d{2})\s*[周]?岁"]:
            m = re.search(pattern, full_text)
            if m:
                val = int(m.group(1))
                if 15 <= val <= 65:
                    return None, val

        # Min only: 18岁以上 (avoid matching experience years like "3年以上")
        for pattern in [r"(\d{2})\s*[周]?岁(?:及)?以上"]:
            m = re.search(pattern, full_text)
            if m:
                val = int(m.group(1))
                if 15 <= val <= 65:
                    return val, None

        return None, None

    @staticmethod
    def _sanitize_key(value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff]+", "_", value.strip().lower())
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        return cleaned or "dimension"

    @staticmethod
    def _mentions_any(text: str, keywords: list[str]) -> bool:
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


class LLMJDTranslator:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.rule_based = RuleBasedJDTranslator()

    def is_enabled(self) -> bool:
        return self.config.enabled

    def translate(self, job_id: str, job_name: str, raw_jd_text: str, notes: str | None = None) -> JobProfile:
        if not self.config.enabled:
            raise LLMTranslationError("LLM 配置未启用。")

        logger.info("LLM JD translation started for job %s model=%s", job_id, self.config.model)
        fallback_profile = self.rule_based.translate(job_id=job_id, job_name=job_name, raw_jd_text=raw_jd_text, notes=notes)
        response_text = self._call_model(self._build_prompt(job_name=job_name, raw_jd_text=raw_jd_text, notes=notes))
        payload = self._parse_payload(response_text)

        hard_constraints, downgraded_constraints = self._normalize_hard_constraints(
            payload.get("hard_constraints"),
            fallback_profile.hard_constraints.items,
            raw_jd_text,
        )
        industry_expansion = self._normalize_industry_expansion(payload.get("industry_expansion"), fallback_profile.industry_expansion.items)
        exclude_rules = self._normalize_exclude_rules(payload.get("exclude_rules"), fallback_profile.exclude_rules.items)
        private_notes = self._ensure_list(payload.get("private_notes"), fallback_profile.private_notes)
        private_notes.extend(downgraded_constraints)
        role_goal_summary = payload.get("role_goal_summary")
        private_notes = self._merge_role_goal_notes(private_notes, role_goal_summary)
        impact_summary = self._build_impact_summary(payload.get("impact_summary"), role_goal_summary, fallback_profile.impact_summary)
        competencies = self._post_process_competencies(
            self._normalize_competencies(payload.get("competencies"), fallback_profile.competencies)
        )

        job_type_note = self._normalize_job_type(payload.get("job_type_hypothesis"))

        # Parse age range from LLM; fall back to rule-based extraction if LLM skips it
        full_text = f"{job_name}\n{raw_jd_text or ''}".strip()
        rule_age_min, rule_age_max = self.rule_based._extract_age_range(full_text)
        age_min = self._parse_age_field(payload.get("age_min"), rule_age_min)
        age_max = self._parse_age_field(payload.get("age_max"), rule_age_max)

        return JobProfile(
            version_id=f"{job_id}-profile-v2-llm",
            version_name="V2 画像初稿",
            job_id=job_id,
            hard_constraints=ProfileRule(title="硬性门槛", items=hard_constraints),
            competencies=competencies,
            industry_expansion=ProfileRule(title="可迁移行业", items=industry_expansion),
            exclude_rules=ProfileRule(title="排除项", items=exclude_rules),
            private_notes=private_notes,
            impact_summary=impact_summary,
            translation_source="llm",
            translation_notes=[
                f"模型：{self.config.model}",
                f"岗位判断：{job_type_note}",
                "当前结果由 LLM 动态结构化生成，维度不是固定模板。",
            ],
            age_min=age_min,
            age_max=age_max,
        )

    def _call_model(self, prompt: str) -> str:
        trace_id = new_trace_id("jd")
        llm_trace_service.record_metadata(trace_id, kind="jd_translation")
        if self.config.api_style == "responses":
            endpoint = f"{self.config.base_url}/responses"
            body = {
                "model": self.config.model,
                "input": [
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "你负责把招聘职位名称和 JD 转成结构化岗位画像。请用简体中文输出字段内容，先理解岗位本质，再输出 JSON。",
                            }
                        ],
                    },
                    {"role": "user", "content": [{"type": "input_text", "text": prompt}]},
                ],
            }
        else:
            endpoint = f"{self.config.base_url}/chat/completions"
            body = {
                "model": self.config.model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": "你负责把招聘职位名称和 JD 转成结构化岗位画像。请用简体中文输出字段内容，先理解岗位本质，再输出 JSON。",
                    },
                    {"role": "user", "content": prompt},
                ],
            }

        log_llm_request(trace_id, endpoint, body)
        raw = self._http_post(trace_id, endpoint, body)
        log_llm_response(trace_id, raw)
        return self._extract_text_content(raw)

    @staticmethod
    def _make_session() -> http_requests.Session:
        session = http_requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
        session.mount("https://", HTTPAdapter(max_retries=retry))
        session.mount("http://", HTTPAdapter(max_retries=retry))
        return session

    def _http_post(self, trace_id: str, endpoint: str, body: dict) -> str:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
            "Connection": "close",
        }
        last_conn_exc: Exception | None = None
        for attempt in range(2):
            try:
                session = http_requests.Session()  # 每次新建，避免复用已关闭连接
                session.mount("https://", HTTPAdapter(max_retries=Retry(total=0)))
                resp = session.post(endpoint, json=body, headers=headers, timeout=self.config.timeout_seconds, verify=False)
                resp.raise_for_status()
                return resp.text
            except http_requests.exceptions.Timeout as exc:
                # 超时不重试：直接回落规则
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

    def _extract_text_content(self, raw: str) -> str:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMTranslationError("LLM 返回不是合法 JSON。") from exc

        if self.config.api_style == "responses":
            texts: list[str] = []
            for item in payload.get("output", []):
                for content in item.get("content", []):
                    text = content.get("text")
                    if text:
                        texts.append(text)
            if texts:
                return "\n".join(texts)
            raise LLMTranslationError("Responses API 没有返回文本。")

        choices = payload.get("choices", [])
        if not choices:
            raise LLMTranslationError("Chat completions 没有返回 choices。")
        text = choices[0].get("message", {}).get("content")
        if not text:
            raise LLMTranslationError("Chat completions 返回内容为空。")
        return text

    def _parse_payload(self, response_text: str) -> dict[str, Any]:
        cleaned = response_text.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not match:
                raise LLMTranslationError("LLM 返回中没有可解析的 JSON 对象。")
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise LLMTranslationError("LLM 返回 JSON 解析失败。") from exc

    @staticmethod
    def _ensure_list(value: Any, fallback: list[str]) -> list[str]:
        if isinstance(value, list):
            cleaned = [str(item).strip() for item in value if str(item).strip()]
            if cleaned:
                return cleaned
        if isinstance(value, str) and value.strip():
            tokens = re.split(r"[，,、;\n]+", value)
            cleaned = [token.strip() for token in tokens if token.strip()]
            if cleaned:
                return cleaned
        return list(fallback)

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

    def _normalize_hard_constraints(
        self,
        value: Any,
        fallback: list[str],
        raw_jd_text: str,
    ) -> tuple[list[str], list[str]]:
        items = self._ensure_list(value, fallback)
        expanded_items: list[str] = []
        for item in items:
            expanded_items.extend(self._split_constraint_fragments(item))
        filtered: list[str] = []
        downgraded: list[str] = []
        soft_markers = [
            "沟通", "服务意识", "学习能力", "抗压", "责任心", "主动性",
            "应变能力", "问题处理能力", "customer service", "communication", "problem solving",
        ]
        semi_soft_markers = ["动手能力", "上手快", "学习意愿", "配合度"]
        for item in expanded_items:
            lowered = item.lower()
            if any(marker.lower() in lowered for marker in soft_markers):
                downgraded.append(f"以下内容更适合作为软性判断，不计入硬门槛：{item}")
                continue
            if any(marker.lower() in lowered for marker in semi_soft_markers):
                downgraded.append(f"以下内容建议转为维度判断或面试追问，不计入硬门槛：{item}")
                continue
            if not self._constraint_has_text_evidence(item, raw_jd_text):
                downgraded.append(f"以下内容为模型推断但 JD 未明确写明，不计入硬门槛：{item}")
                continue
            filtered.append(item)

        filtered = self._unique(filtered)
        downgraded = self._unique(downgraded)

        if not filtered:
            filtered = list(fallback)
        return filtered, downgraded

    @staticmethod
    def _split_constraint_fragments(item: str) -> list[str]:
        text = str(item).strip().strip("。；;")
        if not text:
            return []

        raw_parts = re.split(r"[，,、；;]|并且|且|同时", text)
        parts = [part.strip() for part in raw_parts if part.strip()]

        cleaned: list[str] = []
        for part in parts:
            normalized = re.sub(r"^(具备|具有|能够|能|需|需要)", "", part).strip()
            if "图纸" in normalized and "看懂" not in normalized:
                normalized = f"看懂{normalized}"
            if normalized:
                cleaned.append(normalized)
        return cleaned or [text]

    @classmethod
    def _constraint_has_text_evidence(cls, item: str, raw_jd_text: str) -> bool:
        text = raw_jd_text or ""
        normalized_item = cls._normalize_evidence_text(item)
        normalized_text = cls._normalize_evidence_text(text)

        evidence_groups = [
            (["本科", "大专", "硕士", "博士", "中专", "学历", "专业"], ["本科", "大专", "硕士", "博士", "中专", "学历", "专业"]),
            (["年经验", "年以上", "年及以上", "年工作经验", "工作经验"], ["年", "经验"]),
            (["图纸", "技术图纸", "识图"], ["图纸", "识图"]),
            (["出差", "驻外", "现场", "外出任务"], ["出差", "驻外", "现场", "外出"]),
            (["机械设备相关基础知识", "机械设备基础", "机械基础", "设备原理"], ["机械设备", "机械基础", "设备原理"]),
            (["独立完成现场技术操作", "现场技术操作", "独立操作", "安装", "调试", "运行维护"], ["现场技术操作", "独立", "安装", "调试", "运行维护"]),
            (["资格证", "证书", "上岗证"], ["资格证", "证书", "上岗证"]),
        ]

        for item_markers, text_markers in evidence_groups:
            if any(marker in normalized_item for marker in item_markers):
                return any(marker in normalized_text for marker in text_markers)

        return normalized_item in normalized_text

    @staticmethod
    def _normalize_evidence_text(value: str) -> str:
        normalized = value.strip()
        normalized = normalized.replace("，", "").replace("。", "").replace("、", "")
        normalized = normalized.replace("；", "").replace("：", "").replace("（", "").replace("）", "")
        normalized = normalized.replace("及以上", "以上")
        normalized = re.sub(r"\s+", "", normalized)
        return normalized

    def _normalize_industry_expansion(self, value: Any, fallback: list[str]) -> list[str]:
        items = self._ensure_list(value, fallback)
        mapping = {
            "机械行业": "工业设备售后",
            "售后服务行业": "现场技术服务",
            "机械设备": "工业设备售后",
            "机械设备售后": "工业设备售后",
            "机械行业售后技术支持经验": "设备售后技术支持",
            "熟悉相关机械设备的工作原理和操作流程": "设备安装调试与维护",
        }
        normalized = [mapping.get(item, item) for item in items]
        joined = " ".join(normalized)
        if "售后" in joined and "工业设备售后" not in normalized:
            normalized.append("工业设备售后")
        if ("现场" in joined or "技术服务" in joined) and "现场技术服务" not in normalized:
            normalized.append("现场技术服务")
        if any(keyword in joined for keyword in ["安装", "调试", "维护", "运维"]) and "设备安装调试与维护" not in normalized:
            normalized.append("设备安装调试与维护")
        normalized = self._unique(normalized)
        normalized = self._dedupe_industry_expansion(normalized)
        return normalized or list(fallback)

    @staticmethod
    def _dedupe_industry_expansion(items: list[str]) -> list[str]:
        canonical_map: dict[str, str] = {}
        ordered: list[str] = []
        for item in items:
            canonical = item.replace("机械设备", "设备").replace("工业设备", "设备").strip()
            if canonical in canonical_map:
                continue
            canonical_map[canonical] = item
            ordered.append(item)
        return ordered

    def _normalize_exclude_rules(self, value: Any, fallback: list[str]) -> list[str]:
        items = self._ensure_list(value, fallback)
        cleaned: list[str] = []
        weak_terms = {"销售业绩", "成交", "回款"}
        for item in items:
            if item in weak_terms:
                continue
            cleaned.append(item)
        return cleaned or list(fallback)

    def _normalize_competencies(self, value: Any, fallback: list[CompetencyWeight]) -> list[CompetencyWeight]:
        if not isinstance(value, list):
            return [item.model_copy(deep=True) for item in fallback]

        normalized: list[CompetencyWeight] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            label = self._normalize_dimension_label(str(item.get("label") or "").strip())
            raw_key = str(item.get("key") or label).strip()
            note = str(item.get("note") or "").strip()
            definition = str(item.get("definition") or "").strip()
            if not label and not raw_key:
                continue
            try:
                weight = max(0, min(100, int(item.get("weight", 70))))
            except (TypeError, ValueError):
                weight = 70

            look_for = self._ensure_list(item.get("look_for"), [])
            avoid_signals = self._ensure_list(item.get("avoid_signals"), [])
            note_parts = [part for part in [note, definition] if part]
            if look_for:
                note_parts.append(f"重点证据：{'、'.join(look_for[:4])}")
            if avoid_signals:
                note_parts.append(f"伪匹配警报：{'、'.join(avoid_signals[:3])}")

            normalized.append(
                CompetencyWeight(
                    key=RuleBasedJDTranslator._sanitize_key(raw_key or label),
                    label=label or raw_key,
                    weight=weight,
                    note="；".join(note_parts) or "请优先根据真实动作证据判断该维度。",
                )
            )

        return normalized or [item.model_copy(deep=True) for item in fallback]

    @staticmethod
    def _normalize_dimension_label(label: str) -> str:
        mapping = {
            "fault resolution": "故障闭环",
            "problem solving": "故障闭环",
            "field execution": "现场执行",
            "technical knowledge": "技术基础",
            "technical skills": "技术基础",
            "technical understanding": "技术基础",
            "technical proficiency": "技术基础",
            "field operations": "现场执行",
            "field service": "现场执行",
            "on-site execution": "现场执行",
            "technical operation": "独立操作",
            "independent operation": "独立操作",
            "communication": "服务沟通",
            "communication service": "服务沟通",
            "customer communication": "服务沟通",
            "service communication": "服务沟通",
            "travel adaptability": "出差适应性",
            "adaptability": "出差适应性",
        }
        chinese_mapping = {
            "技术知识": "技术基础",
            "技术技能": "技术基础",
            "技术熟练度": "技术基础",
            "现场操作": "现场执行",
            "现场执行能力": "现场执行",
            "问题解决": "故障闭环",
            "问题解决能力": "故障闭环",
            "沟通能力": "服务沟通",
            "客户沟通能力": "服务沟通",
            "沟通服务": "服务沟通",
            "独立操作能力": "独立操作",
        }
        lowered = label.lower()
        return chinese_mapping.get(mapping.get(lowered, label), mapping.get(lowered, label))

    @staticmethod
    def _sort_competencies(items: list[CompetencyWeight]) -> list[CompetencyWeight]:
        priority = {
            "技术基础": 1,
            "现场执行": 2,
            "故障闭环": 3,
            "独立操作": 4,
            "服务沟通": 5,
            "出差适应性": 6,
            "稳定性": 7,
        }
        return sorted(items, key=lambda item: (priority.get(item.label, 50), -item.weight))

    def _post_process_competencies(self, items: list[CompetencyWeight]) -> list[CompetencyWeight]:
        weight_floor = {
            "技术基础": 88,
            "现场执行": 82,
            "故障闭环": 85,
            "独立操作": 78,
            "服务沟通": 72,
            "出差适应性": 65,
        }
        processed: list[CompetencyWeight] = []
        for item in items:
            updated = item.model_copy(deep=True)
            if updated.label in weight_floor:
                updated.weight = max(updated.weight, weight_floor[updated.label])
            if updated.label == "故障闭环" and "独立定位" not in updated.note:
                updated.note = f"{updated.note}；重点看是否能独立定位故障、提出方案并推动闭环。"
            if updated.label == "现场执行" and "安装" not in updated.note and "调试" not in updated.note:
                updated.note = f"{updated.note}；重点看安装、调试、巡检和现场单兵作业能力。"
            if updated.label == "独立操作" and "单独" not in updated.note:
                updated.note = f"{updated.note}；重点看无人协助时是否也能把现场任务处理下来。"
            if updated.label == "服务沟通" and "客户" not in updated.note:
                updated.note = f"{updated.note}；重点看能否把技术问题讲清楚、稳住客户并推进处理。"
            processed.append(updated)
        return self._sort_competencies(processed)

    @staticmethod
    def _parse_age_field(value: Any, fallback: int | None) -> int | None:
        """Parse an age int from LLM payload; return fallback if absent or invalid."""
        if value is None:
            return fallback
        try:
            parsed = int(value)
            if 15 <= parsed <= 65:
                return parsed
        except (TypeError, ValueError):
            pass
        return fallback

    @staticmethod
    def _normalize_job_type(value: Any) -> str:
        if isinstance(value, dict):
            name = str(value.get("name") or value.get("job_nature") or "").strip()
            reason = str(value.get("reason") or value.get("goal") or "").strip()
            if name and reason:
                return f"{name}；{reason}"
            if name:
                return name
        if isinstance(value, str) and value.strip():
            return value.strip()
        return "模型未单独返回岗位类型说明"

    @staticmethod
    def _merge_role_goal_notes(private_notes: list[str], role_goal_summary: Any) -> list[str]:
        notes = list(private_notes)
        if isinstance(role_goal_summary, dict):
            primary_goal = str(role_goal_summary.get("primary_goal") or "").strip()
            secondary_goals = [str(item).strip() for item in role_goal_summary.get("secondary_goals", []) if str(item).strip()]
            good_looks_like = [str(item).strip() for item in role_goal_summary.get("what_good_looks_like", []) if str(item).strip()]
            if primary_goal:
                notes.insert(0, f"岗位核心目标：{primary_goal}")
            if secondary_goals:
                notes.append(f"次级目标：{'、'.join(secondary_goals[:3])}")
            if good_looks_like:
                notes.append(f"理想候选人信号：{'、'.join(good_looks_like[:3])}")
        return list(dict.fromkeys([item for item in notes if item]))

    @staticmethod
    def _build_impact_summary(impact_summary: Any, role_goal_summary: Any, fallback: str) -> str:
        if isinstance(impact_summary, str) and impact_summary.strip():
            return impact_summary.strip()
        if isinstance(role_goal_summary, dict):
            primary_goal = str(role_goal_summary.get("primary_goal") or "").strip()
            good_looks_like = [str(item).strip() for item in role_goal_summary.get("what_good_looks_like", []) if str(item).strip()]
            if primary_goal and good_looks_like:
                return f"该岗位的核心目标是：{primary_goal}；筛选时应优先寻找{'、'.join(good_looks_like[:3])}这类信号。"
            if primary_goal:
                return f"该岗位的核心目标是：{primary_goal}。后续筛选会围绕这个目标寻找真正能扛事的人。"
        return fallback

    @staticmethod
    def _build_prompt(job_name: str, raw_jd_text: str, notes: str | None) -> str:
        prompt = {
            "task": "请结合职位名称和 JD，把岗位真正想招什么人理解清楚，再输出结构化岗位画像。不要套固定销售模板，也不要只做表面摘要。",
            "rules": [
                "所有返回字段内容都使用简体中文；只有 competencies.key 可以使用英文蛇形命名。",
                "先判断岗位本质是什么，再决定应该出现哪些能力维度。",
                "维度必须根据职位名称和 JD 动态生成，不能机械沿用销售岗的固定 key。",
                "显性要求和隐性要求都要抽取。",
                "把具体设备词、窄行业词适度泛化成更高层的能力或场景，但不要凭空脑补成交、回款等 JD 没写的内容。",
                "不要只复述 JD 原句，要进一步推导这个岗位真正想解决什么问题、需要候选人扛什么事。",
                "competencies 返回 4 到 8 个维度，每个维度除了 key、label、weight、note，还要尽量补充 definition、look_for、avoid_signals。",
                "如果是售后、技术支持、实施、项目、运营等岗位，就生成符合该岗位的维度，不要硬套销售维度。",
                "hard_constraints 只放客观且可直接筛掉人的硬门槛，例如学历、年限、图纸能力、现场/出差接受度，不要放沟通能力、服务意识、主动性、应变能力、问题处理能力这类软能力。",
                "如果模型想把沟通、服务意识、应变能力写进 hard_constraints，请改写到 competencies 或 private_notes 中。",
                "exclude_rules 要写成真正不合适的人群或风险简历类型，不要只写无关名词。",
                "private_notes 要体现招聘时真正该追问和该警惕的点，而不是空泛表扬。",
                "维度名称尽量使用贴近筛人的语言，例如‘现场执行’、‘故障闭环’、‘独立操作’、‘服务沟通’，少用空泛教科书词汇。",
                "请按招聘判断优先级给 weight：最先被 HR 用来筛人的维度权重最高。",
                "如果岗位是机械售后、设备售后、现场技术支持等角色，优先考虑’技术基础、现场执行、故障闭环、独立操作、服务沟通、出差适应性’这类表达。",
                "industry_expansion 优先输出可迁移岗位或能力场景，例如’工业设备售后’、’设备安装调试与维护’、’现场技术服务’，不要只输出空泛行业名。",
                "如果岗位是采购、供应链管理类：industry_expansion 必须输出’机械制造原材料/零部件采购’、’工贸一体化供应链管理’等，不要输出售后或销售类场景；exclude_rules 必须明确排除’工程/建筑/幕墙/装饰行业采购背景’，该类候选人物料类型与机械工贸完全不同，行业经验不可迁移。",
                "输出必须是 JSON 对象。",
            ],
            "json_schema": {
                "job_type_hypothesis": {
                    "name": "string",
                    "confidence": 0.0,
                    "reason": "string",
                },
                "role_goal_summary": {
                    "primary_goal": "string",
                    "secondary_goals": ["string"],
                    "what_good_looks_like": ["string"],
                },
                "age_min": "int or null — JD 明确要求的最小年龄，没写则为 null",
                "age_max": "int or null — JD 明确要求的最大年龄，没写则为 null",
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
            "output_preferences": [
                "如果岗位本质不是销售，就不要生成成交、回款、客户开拓等维度。",
                "让每个维度都能直接指导后续简历筛选和面试追问。",
                "优先让结果看起来像招聘标准，而不是岗位说明书摘要。",
                "如果是采购类岗位：competencies 第一个维度必须是'行业匹配'（weight 最高），专门判断候选人采购物料是否为机械制造/工业品，而非工程建材或装饰材料；private_notes 必须包含面试追问物料类型的具体方法。",
            ],
            "job_name": job_name,
            "notes": notes or "",
            "raw_jd_text": raw_jd_text,
        }
        return json.dumps(prompt, ensure_ascii=False, indent=2)


class HybridJDTranslator:
    def __init__(self) -> None:
        self.rule_based = RuleBasedJDTranslator()

    def translate(self, job_id: str, job_name: str, raw_jd_text: str, notes: str | None = None) -> JobProfile:
        rule_profile = self.rule_based.translate(job_id=job_id, job_name=job_name, raw_jd_text=raw_jd_text, notes=notes)
        llm = LLMJDTranslator(LLMConfig.from_env())

        if not llm.is_enabled():
            rule_profile.translation_notes.append("后台未启用 LLM 配置，当前展示的是规则引擎动态转译结果。")
            return rule_profile

        try:
            return llm.translate(job_id=job_id, job_name=job_name, raw_jd_text=raw_jd_text, notes=notes)
        except LLMTranslationError as exc:
            rule_profile.translation_notes.append(f"LLM 转译失败，已自动回退到规则动态转译：{exc}")
            return rule_profile


jd_translator = HybridJDTranslator()
