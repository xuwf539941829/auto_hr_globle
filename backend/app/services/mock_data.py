from __future__ import annotations

from datetime import datetime, timedelta

from app.models.domain import (
    CandidateAnalysis,
    CandidateCard,
    CandidateConstraintCheck,
    CandidateDetail,
    CandidateDimensionCheck,
    CandidateEvidence,
    CompetencyWeight,
    DashboardSnapshot,
    FeedbackItem,
    FeedbackSummary,
    JobOption,
    JobProfile,
    JobSummary,
    MetricCard,
    ParsedResume,
    ProfileRule,
    ResumeWorkEntry,
    ScreeningBlueprint,
    ScreeningTask,
)


def build_job_profile(
    job_id: str = "job-001",
    version_id: str = "profile-v3-final",
    version_name: str = "V3 最终执行画像",
) -> JobProfile:
    return JobProfile(
        version_id=version_id,
        version_name=version_name,
        job_id=job_id,
        hard_constraints=ProfileRule(
            title="硬性门槛",
            items=["大专及以上", "3年以上相关经验", "接受出差或现场推进"],
        ),
        competencies=[
            CompetencyWeight(key="potential", label="潜力/野心", weight=86, note="允许年限略低，但必须有主动开拓和拿结果的味道。"),
            CompetencyWeight(key="complex_sales", label="复杂销售", weight=92, note="重点看长决策链、高客单价和回款闭环。"),
            CompetencyWeight(key="bd", label="大 B 端开拓", weight=90, note="优先看独立开发客户，而不是纯维护。"),
            CompetencyWeight(key="resilience", label="抗压/皮实", weight=82, note="矿山、工厂、驻外、现场推进经历加分。"),
            CompetencyWeight(key="stability", label="稳定性", weight=64, note="不过度惩罚合理跳槽，但要看每段是否有结果闭环。"),
            CompetencyWeight(key="migration", label="跨行业迁移力", weight=80, note="工业设备、工程机械、重工设备背景可迁移。"),
        ],
        industry_expansion=ProfileRule(
            title="可迁移行业",
            items=["石材机械", "矿山设备", "工程机械", "起重设备", "工业设备"],
        ),
        exclude_rules=ProfileRule(
            title="排除项",
            items=[
                "纯快消销售",
                "只有内勤支持且没有独立成交",
                "频繁短期跳槽且没有结果证明",
                "只做小单零售，没有复杂决策链经验",
            ],
        ),
        private_notes=[
            "优先考虑能打硬仗、能扛现场的人。",
            "允许跨行，但必须看到高客单价动作证据。",
            "做过工厂、矿山、驻外推进的人优先。",
        ],
        impact_summary="这份画像已经合并 JD 转译、优秀样本分析和 HR 校准结果，后续筛选按它执行。",
        translation_source="llm",
        translation_notes=[
            "已融合 JD 初稿、样本学习和 HR 微调。",
            "这是一份用于筛选的执行画像，不只是展示文案。",
        ],
    )


def build_jobs() -> list[JobOption]:
    return [
        JobOption(id="job-001", name="工业设备大客户销售", city="泉州", salary_desc="15-25K", status="active", profile_version_name="V3 最终执行画像"),
        JobOption(id="job-002", name="海外渠道销售", city="厦门", salary_desc="12-18K", status="draft", profile_version_name="V1 画像初稿"),
        JobOption(id="job-003", name="矿山设备区域经理", city="长沙", salary_desc="18-28K", status="calibrating", profile_version_name="V2 人工校准中"),
    ]


def build_job_options() -> list[JobOption]:
    return build_jobs()


def build_screening_blueprint(profile: JobProfile) -> ScreeningBlueprint:
    return ScreeningBlueprint(
        profile_version_id=profile.version_id,
        hard_filters=list(profile.hard_constraints.items),
        scoring_dimensions=[item.model_copy(deep=True) for item in profile.competencies],
        industry_targets=list(profile.industry_expansion.items),
        exclude_rules=list(profile.exclude_rules.items),
        private_notes=list(profile.private_notes),
    )


