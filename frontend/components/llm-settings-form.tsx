"use client";

import { useState } from "react";

import type { LLMSettings } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";

export function LLMSettingsForm({ initialSettings }: { initialSettings: LLMSettings }) {
  const [enabled, setEnabled] = useState(initialSettings.enabled);
  const [apiKey, setApiKey] = useState(initialSettings.api_key);
  const [baseUrl, setBaseUrl] = useState(initialSettings.base_url);
  const [model, setModel] = useState(initialSettings.model);
  const [apiStyle, setApiStyle] = useState(initialSettings.api_style);
  const [timeoutSeconds, setTimeoutSeconds] = useState(String(initialSettings.timeout_seconds));
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSave() {
    setPending(true);
    setMessage(null);

    try {
      const response = await fetch(`${API_BASE}/settings/llm`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          enabled,
          api_key: apiKey,
          base_url: baseUrl,
          model,
          api_style: apiStyle,
          timeout_seconds: Number(timeoutSeconds)
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const saved = (await response.json()) as LLMSettings;
      setEnabled(saved.enabled);
      setApiKey(saved.api_key);
      setBaseUrl(saved.base_url);
      setModel(saved.model);
      setApiStyle(saved.api_style);
      setTimeoutSeconds(String(saved.timeout_seconds));
      setMessage("模型配置已保存。下一次重新转译会直接读取这里的配置。");
    } catch (error) {
      console.error("Save LLM settings failed", error);
      setMessage("保存失败，请检查后端服务。");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="settings-grid">
      <section className="panel">
        <div className="section-title">
          <h2>LLM 连接配置</h2>
          <span className={`pill ${enabled ? "good" : ""}`}>{enabled ? "已启用" : "未启用"}</span>
        </div>

        <div className="list">
          <label className="field-group">
            <strong>启用模型转译</strong>
            <select className="text-input" value={enabled ? "on" : "off"} onChange={(event) => setEnabled(event.target.value === "on")}>
              <option value="on">启用</option>
              <option value="off">关闭</option>
            </select>
          </label>

          <label className="field-group">
            <strong>API Key</strong>
            <input
              className="text-input"
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="输入模型平台的 API Key"
            />
          </label>

          <label className="field-group">
            <strong>Base URL</strong>
            <input
              className="text-input"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder="https://api.openai.com/v1"
            />
          </label>

          <div className="settings-row">
            <label className="field-group">
              <strong>模型名</strong>
              <input className="text-input" value={model} onChange={(event) => setModel(event.target.value)} />
            </label>

            <label className="field-group">
              <strong>接口风格</strong>
              <select className="text-input" value={apiStyle} onChange={(event) => setApiStyle(event.target.value as LLMSettings["api_style"])}>
                <option value="chat_completions">chat_completions</option>
                <option value="responses">responses</option>
              </select>
            </label>
          </div>

          <label className="field-group">
            <strong>超时时间（秒）</strong>
            <input
              className="text-input"
              type="number"
              min={5}
              max={180}
              value={timeoutSeconds}
              onChange={(event) => setTimeoutSeconds(event.target.value)}
            />
          </label>

          <div className="toolbar">
            <button className="primary" type="button" disabled={pending} onClick={handleSave}>
              {pending ? "保存中..." : "保存模型配置"}
            </button>
          </div>

          {message ? <div className="list-item">{message}</div> : null}
        </div>
      </section>

      <section className="panel alt">
        <h2>使用说明</h2>
        <div className="list">
          <div className="list-item">
            <strong>保存后立即生效</strong>
            <div className="muted" style={{ marginTop: 8 }}>
              画像页点击“重新转译”时，后端会优先读取这里的配置，不再依赖环境变量。
            </div>
          </div>
          <div className="list-item">
            <strong>失败自动兜底</strong>
            <div className="muted" style={{ marginTop: 8 }}>
              如果模型请求失败，系统会自动回退到规则转译，不会把整条流程卡死。
            </div>
          </div>
          <div className="list-item">
            <strong>当前状态</strong>
            <div className="muted" style={{ marginTop: 8 }}>
              {initialSettings.has_api_key ? "系统中已经保存过 API Key。" : "当前还没有保存 API Key。"}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
