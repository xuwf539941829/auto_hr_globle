"use client";

import { useState } from "react";
import type { JobProfile } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";

type CompetencyEdit = { key: string; label: string; weight: number; note: string };

type EditState = {
  hardConstraintsText: string;
  competencies: CompetencyEdit[];
  industryExpansionText: string;
  excludeRulesText: string;
  privateNotesText: string;
  impactSummary: string;
};

function toEditState(profile: JobProfile): EditState {
  return {
    hardConstraintsText: profile.hard_constraints.items.join("\n"),
    competencies: profile.competencies.map((c) => ({ key: c.key, label: c.label, weight: c.weight, note: c.note })),
    industryExpansionText: profile.industry_expansion.items.join("\n"),
    excludeRulesText: profile.exclude_rules.items.join("\n"),
    privateNotesText: profile.private_notes.join("\n"),
    impactSummary: profile.impact_summary,
  };
}

export function EditableFinalProfile({
  jobId,
  profile,
  onSave,
}: {
  jobId: string;
  profile: JobProfile;
  onSave: (updated: JobProfile) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editState, setEditState] = useState<EditState>(() => toEditState(profile));
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  function enterEdit() {
    setEditState(toEditState(profile));
    setErrorMsg(null);
    setEditing(true);
  }

  function cancelEdit() {
    setEditing(false);
    setErrorMsg(null);
  }

  async function handleSave() {
    setSaving(true);
    setErrorMsg(null);
    try {
      const body: JobProfile = {
        ...profile,
        hard_constraints: {
          ...profile.hard_constraints,
          items: editState.hardConstraintsText.split("\n").map((s) => s.trim()).filter(Boolean),
        },
        competencies: editState.competencies,
        industry_expansion: {
          ...profile.industry_expansion,
          items: editState.industryExpansionText.split("\n").map((s) => s.trim()).filter(Boolean),
        },
        exclude_rules: {
          ...profile.exclude_rules,
          items: editState.excludeRulesText.split("\n").map((s) => s.trim()).filter(Boolean),
        },
        private_notes: editState.privateNotesText.split("\n").map((s) => s.trim()).filter(Boolean),
        impact_summary: editState.impactSummary.trim() || profile.impact_summary,
      };
      const response = await fetch(`${API_BASE}/jobs/${jobId}/profiles/final`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const updated = (await response.json()) as JobProfile;
      onSave(updated);
      setEditing(false);
    } catch {
      setErrorMsg("保存失败，请检查后端服务。");
    } finally {
      setSaving(false);
    }
  }

  function updateCompetency(index: number, field: keyof Omit<CompetencyEdit, "key">, value: string | number) {
    setEditState((prev) => {
      const next = [...prev.competencies];
      next[index] = { ...next[index], [field]: value };
      return { ...prev, competencies: next };
    });
  }

  // ── 只读视图 ──────────────────────────────────────────────────────────────
  if (!editing) {
    return (
      <div className="panel alt">
        <div className="section-title">
          <h3>最终执行画像</h3>
          <button type="button" onClick={enterEdit}>编辑</button>
        </div>
        <div className="muted" style={{ marginBottom: 12 }}>{profile.version_name}</div>

        <div className="profile-structured-block">
          <div className="profile-structured-section">
            <div className="profile-structured-title">{profile.hard_constraints.title}</div>
            <div className="pill-row">
              {profile.hard_constraints.items.length > 0 ? (
                profile.hard_constraints.items.map((item) => (
                  <span className="pill" key={item}>{item}</span>
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
                  <div className="profile-competency-item" key={item.key}>
                    <div className="card-row">
                      <strong>{item.label}</strong>
                      <span className="pill">{item.weight}</span>
                    </div>
                    <div className="muted" style={{ marginTop: 6 }}>{item.note}</div>
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
                  <span className="pill" key={item}>{item}</span>
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
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              <span className="muted">暂无排除项</span>
            )}
          </div>

          {profile.private_notes.length > 0 && (
            <div className="profile-structured-section">
              <div className="profile-structured-title">老板私房标准</div>
              <ul className="profile-bullet-list">
                {profile.private_notes.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="profile-structured-section">
            <div className="profile-structured-title">画像摘要</div>
            <div className="muted">{profile.impact_summary}</div>
          </div>
        </div>
      </div>
    );
  }

  // ── 编辑视图 ──────────────────────────────────────────────────────────────
  return (
    <div className="panel alt">
      <div className="section-title">
        <h3>最终执行画像（编辑中）</h3>
        <div className="toolbar" style={{ gap: 8 }}>
          <button type="button" onClick={cancelEdit}>取消</button>
          <button className="primary" type="button" disabled={saving} onClick={handleSave}>
            {saving ? "保存中..." : "保存"}
          </button>
        </div>
      </div>
      {errorMsg && (
        <div style={{ color: "var(--color-bad, #ef4444)", marginBottom: 8, fontSize: "0.9em" }}>{errorMsg}</div>
      )}

      <div className="profile-structured-block">
        <div className="profile-structured-section">
          <div className="profile-structured-title">硬性门槛</div>
          <div className="muted" style={{ marginBottom: 4, fontSize: "0.85em" }}>每行一条</div>
          <textarea
            className="textarea"
            value={editState.hardConstraintsText}
            onChange={(e) => setEditState((prev) => ({ ...prev, hardConstraintsText: e.target.value }))}
            style={{ minHeight: 80 }}
          />
        </div>

        <div className="profile-structured-section">
          <div className="profile-structured-title">核心维度</div>
          <div className="profile-competency-list">
            {editState.competencies.map((item, index) => (
              <div className="profile-competency-item" key={item.key}>
                <div className="card-row" style={{ gap: 8, alignItems: "center" }}>
                  <input
                    className="text-input"
                    value={item.label}
                    onChange={(e) => updateCompetency(index, "label", e.target.value)}
                    style={{ flex: 1 }}
                    placeholder="维度名称"
                  />
                  <div className="calibration-slider" style={{ minWidth: 130 }}>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={item.weight}
                      onChange={(e) => updateCompetency(index, "weight", Number(e.target.value))}
                    />
                    <strong>{item.weight}</strong>
                  </div>
                </div>
                <textarea
                  className="textarea"
                  value={item.note}
                  onChange={(e) => updateCompetency(index, "note", e.target.value)}
                  style={{ minHeight: 60, marginTop: 6 }}
                  placeholder="维度说明（重点证据、伪匹配警报等）"
                />
              </div>
            ))}
          </div>
        </div>

        <div className="profile-structured-section">
          <div className="profile-structured-title">可迁移场景</div>
          <div className="muted" style={{ marginBottom: 4, fontSize: "0.85em" }}>每行一条</div>
          <textarea
            className="textarea"
            value={editState.industryExpansionText}
            onChange={(e) => setEditState((prev) => ({ ...prev, industryExpansionText: e.target.value }))}
            style={{ minHeight: 80 }}
          />
        </div>

        <div className="profile-structured-section">
          <div className="profile-structured-title">排除项</div>
          <div className="muted" style={{ marginBottom: 4, fontSize: "0.85em" }}>每行一条</div>
          <textarea
            className="textarea"
            value={editState.excludeRulesText}
            onChange={(e) => setEditState((prev) => ({ ...prev, excludeRulesText: e.target.value }))}
            style={{ minHeight: 80 }}
          />
        </div>

        <div className="profile-structured-section">
          <div className="profile-structured-title">老板私房标准</div>
          <div className="muted" style={{ marginBottom: 4, fontSize: "0.85em" }}>每行一条</div>
          <textarea
            className="textarea"
            value={editState.privateNotesText}
            onChange={(e) => setEditState((prev) => ({ ...prev, privateNotesText: e.target.value }))}
            style={{ minHeight: 80 }}
          />
        </div>

        <div className="profile-structured-section">
          <div className="profile-structured-title">画像摘要</div>
          <textarea
            className="textarea"
            value={editState.impactSummary}
            onChange={(e) => setEditState((prev) => ({ ...prev, impactSummary: e.target.value }))}
            style={{ minHeight: 60 }}
          />
        </div>
      </div>
    </div>
  );
}