def build_parsed_resume(candidate_id: str) -> ParsedResume:
    if candidate_id == "cand-001":
        return ParsedResume(
            work_experiences=[
                ResumeWorkEntry(company="华东重工设备", position="区域销售经理", start="2023", end="至今", summary="矿山机械与现场项目推进"),
                ResumeWorkEntry(company="远虎机械", position="大客户销售", start="2020", end="2023", summary="起重设备销售"),
                ResumeWorkEntry(company="金石装备", position="销售工程师", start="2018", end="2020", summary="建材设备销售"),
            ],
            education_experiences=[],
            action_terms=["客户开发", "开拓", "拜访", "签约", "回款", "项目", "交付"],
            numeric_evidence=["50万美金", "6个月", "3家"],
            timeline_summary=[
                "2023-至今 华东重工设备 | 区域销售经理 | 矿山机械",
                "2020-2023 远虎机械 | 大客户销售 | 起重设备",
                "2018-2020 金石装备 | 销售工程师 | 建材设备",
            ],
            risk_signals=["检测到多段工作经历，面试时需要核查每次变动原因。"],
        )

    if candidate_id == "cand-002":
        return ParsedResume(
            work_experiences=[
                ResumeWorkEntry(company="山岳工程机械", position="客户开发主管", start="2022", end="至今", summary="挖机销售"),
                ResumeWorkEntry(company="中跃机电", position="销售代表", start="2020", end="2022", summary="工业配件"),
            ],
            education_experiences=[],
            action_terms=["开拓", "陌拜", "拜访", "客户开发", "现场"],
            numeric_evidence=["12家"],
            timeline_summary=[
                "2022-至今 山岳工程机械 | 客户开发主管 | 挖机销售",
                "2020-2022 中跃机电 | 销售代表 | 工业配件",
            ],
            risk_signals=[],
        )

    return ParsedResume(
        work_experiences=[
            ResumeWorkEntry(company="建材贸易公司", position="销售主管", start="2021", end="至今", summary="建材贸易销售"),
            ResumeWorkEntry(company="家居零售集团", position="区域经理", start="2018", end="2021", summary="零售渠道"),
        ],
        education_experiences=[],
        action_terms=["负责", "参与"],
        numeric_evidence=[],
        timeline_summary=[
            "2021-至今 建材贸易公司 | 销售主管 | 建材贸易",
            "2018-2021 家居零售集团 | 区域经理 | 零售渠道",
        ],
        risk_signals=["简历里责任描述较多，但缺少明确数字证明。"],
    )


