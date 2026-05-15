"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { CandidateScreeningBoard } from "@/components/candidate-screening-board";
import { EditableFinalProfile } from "@/components/editable-final-profile";
import type { CandidateDetail, JobOption, JobProfile, JobProfileWorkbench, JobSummary, ScreeningBlueprint, ScreeningTask } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";

const SOURCE_LABEL: Record<NonNullable<JobProfile["translation_source"]>, string> = {
  llm: "LLM 转译",
  rules: "规则兜底"
};

type WorkflowStep = "jd" | "sample" | "final" | "screening";

const TASK_STATUS_LABEL: Record<ScreeningTask["status"], string> = {
  pending: "待开始",
  running: "执行中",
  paused: "已暂停",
  completed: "已完成",
  failed: "失败"
};

function getTaskStatusLabel(task: ScreeningTask | null | undefined) {
  if (!task) {
    return "未创建";
  }
  if (task.status === "failed" && task.message?.includes("后端重启已中断")) {
    return "已中断";
  }
  return TASK_STATUS_LABEL[task.status];
}

function ensureProfile(profile: JobProfile | null | undefined): JobProfile | null {
  if (!profile) {
    return null;
  }

  return {
    ...profile,
    translation_source: profile.translation_source ?? "rules",
    translation_notes: profile.translation_notes ?? [],
    competencies: profile.competencies ?? [],
    hard_constraints: profile.hard_constraints ?? { title: "硬性门槛", items: [] },
    industry_expansion: profile.industry_expansion ?? { title: "可迁移场景", items: [] },
    exclude_rules: profile.exclude_rules ?? { title: "排除项", items: [] },
    private_notes: profile.private_notes ?? []
  };
}

function emptyWorkbench(jobId: string): JobProfileWorkbench {
  return {
    job_id: jobId,
    jd_profile: null,
    sample_profile: null,
    final_profile: null
  };
}

function profileToBlueprint(profile: JobProfile | null | undefined): ScreeningBlueprint | null {
  if (!profile) {
    return null;
  }

  return {
    profile_version_id: profile.version_id,
    hard_filters: profile.hard_constraints.items,
    scoring_dimensions: profile.competencies,
    industry_targets: profile.industry_expansion.items,
    exclude_rules: profile.exclude_rules.items,
    private_notes: profile.private_notes
  };
}

function fallbackJob(option: JobOption | undefined, jobId: string): JobSummary {
  return {
    id: option?.id ?? jobId,
    name: option?.name ?? "未命名职位",
    city: option?.city ?? "未设置城市",
    status: option?.status ?? "draft",
    raw_jd_text: "",
    current_profile: {
      version_id: `${jobId}-profile-empty`,
      version_name: "待生成画像",
      job_id: jobId,
      hard_constraints: { title: "硬性门槛", items: [] },
      competencies: [],
      industry_expansion: { title: "可迁移场景", items: [] },
      exclude_rules: { title: "排除项", items: [] },
      private_notes: [],
      impact_summary: "当前还没有生成岗位画像。",
      translation_source: "rules",
      translation_notes: []
    }
  };
}

function normalizeJobMetaText(value: string | null | undefined) {
  const text = (value ?? "").trim();
  if (!text) {
    return "";
  }
  const normalized = text.toLowerCase();
  if (normalized === "unknown" || normalized === "unknown city") {
    return "";
  }
  if (normalized === "no profile yet") {
    return "";
  }
  return text;
}

function getJobCardMeta(item: JobOption) {
  const city = normalizeJobMetaText(item.city);
  const salary = normalizeJobMetaText(item.salary_desc);
  const primaryMetaParts = [city && `城市：${city}`].filter(Boolean) as string[];

  return {
    cityLine: primaryMetaParts.length > 0 ? primaryMetaParts.join(" · ") : `职位 ID：${item.id}`,
    secondaryLine: salary ? `薪资：${salary}` : ""
  };
}

