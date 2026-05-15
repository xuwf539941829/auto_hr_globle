import type {
  CandidateDetail,
  DashboardSnapshot,
  FeedbackSummary,
  JobOption,
  JobSummary,
  ScreeningTask
} from "@/lib/types";

export const mockDashboard: DashboardSnapshot = {
  active_job_name: "工业设备大客户销售",
  profile_version: "V3 最终执行画像",
  metrics: [
    { label: "今日抓取", value: "128", delta: "+18" },
    { label: "已分析", value: "84", delta: "+12" },
    { label: "S 级", value: "6", delta: "+2" },
    { label: "A 级", value: "14", delta: "+4" },
    { label: "已收藏", value: "17", delta: "+5" },
    { label: "已打招呼", value: "9", delta: "+3" }
  ],
  task_status: "running",
  task_progress: 32,
  latest_sync_at: "2026-04-22 10:20",
  recent_feedback: ["太稳，冲劲不够", "这类人很对味"],
  top_candidates: []
};

export const mockJob: JobSummary = {
  id: "job-001",
  name: "工业设备大客户销售",
  city: "泉州",
  status: "active",
  raw_jd_text: "负责工业设备大客户开发，销售高客单价设备，要求能跑矿山和工厂场景，能做长决策周期项目推进。",
  current_profile: {
    version_id: "profile-v3-final",
    version_name: "V3 最终执行画像",
    job_id: "job-001",
    hard_constraints: {
      title: "硬性门槛",
      items: ["大专及以上", "3年以上相关经验", "接受出差或现场推进"]
    },
    competencies: [
      { key: "potential", label: "潜力/野心", weight: 86, note: "允许年限略低，但必须有主动开拓和拿结果的味道。" },
      { key: "complex_sales", label: "复杂销售", weight: 92, note: "重点看长决策链、高客单价和回款闭环。" },
      { key: "bd", label: "大 B 端开拓", weight: 90, note: "优先看独立开发客户，而不是纯维护。" },
      { key: "resilience", label: "抗压/皮实", weight: 82, note: "矿山、工厂、驻外、现场推进经历加分。" },
      { key: "stability", label: "稳定性", weight: 64, note: "不过度惩罚合理跳槽，但要看每段是否有结果闭环。" },
      { key: "migration", label: "跨行业迁移力", weight: 80, note: "工业设备、工程机械、重工设备背景可迁移。" }
    ],
    industry_expansion: {
      title: "可迁移行业",
      items: ["石材机械", "矿山设备", "工程机械", "起重设备", "工业设备"]
    },
    exclude_rules: {
      title: "排除项",
      items: ["纯快消销售", "只有内勤支持且没有独立成交", "频繁短期跳槽且没有结果证明", "只做小单零售，没有复杂决策链经验"]
    },
    private_notes: ["优先考虑能打硬仗、能扛现场的人。", "允许跨行，但必须看到高客单价动作证据。", "做过工厂、矿山、驻外推进的人优先。"],
    impact_summary: "这份画像已经合并 JD 转译、优秀样本分析和 HR 校准结果，后续筛选按它执行。",
    translation_source: "llm",
    translation_notes: ["已融合 JD 初稿、样本学习和 HR 微调。", "这是一份用于筛选的执行画像，不只是展示文案。"]
  }
};

export const mockJobs: JobOption[] = [
  { id: "job-001", name: "工业设备大客户销售", city: "泉州", salary_desc: "15-25K", status: "active", profile_version_name: "V3 最终执行画像" },
  { id: "job-002", name: "海外渠道销售", city: "厦门", salary_desc: "12-18K", status: "draft", profile_version_name: "V1 画像初稿" },
  { id: "job-003", name: "矿山设备区域经理", city: "长沙", salary_desc: "18-28K", status: "calibrating", profile_version_name: "V2 人工校准中" }
];