def build_analysis(score: int, grade: str, summary: str, candidate_id: str) -> CandidateAnalysis:
    if candidate_id == "cand-001":
        return CandidateAnalysis(
            score=score,
            grade=grade,  # type: ignore[arg-type]
            pass_flag=True,
            summary=summary,
            reasoning_summary="候选人具备高客单价设备动作证据、现场推进经验和明确的跨行业迁移逻辑。",
            hard_constraint_check=[
                CandidateConstraintCheck(item="大专及以上", passed=True, reason="学历符合要求。"),
                CandidateConstraintCheck(item="3年以上相关经验", passed=True, reason="累计相关经验超过 6 年。"),
                CandidateConstraintCheck(item="接受出差或现场推进", passed=True, reason="矿山、工厂和现场场景反复出现。"),
            ],
            dimension_checks=[
                CandidateDimensionCheck(key="potential", label="潜力/野心", weight=86, score=88, reason="主动开发信号强。"),
                CandidateDimensionCheck(key="complex_sales", label="复杂销售", weight=92, score=93, reason="有长决策周期和回款闭环证据。"),
                CandidateDimensionCheck(key="bd", label="大 B 端开拓", weight=90, score=91, reason="独立开发客户痕迹明显。"),
                CandidateDimensionCheck(key="resilience", label="抗压/皮实", weight=82, score=86, reason="矿山和现场环境信号充足。"),
                CandidateDimensionCheck(key="stability", label="稳定性", weight=64, score=62, reason="有几次流动，但每段都有结果。"),
                CandidateDimensionCheck(key="migration", label="跨行业迁移力", weight=80, score=88, reason="重工设备背景迁移顺畅。"),
            ],
            score_breakdown=[
                MetricCard(label="硬性门槛", value="19/20"),
                MetricCard(label="核心能力加权", value="28/30"),
                MetricCard(label="行业迁移", value="13/15"),
                MetricCard(label="动作与数字证据", value="14/15"),
                MetricCard(label="抗压/皮实", value="8/10"),
                MetricCard(label="稳定性", value="7/10"),
            ],
            evidence_items=[
                CandidateEvidence(type="action", title="独立客户开发", content="通过拜访、转介绍和驻点推进拿下矿山客户。", impact="+大 B 端开拓", confidence=0.92),
                CandidateEvidence(type="number", title="高客单价首单", content="首单成交 50 万美金，决策周期约 6 个月。", impact="+复杂销售", confidence=0.94),
                CandidateEvidence(type="value", title="现场交付推进", content="长期跟进安装、交付和现场协调。", impact="+抗压/皮实", confidence=0.83),
            ],
            timeline_risks=["近几年有数次流动，面试时要核查动机。"],
            risk_items=["部分结果来自自述，面试中仍需核查具体项目。"],
            value_signals=["能适应矿山和工厂环境。", "接受出差与现场推进。"],
            uncertainties=["需要确认其是否亲自主导了全部招投标流程。"],
            interview_focus=["追问最大项目的完整推进路径。", "核查谁推动了最终回款。"],
            recommended_actions=["collect", "greet", "push"],
        )

    if candidate_id == "cand-002":
        return CandidateAnalysis(
            score=score,
            grade=grade,  # type: ignore[arg-type]
            pass_flag=True,
            summary=summary,
            reasoning_summary="候选人的主动开拓和现场推进味道不错，但大单闭环证据还不够强。",
            hard_constraint_check=[
                CandidateConstraintCheck(item="大专及以上", passed=True, reason="学历符合要求。"),
                CandidateConstraintCheck(item="3年以上相关经验", passed=True, reason="累计经验约 4 年。"),
                CandidateConstraintCheck(item="接受出差或现场推进", passed=True, reason="简历中出现现场和客户拜访信号。"),
            ],
            dimension_checks=[
                CandidateDimensionCheck(key="potential", label="潜力/野心", weight=86, score=84, reason="主动开拓信号明显。"),
                CandidateDimensionCheck(key="complex_sales", label="复杂销售", weight=92, score=68, reason="大单闭环证据还不够。"),
                CandidateDimensionCheck(key="bd", label="大 B 端开拓", weight=90, score=82, reason="开拓和陌拜动作较多。"),
                CandidateDimensionCheck(key="resilience", label="抗压/皮实", weight=82, score=78, reason="现场推进痕迹存在。"),
                CandidateDimensionCheck(key="stability", label="稳定性", weight=64, score=86, reason="履历连续度尚可。"),
                CandidateDimensionCheck(key="migration", label="跨行业迁移力", weight=80, score=85, reason="工程机械背景可迁移。"),
            ],
            score_breakdown=[
                MetricCard(label="硬性门槛", value="19/20"),
                MetricCard(label="核心能力加权", value="24/30"),
                MetricCard(label="行业迁移", value="14/15"),
                MetricCard(label="动作与数字证据", value="11/15"),
                MetricCard(label="抗压/皮实", value="8/10"),
                MetricCard(label="稳定性", value="10/10"),
            ],
            evidence_items=[
                CandidateEvidence(type="action", title="主动开拓风格", content="简历里有陌拜、拜访和客户开发动作。", impact="+大 B 端开拓", confidence=0.82),
            ],
            timeline_risks=[],
            risk_items=["大单金额和回款闭环证据仍然偏少。"],
            value_signals=["主动意愿较强。", "看起来能适应现场环境。"],
            uncertainties=["需要确认是否真正负责过长决策链大客户。"],
            interview_focus=["追问开过的最大客户。", "确认订单金额和回款路径。"],
            recommended_actions=["collect", "push"],
        )

    return CandidateAnalysis(
        score=score,
        grade=grade,  # type: ignore[arg-type]
        pass_flag=False,
        summary=summary,
        reasoning_summary="候选人年限够，但简历更像维护型或零售型销售，不像复杂工业设备成交。",
        hard_constraint_check=[
            CandidateConstraintCheck(item="大专及以上", passed=True, reason="学历可接受。"),
            CandidateConstraintCheck(item="3年以上相关经验", passed=True, reason="年限超过门槛。"),
            CandidateConstraintCheck(item="接受出差或现场推进", passed=False, reason="没有看到足够强的现场或出差信号。"),
        ],
        dimension_checks=[
            CandidateDimensionCheck(key="potential", label="潜力/野心", weight=86, score=55, reason="缺少主动开拓证据。"),
            CandidateDimensionCheck(key="complex_sales", label="复杂销售", weight=92, score=48, reason="没有明显的长决策链项目证据。"),
            CandidateDimensionCheck(key="bd", label="大 B 端开拓", weight=90, score=46, reason="更偏维护和支持，不像独立开拓。"),
            CandidateDimensionCheck(key="resilience", label="抗压/皮实", weight=82, score=42, reason="缺少工厂、矿山或现场环境信号。"),
            CandidateDimensionCheck(key="stability", label="稳定性", weight=64, score=84, reason="履历连续性尚可。"),
            CandidateDimensionCheck(key="migration", label="跨行业迁移力", weight=80, score=52, reason="行业邻接性较弱。"),
        ],
        score_breakdown=[
            MetricCard(label="硬性门槛", value="13/20"),
            MetricCard(label="核心能力加权", value="18/30"),
            MetricCard(label="行业迁移", value="7/15"),
            MetricCard(label="动作与数字证据", value="5/15"),
            MetricCard(label="抗压/皮实", value="4/10"),
            MetricCard(label="稳定性", value="9/10"),
        ],
        evidence_items=[
            CandidateEvidence(type="risk", title="证据偏薄", content="简历用语偏虚，缺少可量化结果。", impact="-证据密度", confidence=0.78),
        ],
        timeline_risks=["没有明显断档，但动作证据仍然较弱。"],
        risk_items=["简历更像维护型或零售型销售。", "没有清晰的金额或项目级别证明。"],
        value_signals=[],
        uncertainties=["需要确认是否曾经独立拿下过工业类订单。"],
        interview_focus=["追问是否从零开发过客户。", "追问最大订单和真实角色。"],
        recommended_actions=[],
    )


