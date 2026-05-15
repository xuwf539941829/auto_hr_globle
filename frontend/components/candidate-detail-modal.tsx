import { useState } from "react";
import Link from "next/link";

import { CandidateGrade } from "@/components/candidate-grade";
import { CandidateManualActions } from "@/components/candidate-manual-actions";
import type { CandidateDetail } from "@/lib/types";

interface CandidateDetailModalProps {
  candidate: CandidateDetail;
  jobId: string;
  onClose: () => void;
}

function ratioTone(score: number, weight: number) {
  const ratio = weight <= 0 ? 0 : score / weight;
  if (ratio >= 0.85) return "good";
  if (ratio >= 0.6) return "warn";
  return "bad";
}

function ratioIcon(score: number, weight: number) {
  const ratio = weight <= 0 ? 0 : score / weight;
  if (ratio >= 0.85) return "●";
  if (ratio >= 0.6) return "▲";
  return "■";
}

export function CandidateDetailModal({ candidate, jobId, onClose }: CandidateDetailModalProps) {
  const [activeTab, setActiveTab] = useState<"overview" | "resume" | "dimensions" | "evidence" | "risks">("overview");
  const analysis = candidate.analysis;
  const parsed = candidate.parsed_resume;
  const hrSections = candidate.hr_resume_sections ?? [];

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-panel candidate-detail-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="candidate-header-info">
            <h2>{candidate.card.name}</h2>
            <div className="muted">
              {candidate.card.current_company} | {candidate.card.current_position}
            </div>
            <div className="pill-row" style={{ marginTop: 8 }}>
              <span className="pill">{candidate.card.age}岁</span>
              <span className="pill">{candidate.card.education}</span>
              <span className="pill">{candidate.card.work_years}年</span>
            </div>
          </div>
          <div className="candidate-header-grade">
            <CandidateGrade grade={candidate.card.grade} />
            <span className={`pill ${analysis.pass_flag ? "good" : "warn"}`}>
              {analysis.pass_flag ? "自动通过" : "待人工复核"}
            </span>
            <span className="pill">{analysis.score}分</span>
          </div>
          <button type="button" className="close-button" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="candidate-summary-section">
          <div className="tip-box">
            <span className="tip-icon">💡</span>
            <div>
              <div className="tip-title">AI 评估摘要</div>
              <div className="tip-content">{analysis.summary}</div>
            </div>
          </div>
          {analysis.reasoning_summary ? (
            <div className="reasoning-box">
              <strong>评估逻辑：</strong>
              {analysis.reasoning_summary}
            </div>
          ) : null}
        </div>

        <div className="modal-tabs">
          <button className={activeTab === "overview" ? "active" : ""} onClick={() => setActiveTab("overview")}>
            总览
          </button>
          <button className={activeTab === "resume" ? "active" : ""} onClick={() => setActiveTab("resume")}>
            简历详情
          </button>
          <button className={activeTab === "dimensions" ? "active" : ""} onClick={() => setActiveTab("dimensions")}>
            维度评分
          </button>
          <button className={activeTab === "evidence" ? "active" : ""} onClick={() => setActiveTab("evidence")}>
            证据链
          </button>
          <button className={activeTab === "risks" ? "active" : ""} onClick={() => setActiveTab("risks")}>
            风险与追问
          </button>
        </div>

        <div className="modal-content">
          {activeTab === "overview" ? (
            <div className="tab-panel">
              <div className="panel-section">
                <h3>硬性门槛检查</h3>
                <div className="constraint-list">
                  {analysis.hard_constraint_check.map((item) => (
                    <div key={item.item} className={`constraint-item ${item.passed ? "pass" : "fail"}`}>
                      <span className="constraint-icon">{item.passed ? "✓" : "✕"}</span>
                      <div className="constraint-info">
                        <strong>{item.item}</strong>
                        <div className="constraint-reason">{item.reason}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="panel-section">
                <h3>分数构成</h3>
                <div className="score-breakdown">
                  {analysis.score_breakdown.map((item) => (
                    <div key={item.label} className="score-item">
                      <span className="score-label">{item.label}</span>
                      <span className="score-value">{item.value}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="panel-section">
                <h3>推荐操作</h3>
                <div className="action-buttons">
                  <CandidateManualActions
                    candidateId={candidate.card.id}
                    collected={candidate.card.collected}
                    greeted={candidate.card.greeted}
                    collectedAt={candidate.card.collected_at}
                    greetedAt={candidate.card.greeted_at}
                    jobId={jobId}
                  />
                </div>
              </div>
            </div>
          ) : null}

          {activeTab === "resume" ? (
            <div className="tab-panel">
              {hrSections.length > 0 ? (
                <div className="panel-section">
                  <h3>Boss 简历完整详情</h3>
                  <div className="list">
                    {hrSections.map((section) => (
                      <div key={section.title} className="list-item">
                        <strong>{section.title}</strong>
                        <div style={{ marginTop: 10 }}>
                          {section.items.length > 0 ? (
                            section.items.map((item, index) => (
                              <div key={`${section.title}-${index}`} style={{ marginTop: index === 0 ? 0 : 10, whiteSpace: "pre-wrap", lineHeight: 1.7 }}>
                                {item}
                              </div>
                            ))
                          ) : (
                            <div className="muted">暂无内容</div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              <div className="panel-section">
                <h3>简历原文摘要</h3>
                <div className="list-item">
                  <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>{candidate.original_resume || "暂无简历原文摘要。"}</div>
                </div>
              </div>

              <div className="panel-section">
                <h3>简历时间线</h3>
                <div className="timeline">
                  {candidate.timeline.length > 0 ? (
                    candidate.timeline.map((item) => (
                      <div key={item} className="timeline-item">
                        {item}
                      </div>
                    ))
                  ) : (
                    <div className="muted">暂无时间线信息。</div>
                  )}
                </div>
              </div>

              {parsed?.work_experiences?.length ? (
                <div className="panel-section">
                  <h3>工作经历</h3>
                  <div className="list">
                    {parsed.work_experiences.map((item) => (
                      <div key={`${item.company}-${item.position}-${item.start}`} className="list-item">
                        <strong>
                          {item.company} | {item.position}
                        </strong>
                        <div className="muted" style={{ marginTop: 6 }}>
                          {item.start} - {item.end || "至今"}
                        </div>
                        {item.summary ? <div style={{ marginTop: 8, whiteSpace: "pre-wrap", lineHeight: 1.7 }}>{item.summary}</div> : null}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {parsed?.education_experiences?.length ? (
                <div className="panel-section">
                  <h3>教育经历</h3>
                  <div className="list">
                    {parsed.education_experiences.map((item) => (
                      <div key={`${item.school}-${item.degree}-${item.start}`} className="list-item">
                        <strong>
                          {item.school} | {item.degree}
                        </strong>
                        <div className="muted" style={{ marginTop: 6 }}>
                          {item.start} - {item.end || "毕业"}
                        </div>
                        {item.summary ? <div style={{ marginTop: 8, whiteSpace: "pre-wrap", lineHeight: 1.7 }}>{item.summary}</div> : null}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {parsed ? (
                <div className="panel-section">
                  <h3>简历关键信号</h3>
                  <div className="pill-row" style={{ marginTop: 10 }}>
                    {parsed.action_terms.map((item) => (
                      <span className="pill" key={`action-${item}`}>
                        {item}
                      </span>
                    ))}
                    {parsed.numeric_evidence.map((item) => (
                      <span className="pill good" key={`number-${item}`}>
                        {item}
                      </span>
                    ))}
                    {parsed.risk_signals.map((item) => (
                      <span className="pill warn" key={`risk-${item}`}>
                        {item}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          {activeTab === "dimensions" ? (
            <div className="tab-panel">
              <div className="panel-section">
                <h3>核心能力维度评分</h3>
                <div className="dimension-list">
                  {analysis.dimension_checks.map((item) => {
                    const tone = ratioTone(item.score, item.weight);
                    return (
                      <div key={item.key} className={`dimension-item ${tone}`}>
                        <div className="dimension-header">
                          <div className="dimension-title">
                            <span className={`status-icon ${tone}`}>{ratioIcon(item.score, item.weight)}</span>
                            <strong>{item.label}</strong>
                          </div>
                          <div className="dimension-score">
                            <span className="score-number">{item.score}</span>
                            <span className="score-weight">/ {item.weight}</span>
                          </div>
                        </div>
                        <div className="dimension-bar">
                          <div className={`dimension-fill ${tone}`} style={{ width: `${(item.score / item.weight) * 100}%` }} />
                        </div>
                        <div className="dimension-reason">{item.reason}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          ) : null}

          {activeTab === "evidence" ? (
            <div className="tab-panel">
              <div className="panel-section">
                <h3>证据链</h3>
                <div className="evidence-list">
                  {analysis.evidence_items.length > 0 ? (
                    analysis.evidence_items.map((item, index) => (
                      <div key={`${item.title}-${index}`} className="evidence-item">
                        <div className="evidence-header">
                          <span className="evidence-type">{item.type}</span>
                          <span className="pill good">{item.impact}</span>
                          <span className="pill">置信度 {Math.round(item.confidence * 100)}%</span>
                        </div>
                        <h4>{item.title}</h4>
                        <div className="evidence-content">{item.content}</div>
                      </div>
                    ))
                  ) : (
                    <div className="muted">当前没有抽取到可展示的证据链。</div>
                  )}
                </div>
              </div>

              {analysis.value_signals.length > 0 ? (
                <div className="panel-section">
                  <h3>价值信号</h3>
                  <ul className="signal-list">
                    {analysis.value_signals.map((item, index) => (
                      <li key={`${item}-${index}`} className="signal-item good">
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}

          {activeTab === "risks" ? (
            <div className="tab-panel">
              {analysis.risk_items.length > 0 ? (
                <div className="panel-section">
                  <h3>风险提示</h3>
                  <ul className="risk-list">
                    {analysis.risk_items.map((item, index) => (
                      <li key={`${item}-${index}`} className="risk-item">
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {analysis.timeline_risks.length > 0 ? (
                <div className="panel-section">
                  <h3>时间线风险</h3>
                  <ul className="risk-list">
                    {analysis.timeline_risks.map((item, index) => (
                      <li key={`${item}-${index}`} className="risk-item warn">
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {analysis.uncertainties.length > 0 ? (
                <div className="panel-section">
                  <h3>待确认项</h3>
                  <ul className="uncertainty-list">
                    {analysis.uncertainties.map((item, index) => (
                      <li key={`${item}-${index}`} className="uncertainty-item">
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {analysis.interview_focus.length > 0 ? (
                <div className="panel-section">
                  <h3>面试追问重点</h3>
                  <div className="interview-focus-list">
                    {analysis.interview_focus.map((item, index) => (
                      <div key={`${item}-${index}`} className="focus-item">
                        <span className="focus-number">{index + 1}</span>
                        <div className="focus-text">{item}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="modal-footer">
          {analysis.llm_trace_id ? (
            <Link href={`/settings/llm/traces/${analysis.llm_trace_id}`}>
              <button type="button">查看 LLM 日志</button>
            </Link>
          ) : null}
        </div>
      </div>
    </div>
  );
}
