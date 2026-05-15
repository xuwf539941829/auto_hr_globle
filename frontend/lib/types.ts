export type MetricCard = {
  label: string;
  value: string;
  delta?: string | null;
};

export type CandidateCard = {
  id: string;
  name: string;
  age: number;
  education: string;
  work_years: number;
  current_company: string;
  current_position: string;
  grade: "S" | "A" | "B" | "C";
  score: number;
  summary: string;
  risk_tags: string[];
  collected: boolean;
  greeted: boolean;
  collected_at?: string | null;
  greeted_at?: string | null;
  source?: string;
  security_id?: string | null;
  lid?: string | null;
  encrypt_geek_id?: string | null;
  encrypt_job_id?: string | null;
  expect_id?: string | null;
};

export type CandidateEvidence = {
  type: "action" | "number" | "timeline" | "value" | "risk";
  title: string;
  content: string;
  impact: string;
  confidence: number;
};

export type CandidateConstraintCheck = {
  item: string;
  passed: boolean;
  reason: string;
};

export type CandidateDimensionCheck = {
  key: string;
  label: string;
  weight: number;
  score: number;
  reason: string;
};

export type ResumeWorkEntry = {
  company: string;
  position: string;
  start: string;
  end: string;
  summary: string;
};

export type ResumeEducationEntry = {
  school: string;
  degree: string;
  start: string;
  end: string;
  summary: string;
};

export type ResumeDetailSection = {
  title: string;
  items: string[];
};

export type ParsedResume = {
  work_experiences: ResumeWorkEntry[];
  education_experiences: ResumeEducationEntry[];
  action_terms: string[];
  numeric_evidence: string[];
  timeline_summary: string[];
  risk_signals: string[];
};

export type CandidateAnalysis = {
  score: number;
  grade: "S" | "A" | "B" | "C";
  pass_flag: boolean;
  summary: string;
  reasoning_summary: string;
  llm_trace_id?: string | null;
  hard_constraint_check: CandidateConstraintCheck[];
  dimension_checks: CandidateDimensionCheck[];
  score_breakdown: MetricCard[];
  evidence_items: CandidateEvidence[];
  timeline_risks: string[];
  risk_items: string[];
  value_signals: string[];
  uncertainties: string[];
  interview_focus: string[];
  recommended_actions: string[];
};

export type ScreeningBlueprint = {
  profile_version_id: string;
  hard_filters: string[];
  scoring_dimensions: CompetencyWeight[];
  industry_targets: string[];
  exclude_rules: string[];
  private_notes: string[];
  age_min?: number | null;
  age_max?: number | null;
};

export type CandidateDetail = {
  card: CandidateCard;
  timeline: string[];
  original_resume: string;
  parsed_resume?: ParsedResume | null;
  hr_resume_sections?: ResumeDetailSection[];
  screening_blueprint?: ScreeningBlueprint | null;
  analysis: CandidateAnalysis;
};

export type CompetencyWeight = {
  key: string;
  label: string;
  weight: number;
  note: string;
};

export type ProfileRule = {
  title: string;
  items: string[];
};

export type JobProfile = {
  version_id: string;
  version_name: string;
  job_id: string;
  hard_constraints: ProfileRule;
  competencies: CompetencyWeight[];
  industry_expansion: ProfileRule;
  exclude_rules: ProfileRule;
  private_notes: string[];
  impact_summary: string;
  translation_source?: "llm" | "rules";
  translation_notes?: string[];
  age_min?: number | null;
  age_max?: number | null;
};

export type JobProfileWorkbench = {
  job_id: string;
  jd_profile?: JobProfile | null;
  sample_profile?: JobProfile | null;
  final_profile?: JobProfile | null;
};

export type JobSummary = {
  id: string;
  name: string;
  city: string;
  status: string;
  raw_jd_text: string;
  current_profile: JobProfile;
};

export type JobOption = {
  id: string;
  name: string;
  city: string;
  salary_desc?: string | null;
  status: string;
  profile_version_name: string;
};

export type LLMSettings = {
  provider_label: string;
  enabled: boolean;
  has_api_key: boolean;
  api_key: string;
  base_url: string;
  model: string;
  api_style: "chat_completions" | "responses";
  timeout_seconds: number;
};

export type LLMTraceSummary = {
  trace_id: string;
  updated_at?: string;
  endpoint?: string;
  metadata?: Record<string, string>;
  has_response: boolean;
  error_count: number;
};

export type LLMTraceDetail = {
  trace_id: string;
  created_at?: string;
  updated_at?: string;
  endpoint?: string;
  metadata?: Record<string, string>;
  request?: unknown;
  response?: string;
  errors?: Array<{ at?: string; message?: string }>;
};

export type BossStatus = {
  cdp_url: string;
  cdp_reachable: boolean;
  browser_connected: boolean;
  boss_page_detected: boolean;
  login_cookie_detected: boolean;
  job_list_available: boolean;
  job_count: number;
  message: string;
};

export type DashboardSnapshot = {
  active_job_name: string;
  profile_version: string;
  metrics: MetricCard[];
  task_status: string;
  task_progress: number;
  latest_sync_at: string;
  recent_feedback: string[];
  top_candidates: CandidateCard[];
};

export type FeedbackItem = {
  id: string;
  candidate_id: string;
  candidate_name: string;
  feedback_type: "positive" | "negative" | "manual_adjust";
  reason: string;
  detail: string;
  created_at: string;
};

export type FeedbackSummary = {
  job_id: string;
  highlights: string[];
  negative_clusters: string[];
  positive_clusters: string[];
  suggested_profile_shift: string[];
  items: FeedbackItem[];
};

export type ScreeningTask = {
  id: string;
  job_id: string;
  profile_version_id: string;
  status: "pending" | "running" | "paused" | "completed" | "failed";
  progress_current: number;
  progress_total: number;
  started_at: string;
  updated_at: string;
  message: string;
  candidate_count?: number;
  auto_pass_count?: number;
  grade_counts?: Record<string, number>;
};
