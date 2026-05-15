"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";

export function CandidateManualActions({
  candidateId,
  jobId,
  collected,
  greeted,
  collectedAt,
  greetedAt,
}: {
  candidateId: string;
  jobId: string;
  collected: boolean;
  greeted: boolean;
  collectedAt?: string | null;
  greetedAt?: string | null;
}) {
  const [collecting, setCollecting] = useState(false);
  const [greeting, setGreeting] = useState(false);
  const [collectedState, setCollectedState] = useState(collected);
  const [greetedState, setGreetedState] = useState(greeted);
  const [message, setMessage] = useState("");

  useEffect(() => {
    setCollectedState(collected);
  }, [collected, collectedAt]);

  useEffect(() => {
    setGreetedState(greeted);
  }, [greeted, greetedAt]);

  async function runAction(action: "collect" | "greet") {
    const isCollect = action === "collect";
    isCollect ? setCollecting(true) : setGreeting(true);
    setMessage("");

    try {
      const response = await fetch(
        `${API_BASE}/candidates/${encodeURIComponent(candidateId)}/${action}?job_id=${encodeURIComponent(jobId)}`,
        {
          method: "POST",
        }
      );

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || `Action ${action} failed`);
      }

      if (isCollect) {
        setCollectedState(true);
        setMessage("已成功加入收藏。");
      } else {
        setGreetedState(true);
        setMessage("已成功发送打招呼。");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "操作失败。");
    } finally {
      isCollect ? setCollecting(false) : setGreeting(false);
    }
  }

  return (
    <div className="list">
      <div className="toolbar">
        <button 
          className={collectedState ? "secondary" : "primary"} 
          disabled={collecting || collectedState} 
          onClick={() => runAction("collect")} 
          type="button"
        >
          {collectedState ? "✓ 已收藏" : collecting ? "收藏中..." : "手动收藏"}
        </button>
        <button 
          className={greetedState ? "secondary" : "primary"}
          disabled={greeting || greetedState} 
          onClick={() => runAction("greet")} 
          type="button"
        >
          {greetedState ? "✓ 已打招呼" : greeting ? "发送中..." : "手动打招呼"}
        </button>
      </div>
      {message ? <div className="muted">{message}</div> : null}
    </div>
  );
}