export const mockCandidates: CandidateDetail[] = [
  {
    card: {
      id: "cand-001",
      name: "李嘉",
      age: 31,
      education: "大专",
      work_years: 6,
      current_company: "华东重工设备",
      current_position: "区域销售经理",
      grade: "S",
      score: 92,
      summary: "高客单价工业设备证据扎实，跨行业迁移逻辑顺。",
      risk_tags: ["需核查流动原因"],
      collected: true,
      greeted: true
    },
    timeline: [
      "2023-至今 华东重工设备 | 区域销售经理 | 矿山机械",
      "2020-2023 远虎机械 | 大客户销售 | 起重设备",
      "2018-2020 金石装备 | 销售工程师 | 建材设备"
    ],
    original_resume: "6 年工业设备销售经验，长期跑矿山和工厂场景，拿过多笔高客单价订单。",
    parsed_resume: {
      work_experiences: [
        { company: "华东重工设备", position: "区域销售经理", start: "2023", end: "至今", summary: "矿山机械与现场项目推进" },
        { company: "远虎机械", position: "大客户销售", start: "2020", end: "2023", summary: "起重设备销售" }
      ],
      education_experiences: [],
      action_terms: ["客户开发", "开拓", "拜访", "签约", "回款", "交付"],
      numeric_evidence: ["50万美金", "6个月", "3家"],
      timeline_summary: [
        "2023-至今 华东重工设备 | 区域销售经理 | 矿山机械",
        "2020-2023 远虎机械 | 大客户销售 | 起重设备"
      ],
      risk_signals: ["检测到多段工作经历，面试时需要核查每次变动原因。"]
    },
    screening_blueprint: {
      profile_version_id: "profile-v3-final",
      hard_filters: ["大专及以上", "3年以上相关经验", "接受出差或现场推进"],
      scoring_dimensions: mockJob.current_profile.competencies,
      industry_targets: mockJob.current_profile.industry_expansion.items,
      exclude_rules: mockJob.current_profile.exclude_rules.items,
      private_notes: mockJob.current_profile.private_notes
    },
    analysis: {
      score: 92,
      grade: "S",
      pass_flag: true,
      summary: "证据密度高，值得立刻进入收藏和打招呼流程。",
      reasoning_summary: "候选人具备高客单价设备动作证据、现场推进经验和明确的跨行业迁移逻辑。",
      hard_constraint_check: [
        { item: "大专及以上", passed: true, reason: "学历符合要求。" },
        { item: "3年以上相关经验", passed: true, reason: "累计相关经验超过 6 年。" },
        { item: "接受出差或现场推进", passed: true, reason: "矿山、工厂和现场场景反复出现。" }
      ],
      dimension_checks: [
        { key: "potential", label: "潜力/野心", weight: 86, score: 88, reason: "主动开发信号强。" },
        { key: "complex_sales", label: "复杂销售", weight: 92, score: 93, reason: "有长决策周期和回款闭环证据。" },
        { key: "bd", label: "大 B 端开拓", weight: 90, score: 91, reason: "独立开发客户痕迹明显。" }
      ],
      score_breakdown: [
        { label: "硬性门槛", value: "19/20" },
        { label: "核心能力加权", value: "28/30" }
      ],
      evidence_items: [
        { type: "action", title: "独立客户开发", content: "通过拜访、转介绍和驻点推进拿下矿山客户。", impact: "+大 B 端开拓", confidence: 0.92 },
        { type: "number", title: "高客单价首单", content: "首单成交 50 万美金，决策周期约 6 个月。", impact: "+复杂销售", confidence: 0.94 }
      ],
      timeline_risks: ["近几年有数次流动，面试时要核查动机。"],
      risk_items: ["部分结果来自自述，面试中仍需核查具体项目。"],
      value_signals: ["能适应矿山和工厂环境。"],
      uncertainties: ["需要确认其是否亲自主导了全部招投标流程。"],
      interview_focus: ["追问最大项目的完整推进路径。"],
      recommended_actions: ["collect", "greet", "push"]
    }
  },
  {
    card: {
      id: "cand-002",
      name: "周琳",
      age: 28,
      education: "本科",
      work_years: 4,
      current_company: "山岳工程机械",
      current_position: "客户开发主管",
      grade: "A",
      score: 86,
      summary: "主动开拓味道对，但大单闭环证据还需补强。",
      risk_tags: ["大单证据偏少"],
      collected: true,
      greeted: false
    },
    timeline: [
      "2022-至今 山岳工程机械 | 客户开发主管 | 挖机销售",
      "2020-2022 中跃机电 | 销售代表 | 工业配件"
    ],
    original_resume: "工程机械和工业配件销售背景，擅长客户开发、拜访和现场推进。",
    parsed_resume: {
      work_experiences: [{ company: "山岳工程机械", position: "客户开发主管", start: "2022", end: "至今", summary: "挖机销售" }],
      education_experiences: [],
      action_terms: ["开拓", "陌拜", "拜访", "客户开发", "现场"],
      numeric_evidence: ["12家"],
      timeline_summary: ["2022-至今 山岳工程机械 | 客户开发主管 | 挖机销售"],
      risk_signals: []
    },
    screening_blueprint: {
      profile_version_id: "profile-v3-final",
      hard_filters: ["大专及以上", "3年以上相关经验", "接受出差或现场推进"],
      scoring_dimensions: mockJob.current_profile.competencies,
      industry_targets: mockJob.current_profile.industry_expansion.items,
      exclude_rules: mockJob.current_profile.exclude_rules.items,
      private_notes: mockJob.current_profile.private_notes
    },
    analysis: {
      score: 86,
      grade: "A",
      pass_flag: true,
      summary: "值得继续跟进，建议先收藏并追问关键证据。",
      reasoning_summary: "候选人的主动开拓和现场推进味道不错，但大单闭环证据还不够强。",
      hard_constraint_check: [
        { item: "大专及以上", passed: true, reason: "学历符合要求。" },
        { item: "3年以上相关经验", passed: true, reason: "累计经验约 4 年。" },
        { item: "接受出差或现场推进", passed: true, reason: "简历中出现现场和客户拜访信号。" }
      ],
      dimension_checks: [
        { key: "potential", label: "潜力/野心", weight: 86, score: 84, reason: "主动开拓信号明显。" },
        { key: "complex_sales", label: "复杂销售", weight: 92, score: 68, reason: "大单闭环证据还不够。" },
        { key: "bd", label: "大 B 端开拓", weight: 90, score: 82, reason: "开拓和陌拜动作较多。" }
      ],
      score_breakdown: [
        { label: "硬性门槛", value: "19/20" },
        { label: "核心能力加权", value: "24/30" }
      ],
      evidence_items: [
        { type: "action", title: "主动开拓风格", content: "简历里有陌拜、拜访和客户开发动作。", impact: "+大 B 端开拓", confidence: 0.82 }
      ],
      timeline_risks: [],
      risk_items: ["大单金额和回款闭环证据仍然偏少。"],
      value_signals: ["主动意愿较强。"],
      uncertainties: ["需要确认是否真正负责过长决策链大客户。"],
      interview_focus: ["追问开过的最大客户。"],
      recommended_actions: ["collect", "push"]
    }
  }
];