function ProfileSnapshot({ title, profile }: { title: string; profile: JobProfile | null }) {
  if (!profile) {
    return (
      <div className="panel alt">
        <h3>{title}</h3>
        <div className="muted" style={{ marginTop: 8 }}>
          当前阶段还没有生成结构化结果。
        </div>
      </div>
    );
  }

  return (
    <div className="panel alt">
      <div className="section-title">
        <h3>{title}</h3>
        <span className="pill">{SOURCE_LABEL[profile.translation_source ?? "rules"]}</span>
      </div>
      <div className="muted" style={{ marginBottom: 12 }}>
        {profile.version_name}
      </div>

      <div className="profile-structured-block">
        <div className="profile-structured-section">
          <div className="profile-structured-title">{profile.hard_constraints.title}</div>
          <div className="pill-row">
            {profile.hard_constraints.items.length > 0 ? (
              profile.hard_constraints.items.map((item) => (
                <span className="pill" key={`${title}-hard-${item}`}>
                  {item}
                </span>
              ))
            ) : (
              <span className="muted">暂无硬性门槛</span>
            )}
          </div>
        </div>

        <div className="profile-structured-section">
          <div className="profile-structured-title">核心维度</div>
          <div className="profile-competency-list">
            {profile.competencies.length > 0 ? (
              profile.competencies.map((item) => (
                <div className="profile-competency-item" key={`${title}-${item.key}`}>
                  <div className="card-row">
                    <strong>{item.label}</strong>
                    <span className="pill">{item.weight}</span>
                  </div>
                  <div className="muted" style={{ marginTop: 6 }}>
                    {item.note}
                  </div>
                </div>
              ))
            ) : (
              <span className="muted">暂无核心维度</span>
            )}
          </div>
        </div>

        <div className="profile-structured-section">
          <div className="profile-structured-title">{profile.industry_expansion.title}</div>
          <div className="pill-row">
            {profile.industry_expansion.items.length > 0 ? (
              profile.industry_expansion.items.map((item) => (
                <span className="pill" key={`${title}-industry-${item}`}>
                  {item}
                </span>
              ))
            ) : (
              <span className="muted">暂无可迁移场景</span>
            )}
          </div>
        </div>

        <div className="profile-structured-section">
          <div className="profile-structured-title">{profile.exclude_rules.title}</div>
          {profile.exclude_rules.items.length > 0 ? (
            <ul className="profile-bullet-list">
              {profile.exclude_rules.items.map((item) => (
                <li key={`${title}-exclude-${item}`}>{item}</li>
              ))}
            </ul>
          ) : (
            <span className="muted">暂无排除项</span>
          )}
        </div>

        <div className="profile-structured-section">
          <div className="profile-structured-title">画像摘要</div>
          <div className="muted">{profile.impact_summary}</div>
        </div>
      </div>
    </div>
  );
}

const STEP_META: Record<WorkflowStep, { label: string; title: string; description: string }> = {
  jd: {
    label: "第一步",
    title: "JD 转译",
    description: "左边保留原始 JD，右边直接看结构化初稿。"
  },
  sample: {
    label: "第二步",
    title: "优秀样本分析",
    description: "左边放优秀样本原文，右边看样本增强后的招聘标准。"
  },
  final: {
    label: "第三步",
    title: "最终执行画像",
    description: "左边做 HR 微调，右边看最终可执行画像。"
  },
  screening: {
    label: "第四步",
    title: "候选人筛选",
    description: "直接基于最终执行画像查看筛选表，不再跳转到单独页面。"
  }
};