def build_candidates() -> list[CandidateDetail]:
    profile = build_job_profile()
    blueprint = build_screening_blueprint(profile)
    return [
        CandidateDetail(
            card=CandidateCard(
                id="cand-001",
                name="李嘉",
                age=31,
                education="大专",
                work_years=6,
                current_company="华东重工设备",
                current_position="区域销售经理",
                grade="S",
                score=92,
                summary="高客单价工业设备证据扎实，跨行业迁移逻辑顺。",
                risk_tags=["需核查流动原因"],
                collected=True,
                greeted=True,
            ),
            timeline=[
                "2023-至今 华东重工设备 | 区域销售经理 | 矿山机械",
                "2020-2023 远虎机械 | 大客户销售 | 起重设备",
                "2018-2020 金石装备 | 销售工程师 | 建材设备",
            ],
            original_resume="6 年工业设备销售经验，长期跑矿山和工厂场景，拿过多笔高客单价订单。",
            parsed_resume=build_parsed_resume("cand-001"),
            screening_blueprint=blueprint,
            analysis=build_analysis(92, "S", "证据密度高，值得立刻进入收藏和打招呼流程。", "cand-001"),
        ),
        CandidateDetail(
            card=CandidateCard(
                id="cand-002",
                name="周琳",
                age=28,
                education="本科",
                work_years=4,
                current_company="山岳工程机械",
                current_position="客户开发主管",
                grade="A",
                score=86,
                summary="主动开拓味道对，但大单闭环证据还需补强。",
                risk_tags=["大单证据偏少"],
                collected=True,
                greeted=False,
            ),
            timeline=[
                "2022-至今 山岳工程机械 | 客户开发主管 | 挖机销售",
                "2020-2022 中跃机电 | 销售代表 | 工业配件",
            ],
            original_resume="工程机械和工业配件销售背景，擅长客户开发、拜访和现场推进。",
            parsed_resume=build_parsed_resume("cand-002"),
            screening_blueprint=blueprint,
            analysis=build_analysis(86, "A", "值得继续跟进，建议先收藏并追问关键证据。", "cand-002"),
        ),
        CandidateDetail(
            card=CandidateCard(
                id="cand-003",
                name="陈松",
                age=34,
                education="本科",
                work_years=8,
                current_company="建材贸易公司",
                current_position="销售主管",
                grade="B",
                score=74,
                summary="年限够，但动作证据弱，更像维护型销售。",
                risk_tags=["动作证据弱", "需 HR 复核"],
                collected=False,
                greeted=False,
            ),
            timeline=[
                "2021-至今 建材贸易公司 | 销售主管 | 建材贸易",
                "2018-2021 家居零售集团 | 区域经理 | 零售渠道",
            ],
            original_resume="多年销售管理经验，主要负责团队协调、客户维护和目标达成。",
            parsed_resume=build_parsed_resume("cand-003"),
            screening_blueprint=blueprint,
            analysis=build_analysis(74, "B", "可以保留给 HR 复核，但不建议自动推进。", "cand-003"),
        ),
    ]