export const mockTask: ScreeningTask = {
  id: "task-001",
  job_id: "job-001",
  profile_version_id: "profile-v3-final",
  status: "running",
  progress_current: 38,
  progress_total: 120,
  started_at: "2026-04-22T09:58:00",
  updated_at: "2026-04-22T10:20:00",
  message: "正在扫描 Boss 候选人并执行证据审计。"
};

export const mockFeedback: FeedbackSummary = {
  job_id: "job-001",
  highlights: ["系统明显更偏好有矿山、工厂、驻外经历的人。", "稳定但动作证据弱的候选人正在被降权。"],
  negative_clusters: ["太稳，冲劲不够", "缺少主动开拓", "偏零售或维护型销售"],
  positive_clusters: ["能打现场", "有高客单价证据", "跨行业但能拿结果"],
  suggested_profile_shift: ["把潜力/野心权重再提高一点。", "稳定性保持中位，不要过度惩罚合理跳槽。"],
  items: [
    {
      id: "fb-001",
      candidate_id: "cand-003",
      candidate_name: "陈松",
      feedback_type: "negative",
      reason: "太稳，冲劲不够",
      detail: "更像维护型销售，缺少主动开拓和拿结果的味道。",
      created_at: "2026-04-22T07:20:00"
    }
  ]
};