export function ProfileDraftWorkspace({
  jobs,
  jobId
}: {
  jobs: JobOption[];
  jobId: string;
}) {
  const selectedOption = useMemo(() => jobs.find((item) => item.id === jobId) ?? null, [jobs, jobId]);
  const initialJob = useMemo(() => fallbackJob(selectedOption ?? undefined, jobId), [selectedOption, jobId]);

  const [job, setJob] = useState<JobSummary>(initialJob);
  const [loadingDetail, setLoadingDetail] = useState(true);
  const [jdText, setJdText] = useState(initialJob.raw_jd_text);
  const [jdPending, setJdPending] = useState(false);
  const [samplePending, setSamplePending] = useState(false);
  const [calibratePending, setCalibratePending] = useState(false);
  const [screeningPending, setScreeningPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  
  // 任务选择器状态
  const [taskList, setTaskList] = useState<ScreeningTask[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string>("");
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [sampleResumeOne, setSampleResumeOne] = useState("");
  const [sampleResumeTwo, setSampleResumeTwo] = useState("");
  const [sampleNotes, setSampleNotes] = useState("");
  const [sampleFiles, setSampleFiles] = useState<File[]>([]);
  const [localWorkbench, setLocalWorkbench] = useState<JobProfileWorkbench>(emptyWorkbench(jobId));
  const [manualNotes, setManualNotes] = useState("");
  const [industryExpansion, setIndustryExpansion] = useState("");
  const [excludeRules, setExcludeRules] = useState("");
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [activeStep, setActiveStep] = useState<WorkflowStep>("jd");
  const [currentTask, setCurrentTask] = useState<ScreeningTask | null>(null);
  const [screeningCandidates, setScreeningCandidates] = useState<CandidateDetail[]>([]);
  const [isPaused, setIsPaused] = useState(false);
  const isPausedRef = useRef(false);
  isPausedRef.current = isPaused;

  const jdProfile = ensureProfile(localWorkbench.jd_profile);
  const sampleProfile = ensureProfile(localWorkbench.sample_profile);
  const finalProfile = ensureProfile(localWorkbench.final_profile);
  const activeCalibrationProfile = sampleProfile ?? jdProfile;
  const taskBelongsToCurrentJob = currentTask?.job_id === job.id;
  useEffect(() => {
    setJob(initialJob);
    setJdText(initialJob.raw_jd_text);
    setLocalWorkbench(emptyWorkbench(jobId));
    setMessage(null);
    setActiveStep("jd");
    setCurrentTask(null);
    setTaskList([]);
    setSelectedTaskId("");
    setScreeningCandidates([]);
  }, [initialJob, jobId]);

  useEffect(() => {
    if (!selectedOption) {
      return;
    }

    let cancelled = false;

    async function restoreScreeningState() {
      try {
        const [currentTaskResponse, taskListResponse] = await Promise.all([
          fetch(`${API_BASE}/screening-tasks/current`, { cache: "no-store" }),
          fetch(`${API_BASE}/screening-tasks/list?job_id=${jobId}`, { cache: "no-store" }),
        ]);

        const currentTaskPayload = currentTaskResponse.ok ? ((await currentTaskResponse.json()) as ScreeningTask) : null;
        const taskListPayload = taskListResponse.ok
          ? ((await taskListResponse.json()) as { items?: ScreeningTask[] })
          : { items: [] };

        if (cancelled) {
          return;
        }

        const items = taskListPayload.items ?? [];
        setTaskList(items);

        const restoredTask =
          (currentTaskPayload && currentTaskPayload.job_id === jobId ? currentTaskPayload : null) ??
          items[0] ??
          null;

        if (!restoredTask) {
          return;
        }

        setCurrentTask(restoredTask);
        setSelectedTaskId(restoredTask.id);

        const candidatesResponse = await fetch(`${API_BASE}/screening-tasks/${restoredTask.id}/candidates`, {
          cache: "no-store",
        });

        if (!cancelled && candidatesResponse.ok) {
          const candidates = (await candidatesResponse.json()) as CandidateDetail[];
          setScreeningCandidates(candidates ?? []);
        }
      } catch (err) {
        console.error("Restore screening state failed:", err);
      }
    }

    restoreScreeningState();
    return () => {
      cancelled = true;
    };
  }, [jobId, selectedOption]);

  // 加载任务列表
  useEffect(() => {
    if (activeStep !== "screening") return;
    
    async function loadTasks() {
      try {
        const response = await fetch(`${API_BASE}/screening-tasks/list?job_id=${job.id}`);
        if (response.ok) {
          const data = await response.json();
          setTaskList(data.items || []);
          // 默认选中最新任务
          if (data.items && data.items.length > 0 && !selectedTaskId) {
            setSelectedTaskId(data.items[0].id);
          }
        }
      } catch (err) {
        console.error("加载任务列表失败:", err);
      }
    }
    
    loadTasks();
  }, [activeStep, job.id]);

  // Single SSE connection for selected task
  useEffect(() => {
    if (activeStep !== "screening" || !selectedTaskId) {
      return;
    }

    let cancelled = false;
    let reconnectTimer: NodeJS.Timeout | null = null;
    let source: EventSource | null = null;

    function connect() {
      if (source) {
        source.close();
      }

      source = new EventSource(`${API_BASE}/screening-tasks/stream?task_id=${encodeURIComponent(selectedTaskId)}`);

      source.onopen = () => {
        console.log("SSE connection opened for task", selectedTaskId);
      };

      source.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          console.log("SSE event received:", payload.type);

          if (payload.type === "state") {
            // 更新任务状态
            if (!cancelled) {
              setCurrentTask((current) => (current ? { ...current, ...payload.data } : current));
            }
          } else if (payload.type === "heartbeat") {
            // 心跳，无需处理
          }
        } catch {
          // Ignore malformed event payloads.
        }
      };

      source.onerror = () => {
        console.error("SSE error, reconnecting in 3s...");
        source?.close();
        // Reconnect after 3 seconds
        reconnectTimer = setTimeout(() => {
          if (!cancelled) {
            connect();
          }
        }, 3000);
      };
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
      }
      if (source) {
        source.close();
      }
    };
  }, [activeStep, selectedTaskId]);

  // Single SSE connection for all real-time updates (replaces polling)
  useEffect(() => {
    if (activeStep !== "screening" && currentTask?.status !== "running") {
      return;
    }

    let cancelled = false;
    let reconnectTimer: NodeJS.Timeout | null = null;
    let source: EventSource | null = null;

    function connect() {
      if (source) {
        source.close();
      }

      source = new EventSource(`${API_BASE}/screening-tasks/stream?job_id=${encodeURIComponent(job.id)}`);

      source.onopen = () => {
        console.log("SSE connection opened for job", job.id);
      };

      source.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as
            | { type?: "snapshot"; task?: ScreeningTask | null; candidates?: CandidateDetail[]; seq?: number }
            | { type?: "task"; task?: ScreeningTask; seq?: number }
            | { type?: "candidate_upsert"; candidate?: CandidateDetail; seq?: number };

          console.log("SSE event received:", payload.type);

          if (payload.type === "snapshot") {
            if (payload.task) {
              setCurrentTask(payload.task);
              setSelectedTaskId(payload.task.id);
            }
            if (payload.candidates && !isPausedRef.current) {
              setScreeningCandidates(payload.candidates);
            }
          } else if (payload.type === "task") {
            if (payload.task) {
              setCurrentTask(payload.task);
              setSelectedTaskId(payload.task.id);
            }
          } else if (payload.type === "candidate_upsert") {
            if (payload.candidate && !isPausedRef.current) {
              setScreeningCandidates((current) => {
                const index = current.findIndex((item) => item.card.id === payload.candidate!.card.id);
                if (index === -1) {
                  return [...current, payload.candidate!];
                }
                const next = [...current];
                next[index] = payload.candidate!;
                return next;
              });
            }
          }

          if (payload.type === "task" && (payload.task?.status === "completed" || payload.task?.status === "failed")) {
            source?.close();
          }
        } catch {
          // Ignore malformed event payloads.
        }
      };

      source.onerror = () => {
        console.error("SSE error, reconnecting in 3s...");
        source?.close();
        // Reconnect after 3 seconds
        reconnectTimer = setTimeout(() => {
          if (!cancelled) {
            connect();
          }
        }, 3000);
      };
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
      }
      if (source) {
        source.close();
      }
    };
  }, [activeStep, job.id, currentTask?.status]);

  useEffect(() => {
    if (!selectedOption) {
      setLoadingDetail(false);
      return;
    }

    let cancelled = false;

    async function loadDetail() {
      setLoadingDetail(true);
      try {
        const [jobResponse, workbenchResponse] = await Promise.all([
          fetch(`${API_BASE}/jobs/${jobId}`, { cache: "no-store" }),
          fetch(`${API_BASE}/jobs/${jobId}/profiles/workbench`, { cache: "no-store" })
        ]);

        const nextJob = jobResponse.ok
          ? ((await jobResponse.json()) as JobSummary)
          : fallbackJob(jobs.find((item) => item.id === jobId), jobId);
        const nextWorkbench = workbenchResponse.ok
          ? ((await workbenchResponse.json()) as JobProfileWorkbench)
          : emptyWorkbench(jobId);

        if (cancelled) {
          return;
        }

        const normalizedWorkbench: JobProfileWorkbench = {
          job_id: nextWorkbench.job_id,
          jd_profile: ensureProfile(nextWorkbench.jd_profile),
          sample_profile: ensureProfile(nextWorkbench.sample_profile),
          final_profile: ensureProfile(nextWorkbench.final_profile)
        };

        setJob(nextJob);
        setJdText(nextJob.raw_jd_text ?? "");
        setLocalWorkbench(normalizedWorkbench);

        const baseProfile = normalizedWorkbench.sample_profile ?? normalizedWorkbench.jd_profile;
        setManualNotes((baseProfile?.private_notes ?? []).join("\n"));
        setIndustryExpansion((baseProfile?.industry_expansion.items ?? []).join("、"));
        setExcludeRules((baseProfile?.exclude_rules.items ?? []).join("、"));
        setWeights(Object.fromEntries((baseProfile?.competencies ?? []).map((item) => [item.key, item.weight])));
      } catch {
        if (!cancelled) {
          setMessage("当前职位详情加载失败，页面先展示职位列表，你仍然可以稍后重试。");
        }
      } finally {
        if (!cancelled) {
          setLoadingDetail(false);
        }
      }
    }

    loadDetail();
    return () => {
      cancelled = true;
    };
  }, [jobId, jobs, selectedOption]);

  function syncCalibrationBase(profile: JobProfile | null) {
    setManualNotes((profile?.private_notes ?? []).join("\n"));
    setIndustryExpansion((profile?.industry_expansion.items ?? []).join("、"));
    setExcludeRules((profile?.exclude_rules.items ?? []).join("、"));
    setWeights(Object.fromEntries((profile?.competencies ?? []).map((item) => [item.key, item.weight])));
  }

  async function handleRetranslate() {
    setJdPending(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/jobs/${job.id}/translate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: null, raw_jd_text: jdText })
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const nextProfile = ensureProfile((await response.json()) as JobProfile);
      setLocalWorkbench((current) => ({
        ...current,
        jd_profile: nextProfile,
        sample_profile: null,
        final_profile: null
      }));
      syncCalibrationBase(nextProfile);
      setActiveStep("jd");
      setMessage(`已更新 JD 初稿：${nextProfile?.version_name ?? ""}`);
    } catch {
      setMessage("重新转译失败，请检查后端服务或模型配置。");
    } finally {
      setJdPending(false);
    }
  }

  async function handleAnalyzeSamples() {
    const resumes = [sampleResumeOne, sampleResumeTwo].map((item) => item.trim()).filter(Boolean);
    if (resumes.length === 0 && sampleFiles.length === 0) {
      setMessage("请至少粘贴一份优秀样本简历，或上传一份简历文件。");
      return;
    }

    setSamplePending(true);
    setMessage(null);
    try {
      const formData = new FormData();
      resumes.forEach((resume) => formData.append("pasted_resumes", resume));
      sampleFiles.forEach((file) => formData.append("files", file));
      if (sampleNotes.trim()) {
        formData.append("notes", sampleNotes.trim());
      }
      const response = await fetch(`${API_BASE}/jobs/${job.id}/samples/analyze-upload`, {
        method: "POST",
        body: formData
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const nextProfile = ensureProfile((await response.json()) as JobProfile);
      setLocalWorkbench((current) => ({ ...current, sample_profile: nextProfile, final_profile: null }));
      syncCalibrationBase(nextProfile);
      setActiveStep("sample");
      setMessage(`已根据优秀样本生成增强画像：${nextProfile?.version_name ?? ""}`);
    } catch {
      setMessage("样本分析失败，请检查后端服务或模型配置。");
    } finally {
      setSamplePending(false);
    }
  }

  async function handleGenerateFinalProfile() {
    if (!activeCalibrationProfile) {
      setMessage("请先完成 JD 转译，必要时再分析优秀样本。");
      return;
    }

    setCalibratePending(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/jobs/${job.id}/profiles/calibrate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          competency_weights: weights,
          manual_notes: manualNotes
            .split("\n")
            .map((item) => item.trim())
            .filter(Boolean),
          industry_expansion: industryExpansion
            .split(/[、\n]/)
            .map((item) => item.trim())
            .filter(Boolean),
          exclude_rules: excludeRules
            .split(/[、\n]/)
            .map((item) => item.trim())
            .filter(Boolean),
          base_stage: sampleProfile ? "sample" : "jd"
        })
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const nextProfile = ensureProfile((await response.json()) as JobProfile);
      setLocalWorkbench((current) => ({ ...current, final_profile: nextProfile }));
      setActiveStep("final");
      setMessage(`已生成最终执行画像：${nextProfile?.version_name ?? ""}`);
    } catch {
      setMessage("生成最终执行画像失败，请检查后端服务。");
    } finally {
      setCalibratePending(false);
    }
  }

  // 处理全量重新筛选（需要确认）
  function handleRestartScreening() {
    if (taskBelongsToCurrentJob && currentTask) {
      setShowConfirmDialog(true);
    } else {
      handleStartScreening(false);
    }
  }

  // 确认全量重新筛选
  async function confirmRestart() {
    if (confirmText !== "确认清空") {
      setMessage('请输入"确认清空"以确认操作');
      return;
    }

    setShowConfirmDialog(false);
    setConfirmText("");

    // 清空磁盘数据，再以 skip_seen=false 开始全量筛选
    if (currentTask) {
      try {
        await fetch(`${API_BASE}/screening-tasks/${currentTask.id}/clear`, { method: "POST" });
      } catch (err) {
        console.error("清空数据失败:", err);
      }
    }

    handleStartScreening(false);
  }
  
  // 切换任务
  function handleTaskChange(taskId: string) {
    setSelectedTaskId(taskId);
    // 加载选中任务的候选人
    loadTaskCandidates(taskId);
  }
  
  // 加载任务候选人
  async function loadTaskCandidates(taskId: string) {
    try {
      const response = await fetch(`${API_BASE}/screening-tasks/${taskId}/candidates`);
      if (response.ok) {
        const data = await response.json();
        setScreeningCandidates(data || []);
      }
    } catch (err) {
      console.error("加载候选人失败:", err);
    }
  }

  // 开始筛选；skipSeen=true 续跑（只处理新人），skipSeen=false 全量重新分析
  async function handleStartScreening(skipSeen: boolean = true) {
    if (!finalProfile) {
      setMessage("请先生成最终执行画像，再开始筛选。");
      return;
    }

    if (!skipSeen) {
      // 全量重新筛选时，先清空本地展示
      setScreeningCandidates([]);
      setCurrentTask((current) =>
        current
          ? { ...current, candidate_count: 0, auto_pass_count: 0, grade_counts: {}, progress_current: 0, message: "数据已清空，准备重新筛选。" }
          : current,
      );
    }

    setScreeningPending(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/screening-tasks/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: job.id, pages: 3, skip_seen: skipSeen }),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = (await response.json()) as ScreeningTask;
      setCurrentTask(payload);
      setSelectedTaskId(payload.id);
      setActiveStep("screening");
      setMessage(
        skipSeen
          ? "续跑中：已看过的简历会自动跳过，只处理新出现的候选人。"
          : "全量筛选已开始，后台重新扫描所有候选人。",
      );
    } catch {
      setMessage("开始筛选失败，请检查 Boss 连接和后端服务。");
    } finally {
      setScreeningPending(false);
    }
  }

  const steps: WorkflowStep[] = ["jd", "sample", "final", "screening"];
  const currentStepIndex = steps.indexOf(activeStep);
  const currentMeta = STEP_META[activeStep];

  const stepProfiles: Record<WorkflowStep, JobProfile | null> = {
    jd: jdProfile,
    sample: sampleProfile,
    final: finalProfile,
    screening: finalProfile
  };
  const screeningBlueprint =
    profileToBlueprint(finalProfile) ??
    profileToBlueprint(sampleProfile) ??
    profileToBlueprint(jdProfile);

  function goPrevStep() {
    if (currentStepIndex > 0) {
      setActiveStep(steps[currentStepIndex - 1]);
    }
  }

  function goNextStep() {
    if (currentStepIndex < steps.length - 1) {
      setActiveStep(steps[currentStepIndex + 1]);
    }
  }

  function renderStepInput() {
    if (activeStep === "jd") {
      return (
        <div className="panel">
          <div className="section-title">
            <h3>原始 JD</h3>
            <span className="pill">{job.city}</span>
          </div>
          <div className="list">
            <div className="list-item">
              <strong>{job.name}</strong>
              <div className="muted" style={{ marginTop: 8 }}>
                当前状态：{job.status}
              </div>
            </div>
            {loadingDetail ? (
              <div className="list-item muted">正在加载当前职位的 JD 内容...</div>
            ) : (
              <>
                <textarea className="textarea" value={jdText} onChange={(event) => setJdText(event.target.value)} />
                <div className="toolbar">
                  <button className="primary" type="button" disabled={jdPending} onClick={handleRetranslate}>
                    {jdPending ? "转译中..." : "生成 JD 初稿"}
                  </button>
                  <Link href="/settings/llm" className="toolbar-link">
                    配置模型
                  </Link>
                </div>
              </>
            )}
          </div>
        </div>
      );
    }

    if (activeStep === "sample") {
      return (
        <div className="panel">
          <div className="section-title">
            <h3>优秀样本原文</h3>
            <span className="pill">样本输入</span>
          </div>
          <div className="list">
            <div className="list-item">
              <strong>让系统理解“什么样的人最对味”</strong>
              <div className="muted" style={{ marginTop: 8 }}>
                这里保留原始样本内容，右边只看样本增强后的结构化结果。
              </div>
            </div>
            <div className="field-group">
              <strong>样本简历 1</strong>
              <textarea className="textarea" value={sampleResumeOne} onChange={(event) => setSampleResumeOne(event.target.value)} style={{ minHeight: 140 }} />
            </div>
            <div className="field-group">
              <strong>样本简历 2</strong>
              <textarea className="textarea" value={sampleResumeTwo} onChange={(event) => setSampleResumeTwo(event.target.value)} style={{ minHeight: 140 }} />
            </div>
            <div className="field-group">
              <strong>上传优秀简历文件</strong>
              <input className="text-input" type="file" multiple accept=".txt,.md,.docx,.pdf" onChange={(event) => setSampleFiles(Array.from(event.target.files ?? []))} />
              <div className="muted">支持 `txt`、`md`、`docx`、`pdf`，上传文件会保存在项目目录下方便追溯。</div>
            </div>
            <div className="field-group">
              <strong>样本备注</strong>
              <textarea
                className="textarea"
                value={sampleNotes}
                onChange={(event) => setSampleNotes(event.target.value)}
                style={{ minHeight: 90 }}
                placeholder="例如：我喜欢这类人，是因为他做过矿山设备现场项目，而且能独立排障。"
              />
            </div>
            <div className="toolbar">
              <button className="primary" type="button" disabled={samplePending || loadingDetail} onClick={handleAnalyzeSamples}>
                {samplePending ? "分析中..." : "生成样本增强画像"}
              </button>
            </div>
          </div>
        </div>
      );
    }

  if (activeStep === "screening") {
    return (
      <div className="panel">
        {/* 任务选择器 */}
        {taskList.length > 0 && (
          <div className="field-group" style={{ marginBottom: 16 }}>
            <strong>选择任务</strong>
            <select 
              className="text-input" 
              value={selectedTaskId} 
              onChange={(e) => handleTaskChange(e.target.value)}
            >
              {taskList.map((task) => (
                <option key={task.id} value={task.id}>
                  {task.id} - {getTaskStatusLabel(task)} - {task.candidate_count || 0}人
                </option>
              ))}
            </select>
          </div>
        )}
        
        <div className="workflow-actions" style={{ marginBottom: 16 }}>
          <button type="button" onClick={() => setActiveStep("final")}>
            返回最终执行画像
          </button>
          {taskBelongsToCurrentJob ? (
            <>
              <button
                className="primary"
                type="button"
                disabled={screeningPending || !finalProfile}
                onClick={() => handleStartScreening(true)}
                title="跳过已分析过的候选人，只处理 Boss 新推荐的人"
              >
                {screeningPending ? "筛选中..." : "续跑（只看新人）"}
              </button>
              <button
                type="button"
                disabled={screeningPending || !finalProfile}
                onClick={handleRestartScreening}
                title="清空全部结果，从头重新分析所有候选人"
              >
                全量重新筛选...
              </button>
              <button
                type="button"
                className={isPaused ? "primary" : ""}
                onClick={() => setIsPaused((v) => !v)}
              >
                {isPaused ? "继续更新" : "暂停更新"}
              </button>
            </>
          ) : (
            <button
              className="primary"
              type="button"
              disabled={screeningPending || !finalProfile}
              onClick={() => handleStartScreening(true)}
            >
              {screeningPending ? "筛选中..." : "开始筛选"}
            </button>
          )}
        </div>

        {/* 确认对话框 */}
        {showConfirmDialog && (
          <div className="panel alt" style={{ marginTop: 12, marginBottom: 12, border: "2px solid #ef4444" }}>
            <div className="section-title">
              <h3>⚠️ 确认重新筛选</h3>
            </div>
            <div className="list">
              <div className="list-item">
                <strong>当前任务状态：</strong>
                <div className="muted" style={{ marginTop: 8 }}>
                  • 候选人数量：{currentTask?.candidate_count || 0}人<br/>
                  • 筛选完成：{currentTask?.candidate_count || 0}人<br/>
                  • 已收藏：{currentTask?.auto_pass_count || 0}人
                </div>
              </div>
              <div className="list-item" style={{ color: "#ef4444" }}>
                <strong>❗ 重新筛选将清空所有数据</strong>
              </div>
              <div className="list-item">
                <strong>请输入"确认清空"以继续：</strong>
                <input 
                  className="text-input" 
                  value={confirmText} 
                  onChange={(e) => setConfirmText(e.target.value)}
                  placeholder="确认清空"
                  style={{ marginTop: 8 }}
                />
              </div>
              <div className="toolbar">
                <button type="button" onClick={() => { setShowConfirmDialog(false); setConfirmText(""); }}>
                  取消
                </button>
                <button 
                  className="primary" 
                  type="button" 
                  onClick={confirmRestart}
                  disabled={confirmText !== "确认清空"}
                >
                  确认清空并重新筛选
                </button>
              </div>
            </div>
          </div>
        )}

        <CandidateScreeningBoard
          jobId={job.id}
          candidates={screeningCandidates}
          task={taskBelongsToCurrentJob && currentTask ? currentTask : {
            id: "screening-task-empty",
            job_id: job.id,
            profile_version_id: screeningBlueprint?.profile_version_id ?? "",
            status: "pending",
            progress_current: 0,
            progress_total: 1,
            started_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            message: "当前还没有筛选任务。",
            candidate_count: 0,
            auto_pass_count: 0,
            grade_counts: {}
          }}
          blueprint={screeningCandidates[0]?.screening_blueprint ?? screeningBlueprint}
        />
      </div>
    );
  }

    return (
      <div className="panel">
        <div className="section-title">
          <h3>HR 校准输入</h3>
          <span className="pill">人工微调</span>
        </div>
        <div className="list">
          <div className="list-item">
            <strong>这里不是重新定义要求，而是微调已经汇总好的结构化标准</strong>
            <div className="muted" style={{ marginTop: 8 }}>
              左边做权重、私房标准、可迁移场景和排除项的微调，右边直接查看最终执行画像。
            </div>
          </div>

          {(activeCalibrationProfile?.competencies ?? []).map((item) => (
            <div className="calibration-row" key={item.key}>
              <div>
                <strong>{item.label}</strong>
                <div className="muted" style={{ marginTop: 6 }}>
                  {item.note}
                </div>
              </div>
              <div className="calibration-slider">
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={weights[item.key] ?? item.weight}
                  onChange={(event) => setWeights((current) => ({ ...current, [item.key]: Number(event.target.value) }))}
                />
                <strong>{weights[item.key] ?? item.weight}</strong>
              </div>
            </div>
          ))}

          <div className="field-group">
            <strong>老板私房标准</strong>
            <textarea className="textarea" value={manualNotes} onChange={(event) => setManualNotes(event.target.value)} style={{ minHeight: 110 }} />
          </div>

          <div className="field-group">
            <strong>可迁移场景补充</strong>
            <input className="text-input" value={industryExpansion} onChange={(event) => setIndustryExpansion(event.target.value)} />
          </div>

          <div className="field-group">
            <strong>排除项补充</strong>
            <input className="text-input" value={excludeRules} onChange={(event) => setExcludeRules(event.target.value)} />
          </div>

          <div className="toolbar">
            <button className="primary" type="button" disabled={calibratePending || loadingDetail} onClick={handleGenerateFinalProfile}>
              {calibratePending ? "生成中..." : "生成最终执行画像"}
            </button>
            <button className="secondary" type="button" disabled={screeningPending || !finalProfile} onClick={() => handleStartScreening(true)}>
              {screeningPending ? "筛选中..." : taskBelongsToCurrentJob ? "续跑筛选" : "开始筛选"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (jobs.length === 0) {
    return (
      <section className="panel">
        <h2>暂无可设计的职位</h2>
        <div className="muted" style={{ marginTop: 8 }}>
          招聘职位列表当前为空。先去 Boss 连接页同步真实职位，再回来构建画像。
        </div>
      </section>
    );
  }

  if (!selectedOption) {
    return (
      <section className="workflow-shell">
        <aside className="panel">
          <div className="section-title">
            <h2>招聘职位列表</h2>
            <span className="pill">Boss 实时</span>
          </div>
          <div className="job-list">
            {jobs.map((item) => {
              const meta = getJobCardMeta(item);
              return (
                <Link key={item.id} href={`/jobs/${item.id}/profile-draft`} className="job-option">
                  <div className="card-row">
                    <strong>{item.name}</strong>
                    <span className={`pill ${item.status === "active" ? "good" : ""}`}>{item.status}</span>
                  </div>
                  <div className="muted" style={{ marginTop: 8 }}>
                    {meta.cityLine}
                  </div>
                  {meta.secondaryLine ? (
                    <div className="muted" style={{ marginTop: 4 }}>
                      {meta.secondaryLine}
                    </div>
                  ) : null}
                </Link>
              );
            })}
          </div>
        </aside>
        <div className="workflow-main">
          <div className="panel">
            <h2>请先选择一个招聘职位</h2>
            <div className="muted" style={{ marginTop: 8 }}>
              只有选中了真实招聘职位，我们才会开始构建 JD 初稿、样本增强画像和最终执行画像。
            </div>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="workflow-shell">
      <aside className="panel">
        <div className="section-title">
          <h2>招聘职位列表</h2>
          <span className="pill">Boss 实时</span>
        </div>
        <div className="job-list">
          {jobs.map((item) => {
            const meta = getJobCardMeta(item);
            return (
              <Link
                key={item.id}
                href={`/jobs/${item.id}/profile-draft`}
                className={`job-option ${selectedOption.id === item.id ? "active" : ""}`}
              >
                <div className="card-row">
                  <strong>{item.name}</strong>
                  <span className={`pill ${item.status === "active" ? "good" : ""}`}>{item.status}</span>
                </div>
                <div className="muted" style={{ marginTop: 8 }}>
                  {meta.cityLine}
                </div>
                {meta.secondaryLine ? (
                  <div className="muted" style={{ marginTop: 4 }}>
                    {meta.secondaryLine}
                  </div>
                ) : null}
              </Link>
            );
          })}
        </div>
      </aside>

      <div className="workflow-main">
        <div className="panel">
          <div className="section-title">
            <div>
              <div className="muted">{currentMeta.label}</div>
              <h2 style={{ marginTop: 6 }}>{currentMeta.title}</h2>
              <div className="muted" style={{ marginTop: 6 }}>
                {currentMeta.description}
              </div>
            </div>
            <span className="pill">{job.name}</span>
          </div>

          <div className="workflow-stepper">
            {steps.map((step, index) => (
              <button
                key={step}
                type="button"
                className={`workflow-step ${activeStep === step ? "active" : ""}`}
                onClick={() => setActiveStep(step)}
              >
                <span className="workflow-step-index">{index + 1}</span>
                <span>{STEP_META[step].title}</span>
              </button>
            ))}
          </div>

          <div className="workflow-actions" style={{ marginTop: 14 }}>
            <button type="button" onClick={goPrevStep} disabled={currentStepIndex === 0}>
              上一步
            </button>
            <button type="button" onClick={goNextStep} disabled={currentStepIndex === steps.length - 1}>
              下一步
            </button>
          </div>
        </div>

        {activeStep === "screening" ? (
          <div>{renderStepInput()}</div>
        ) : (
          <div className="workflow-stage-grid">
            {renderStepInput()}
            {activeStep === "final" && finalProfile ? (
              <EditableFinalProfile
                jobId={job.id}
                profile={finalProfile}
                onSave={(updated) => setLocalWorkbench((curr) => ({ ...curr, final_profile: updated }))}
              />
            ) : (
              <ProfileSnapshot title={STEP_META[activeStep].title} profile={stepProfiles[activeStep]} />
            )}
          </div>
        )}

        {message ? <div className="panel">{message}</div> : null}
      </div>
    </section>
  );
}