class InMemoryStore:
    def __init__(self) -> None:
        self.profile = build_job_profile()
        self.job = JobSummary(
            id="job-001",
            name="工业设备大客户销售",
            city="泉州",
            status="active",
            raw_jd_text="负责工业设备大客户开发，销售高客单价设备，要求能跑矿山和工厂场景，能做长决策周期项目推进。",
            current_profile=self.profile,
        )
        self.candidates = build_candidates()
        now = datetime.now()
        self.task = ScreeningTask(
            id="task-001",
            job_id=self.job.id,
            profile_version_id=self.profile.version_id,
            status="running",
            progress_current=38,
            progress_total=120,
            started_at=now - timedelta(minutes=22),
            updated_at=now,
            message="正在扫描 Boss 候选人并执行证据审计。",
        )
        self.feedback_items = [
            FeedbackItem(
                id="fb-001",
                candidate_id="cand-003",
                candidate_name="陈松",
                feedback_type="negative",
                reason="太稳，冲劲不够",
                detail="更像维护型销售，缺少主动开拓和拿结果的味道。",
                created_at=now - timedelta(hours=3),
            ),
            FeedbackItem(
                id="fb-002",
                candidate_id="cand-001",
                candidate_name="李嘉",
                feedback_type="positive",
                reason="这类人很对味",
                detail="跨行业可以接受，但必须有硬动作和现场推进能力。",
                created_at=now - timedelta(hours=1, minutes=15),
            ),
        ]

    def build_dashboard(self) -> DashboardSnapshot:
        return DashboardSnapshot(
            active_job_name=self.job.name,
            profile_version=self.profile.version_name,
            metrics=[
                MetricCard(label="今日抓取", value="128", delta="+18"),
                MetricCard(label="已分析", value="84", delta="+12"),
                MetricCard(label="S 级", value="6", delta="+2"),
                MetricCard(label="A 级", value="14", delta="+4"),
                MetricCard(label="已收藏", value="17", delta="+5"),
                MetricCard(label="已打招呼", value="9", delta="+3"),
            ],
            task_status=self.task.status,
            task_progress=round(self.task.progress_current / self.task.progress_total * 100),
            latest_sync_at=self.task.updated_at.strftime("%Y-%m-%d %H:%M"),
            recent_feedback=[item.reason for item in self.feedback_items],
            top_candidates=[detail.card for detail in self.candidates[:2]],
        )

    def build_feedback_summary(self) -> FeedbackSummary:
        return FeedbackSummary(
            job_id=self.job.id,
            highlights=[
                "系统明显更偏好有矿山、工厂、驻外经历的人。",
                "稳定但动作证据弱的候选人正在被降权。",
            ],
            negative_clusters=["太稳，冲劲不够", "缺少主动开拓", "偏零售或维护型销售"],
            positive_clusters=["能打现场", "有高客单价证据", "跨行业但能拿结果"],
            suggested_profile_shift=[
                "把潜力/野心权重再提高一点。",
                "稳定性保持中位，不要过度惩罚合理跳槽。",
            ],
            items=self.feedback_items,
        )


_store: InMemoryStore | None = None


def get_store() -> InMemoryStore:
    global _store
    if _store is None:
        _store = InMemoryStore()
    return _store


class LazyStoreProxy:
    def __getattr__(self, item: str):
        return getattr(get_store(), item)

    def __setattr__(self, key: str, value):
        if key.startswith("_"):
            object.__setattr__(self, key, value)
            return
        setattr(get_store(), key, value)


store = LazyStoreProxy()
