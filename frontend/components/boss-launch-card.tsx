"use client";

import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";

type BrowserType = "auto" | "chrome" | "edge";

type LaunchResponse = {
  status: string;
  browser_type: string;
  browser_name: string;
  browser_path: string;
  debug_port: number;
  user_data_dir: string;
  target_url: string;
  message: string;
};

type BossStatus = {
  cdp_url: string;
  cdp_reachable: boolean;
  browser_connected: boolean;
  boss_page_detected: boolean;
  login_cookie_detected: boolean;
  job_list_available: boolean;
  job_count: number;
  message: string;
};

const BROWSER_OPTIONS: { value: BrowserType; label: string }[] = [
  { value: "auto", label: "自动检测" },
  { value: "chrome", label: "Google Chrome" },
  { value: "edge", label: "Microsoft Edge" },
];

export function BossLaunchCard() {
  const [browserType, setBrowserType] = useState<BrowserType>("auto");
  const [launchPending, setLaunchPending] = useState(false);
  const [statusPending, setStatusPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [details, setDetails] = useState<LaunchResponse | null>(null);
  const [status, setStatus] = useState<BossStatus | null>(null);

  async function handleLaunch() {
    setLaunchPending(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/boss/launch-login?browser_type=${browserType}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? `HTTP ${response.status}`);
      }

      const payload = (await response.json()) as LaunchResponse;
      setDetails(payload);
      setMessage(payload.message);
    } catch (error) {
      console.error("Launch Boss login failed", error);
      setMessage(error instanceof Error ? error.message : "启动失败，请检查后端服务。");
    } finally {
      setLaunchPending(false);
    }
  }

  async function handleStatusCheck() {
    setStatusPending(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/boss/status`, {
        method: "GET",
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? `HTTP ${response.status}`);
      }

      const payload = (await response.json()) as BossStatus;
      setStatus(payload);
      setMessage(payload.message);
    } catch (error) {
      console.error("Check Boss status failed", error);
      setMessage(error instanceof Error ? error.message : "检测失败，请检查后端服务。");
    } finally {
      setStatusPending(false);
    }
  }

  return (
    <div className="list">
      <div className="list-item">
        <strong>一键启动 Boss 登录浏览器</strong>
        <div className="muted" style={{ marginTop: 8 }}>
          点击后系统会直接启动带 9222 调试端口的浏览器，并打开 Boss 招聘后台页面。
        </div>
      </div>

      <div className="list-item">
        <strong>浏览器选择</strong>
        <div style={{ display: "flex", gap: 20, marginTop: 10, flexWrap: "wrap" }}>
          {BROWSER_OPTIONS.map(({ value, label }) => (
            <label
              key={value}
              style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", userSelect: "none" }}
            >
              <input
                type="radio"
                name="browserType"
                value={value}
                checked={browserType === value}
                onChange={() => setBrowserType(value)}
              />
              {label}
            </label>
          ))}
        </div>
      </div>

      <div className="toolbar">
        <button className="primary" type="button" disabled={launchPending} onClick={handleLaunch}>
          {launchPending ? "启动中..." : "启动 Boss 登录"}
        </button>
        <button type="button" disabled={statusPending} onClick={handleStatusCheck}>
          {statusPending ? "检测中..." : "检测连接状态"}
        </button>
      </div>

      {message ? <div className="list-item">{message}</div> : null}

      {details ? (
        <div className="list-item">
          <strong>启动详情</strong>
          <div className="muted" style={{ marginTop: 8 }}>
            浏览器：{details.browser_name}（{details.browser_path}）
          </div>
          <div className="muted" style={{ marginTop: 6 }}>
            调试端口：{details.debug_port}
          </div>
          <div className="muted" style={{ marginTop: 6 }}>
            配置目录：{details.user_data_dir}
          </div>
        </div>
      ) : null}

      {status ? (
        <div className="list-item">
          <strong>连接状态</strong>
          <div className="pill-row" style={{ marginTop: 10 }}>
            <span className={`pill ${status.cdp_reachable ? "good" : "bad"}`}>9222 端口</span>
            <span className={`pill ${status.browser_connected ? "good" : "bad"}`}>浏览器连接</span>
            <span className={`pill ${status.boss_page_detected ? "good" : "warn"}`}>Boss 页面</span>
            <span className={`pill ${status.login_cookie_detected ? "good" : "warn"}`}>登录态</span>
            <span className={`pill ${status.job_list_available ? "good" : "warn"}`}>职位列表</span>
          </div>
          <div className="muted" style={{ marginTop: 10 }}>
            当前职位数：{status.job_count}
          </div>
          <div className="muted" style={{ marginTop: 6 }}>
            调试地址：{status.cdp_url}
          </div>
        </div>
      ) : null}
    </div>
  );
}
