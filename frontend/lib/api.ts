import {
  mockDashboard,
  mockFeedback,
  mockJob,
  mockJobs,
} from "@/lib/mock-data";
import type {
  BossStatus,
  CandidateDetail,
  DashboardSnapshot,
  FeedbackSummary,
  JobOption,
  JobProfile,
  JobProfileWorkbench,
  JobSummary,
  LLMTraceDetail,
  LLMTraceSummary,
  LLMSettings,
  ScreeningTask
} from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://autohr.stoneboss.vip/api";

function emptyTask(jobId = ""): ScreeningTask {
  const now = new Date().toISOString();
  return {
    id: "screening-task-empty",
    job_id: jobId,
    profile_version_id: "",
    status: "pending",
    progress_current: 0,
    progress_total: 1,
    started_at: now,
    updated_at: now,
    message: "当前还没有筛选任务。",
    candidate_count: 0,
    auto_pass_count: 0,
    grade_counts: {}
  };
}

async function fetchJson<T>(path: string, fallback: T, timeoutMs = 1500): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE}${path}`, { cache: "no-store", signal: controller.signal });
    if (!response.ok) {
      return fallback;
    }
    return (await response.json()) as T;
  } catch {
    return fallback;
  } finally {
    clearTimeout(timeout);
  }
}

export async function getDashboard(): Promise<DashboardSnapshot> {
  return fetchJson("/dashboard", mockDashboard);
}

export async function getCurrentJob(): Promise<JobSummary> {
  return fetchJson("/jobs/current", mockJob);
}

export async function getJobs(): Promise<JobOption[]> {
  return fetchJson("/jobs", []);
}

export async function getLiveBossJobs(): Promise<JobOption[]> {
  return fetchJson("/boss/jobs/live", []);
}

export async function getJob(jobId: string): Promise<JobSummary> {
  const [liveJobs, jobData] = await Promise.all([
    getJobs(),
    fetchJson<JobSummary | null>(`/jobs/${jobId}`, null),
  ]);
  if (jobData !== null) return jobData;

  const option = liveJobs.find((item) => item.id === jobId) ?? mockJobs.find((item) => item.id === jobId);
  if (option == null) return mockJob;
  return {
    ...mockJob,
    id: option.id,
    name: option.name,
    city: option.city,
    status: option.status,
    raw_jd_text: `${option.name} job description placeholder.`,
    current_profile: {
      ...mockJob.current_profile,
      version_id: `${option.id}-profile-v1`,
      version_name: option.profile_version_name,
      job_id: option.id
    }
  };
}

export async function getCurrentProfile(jobId: string): Promise<JobProfile> {
  const result = await fetchJson<JobProfile | null>(`/jobs/${jobId}/profiles/current`, null);
  if (result !== null) return result;
  return (await getJob(jobId)).current_profile;
}

export async function getProfileWorkbench(jobId: string): Promise<JobProfileWorkbench> {
  const result = await fetchJson<JobProfileWorkbench | null>(`/jobs/${jobId}/profiles/workbench`, null);
  if (result !== null) return result;
  return {
    job_id: jobId,
    jd_profile: (await getJob(jobId)).current_profile,
    sample_profile: null,
    final_profile: null
  };
}

export async function getCandidates(jobId = "job-001"): Promise<CandidateDetail[]> {
  return fetchJson(`/candidates?job_id=${encodeURIComponent(jobId)}`, []);
}

export async function getCandidate(candidateId: string, jobId = "job-001"): Promise<CandidateDetail> {
  const response = await fetchJson<CandidateDetail | null>(
    `/candidates/${candidateId}?job_id=${encodeURIComponent(jobId)}`,
    null,
  );
  if (response == null) {
    throw new Error("Candidate not found.");
  }
  return response;
}

export async function getTask(jobId = ""): Promise<ScreeningTask> {
  const task = await fetchJson("/screening-tasks/current", emptyTask(jobId));
  if (jobId && task.job_id && task.job_id !== jobId) {
    return emptyTask(jobId);
  }
  return task;
}

export async function getFeedbackSummary(): Promise<FeedbackSummary> {
  return fetchJson("/feedback/summary", mockFeedback);
}

export async function getLLMSettings(): Promise<LLMSettings> {
  return fetchJson("/settings/llm", {
    provider_label: "OpenAI Compatible",
    enabled: false,
    has_api_key: false,
    api_key: "",
    base_url: "https://api.openai.com/v1",
    model: "gpt-4.1-mini",
    api_style: "chat_completions",
    timeout_seconds: 45
  });
}

export async function getLLMTraces(): Promise<LLMTraceSummary[]> {
  return fetchJson("/settings/llm/traces", []);
}

export async function getLLMTrace(traceId: string): Promise<LLMTraceDetail | null> {
  return fetchJson(`/settings/llm/traces/${encodeURIComponent(traceId)}`, null);
}

export async function getBossStatus(): Promise<BossStatus> {
  return fetchJson("/boss/status", {
    cdp_url: "http://127.0.0.1:9222",
    cdp_reachable: false,
    browser_connected: false,
    boss_page_detected: false,
    login_cookie_detected: false,
    job_list_available: false,
    job_count: 0,
    message: "Boss connection status has not been checked yet."
  }, 900);
}
