"use client";

import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";

export function ScreeningTaskActions({ jobId }: { jobId: string }) {
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState("");

  async function runTask() {
    setRunning(true);
    setMessage("");
    try {
      const response = await fetch(`${API_BASE}/screening-tasks/run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          job_id: jobId,
          pages: 1
        })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "Failed to run screening task.");
      }
      setMessage(payload.message || "Screening task finished.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to run screening task.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="list">
      <div className="toolbar">
        <button className="primary" disabled={running} onClick={runTask} type="button">
          {running ? "Running..." : "Run screening once"}
        </button>
      </div>
      {message ? <div className="muted">{message}</div> : null}
    </div>
  );
}
