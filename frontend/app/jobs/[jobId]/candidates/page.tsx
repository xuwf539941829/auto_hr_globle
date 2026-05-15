"use client";

import { useEffect, useState, useCallback, useRef } from "react";

import { CandidateScreeningBoard } from "@/components/candidate-screening-board";
import { PageHeader } from "@/components/page-header";
import { getCandidates, getProfileWorkbench, getTask } from "@/lib/api";
import type { CandidateDetail, JobProfile, ScreeningBlueprint, ScreeningTask } from "@/lib/types";

export async function generateStaticParams() {
  return [{ jobId: "job-001" }];
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
    private_notes: profile.private_notes,
  };
}

export default function CandidatesPage({ params }: { params: Promise<{ jobId: string }> }) {
  const [jobId, setJobId] = useState<string>("");
  const [candidates, setCandidates] = useState<CandidateDetail[]>([]);
  const [task, setTask] = useState<ScreeningTask | null>(null);
  const [workbench, setWorkbench] = useState<any>(null);
  const [blueprint, setBlueprint] = useState<ScreeningBlueprint | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPaused, setIsPaused] = useState(false);
  const isPausedRef = useRef(false);
  isPausedRef.current = isPaused;

  const togglePause = useCallback(() => {
    setIsPaused((prev) => !prev);
  }, []);

  // Use ref to track latest candidates for SSE updates
  const candidatesRef = useRef<CandidateDetail[]>([]);
  candidatesRef.current = candidates;

  // Stable callback for updating candidates list from SSE
  const handleCandidateUpsert = useCallback((candidate: CandidateDetail) => {
    setCandidates((prev) => {
      const next = [...prev];
      const idx = next.findIndex((item) => item.card.id === candidate.card.id);
      if (idx >= 0) {
        next[idx] = candidate;
      } else {
        next.push(candidate);
      }
      return next;
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    let eventSource: EventSource | null = null;
    let reconnectTimer: NodeJS.Timeout | null = null;

    async function init() {
      const { jobId: jid } = await params;
      if (cancelled) return;
      setJobId(jid);

      try {
        const [c, t, w] = await Promise.all([
          getCandidates(jid),
          getTask(jid),
          getProfileWorkbench(jid),
        ]);
        if (cancelled) return;

        setCandidates(c);
        setTask(t);
        setWorkbench(w);
        setIsLoading(false);

        // Prefer the profile version the task was actually started with, so column
        // headers always match what was screened — even if the workbench has a newer
        // final_profile that differs from the running task's profile.
        const allProfiles = [w?.final_profile, w?.sample_profile, w?.jd_profile].filter(Boolean);
        const taskProfile = t?.profile_version_id
          ? allProfiles.find((p) => p?.version_id === t.profile_version_id) ?? null
          : null;
        const profileBlueprint =
          profileToBlueprint(taskProfile) ??
          profileToBlueprint(w.final_profile) ??
          profileToBlueprint(w.sample_profile) ??
          profileToBlueprint(w.jd_profile);
        setBlueprint(c[0]?.screening_blueprint ?? profileBlueprint);

        // Connect to SSE stream for real-time updates
        connectSSE(jid);
      } catch (error) {
        console.error("Failed to load initial data:", error);
        setIsLoading(false);
      }
    }

    function connectSSE(jid: string) {
      if (eventSource) {
        eventSource.close();
      }

      const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";
      eventSource = new EventSource(`${API_BASE}/screening-tasks/stream?job_id=${encodeURIComponent(jid)}`);

      eventSource.onopen = () => {
        console.log("SSE connection opened for job", jid);
      };

      eventSource.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          console.log("SSE event received:", payload.type, payload);
          
          if (payload.type === "snapshot") {
            if (payload.task) {
              setTask(payload.task);
            }
            if (payload.candidates && Array.isArray(payload.candidates) && !isPausedRef.current) {
              console.log("Setting candidates from snapshot:", payload.candidates.length);
              setCandidates(payload.candidates);
            }
          } else if (payload.type === "task") {
            if (payload.task) {
              setTask(payload.task);
            }
          } else if (payload.type === "candidate_upsert") {
            if (payload.candidate && !isPausedRef.current) {
              console.log("Upserting candidate:", payload.candidate.card?.id);
              handleCandidateUpsert(payload.candidate);
            }
          }
        } catch (err) {
          console.error("Failed to parse SSE event:", err);
        }
      };

      eventSource.onerror = (error) => {
        console.error("SSE error:", error);
        eventSource?.close();
        
        // Reconnect after 3 seconds
        reconnectTimer = setTimeout(() => {
          if (!cancelled) {
            console.log("Reconnecting SSE...");
            connectSSE(jid);
          }
        }, 3000);
      };
    }

    init();

    return () => {
      cancelled = true;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
      }
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [params, handleCandidateUpsert]);

  if (isLoading) {
    return (
      <>
        <PageHeader title="候选人筛选台" description="加载中..." />
        <div className="panel" style={{ padding: 40, textAlign: "center" }}>
          <div className="muted">正在加载候选人数据...</div>
        </div>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="候选人筛选台"
        description="主表格直接按当前岗位的招聘要求建列。即使候选人还没拉回，也先展示本轮筛选到底在看什么。"
        badge={`任务状态：${task?.status || "未知"}`}
      />
      <CandidateScreeningBoard jobId={jobId} candidates={candidates} task={task || { id: "", job_id: jobId, profile_version_id: "", status: "pending", progress_current: 0, progress_total: 1, started_at: new Date().toISOString(), updated_at: new Date().toISOString(), message: "", candidate_count: 0, auto_pass_count: 0, grade_counts: {} }} blueprint={blueprint} isPaused={isPaused} onTogglePause={togglePause} />
    </>
  );
}
