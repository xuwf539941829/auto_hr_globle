"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { CandidateDetailModal } from "@/components/candidate-detail-modal";
import { CandidateGrade } from "@/components/candidate-grade";
import { CandidateManualActions } from "@/components/candidate-manual-actions";
import type { CandidateDetail, ScreeningBlueprint, ScreeningTask } from "@/lib/types";

type RequirementColumn =
  | { kind: "hard"; key: string; label: string }
  | { kind: "dimension"; key: string; label: string; weight: number };

function buildRequirementColumns(
  blueprint: ScreeningBlueprint | null | undefined,
  candidates: CandidateDetail[],
): RequirementColumn[] {
  const hardKeys = new Set<string>();
  const dimensionKeys = new Map<string, { label: string; weight: number }>();

  (blueprint?.hard_filters ?? []).forEach((item) => hardKeys.add(item));
  (blueprint?.scoring_dimensions ?? []).forEach((item) => {
    if (!dimensionKeys.has(item.key)) {
      dimensionKeys.set(item.key, { label: item.label, weight: item.weight });
    }
  });

  if (dimensionKeys.size === 0 && candidates.length > 0) {
    candidates[0].analysis.dimension_checks.forEach((item) => {
      if (!dimensionKeys.has(item.key)) {
        dimensionKeys.set(item.key, { label: item.label, weight: item.weight });
      }
    });
  }

  return [
    ...Array.from(hardKeys).map((item) => ({ kind: "hard" as const, key: item, label: item })),
    ...Array.from(dimensionKeys.entries()).map(([key, value]) => ({
      kind: "dimension" as const,
      key,
      label: value.label,
      weight: value.weight,
    })),
  ];
}

function hardCheckStatus(candidate: CandidateDetail, key: string) {
  return candidate.analysis.hard_constraint_check.find((item) => item.item === key) ?? null;
}

function dimensionStatus(candidate: CandidateDetail, key: string) {
  return candidate.analysis.dimension_checks.find((item) => item.key === key) ?? null;
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

function buildAuditRows(candidate: CandidateDetail) {
  const hardRows = candidate.analysis.hard_constraint_check.map((item) => ({
    id: `hard-${item.item}`,
    label: item.item,
    statusText: item.passed ? "通过" : "未过",
    tone: item.passed ? "good" : "bad",
    icon: item.passed ? "✓" : "✕",
    value: "硬门槛",
    reason: item.reason,
  }));

  const dimensionRows = candidate.analysis.dimension_checks.map((item) => ({
    id: `dimension-${item.key}`,
    label: item.label,
    statusText: `${item.score}/${item.weight}`,
    tone: ratioTone(item.score, item.weight),
    icon: ratioIcon(item.score, item.weight),
    value: `权重 ${item.weight}`,
    reason: item.reason,
  }));

  return [...hardRows, ...dimensionRows];
}

function taskStatusLabel(task: ScreeningTask) {
  if (task.status === "failed" && task.message?.includes("后端重启已中断")) {
    return "已中断";
  }
  return task.status;
}

export function CandidateScreeningBoard({
  jobId,
  candidates,
  task,
  blueprint,
  isPaused = false,
  onTogglePause,
}: {
  jobId: string;
  candidates: CandidateDetail[];
  task: ScreeningTask;
  blueprint?: ScreeningBlueprint | null;
  isPaused?: boolean;
  onTogglePause?: () => void;
}) {
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [pageSize, setPageSize] = useState(10);
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedGrades, setSelectedGrades] = useState<string[]>([]);
  const [gradeFilterOpen, setGradeFilterOpen] = useState(false);
  const [collectedFilter, setCollectedFilter] = useState<"all" | "collected" | "not_collected">("all");
  const gradeDropdownRef = useRef<HTMLDivElement>(null);
  const tableScrollRef = useRef<HTMLDivElement>(null);
  const stickyBarRef = useRef<HTMLDivElement>(null);
  const stickyInnerRef = useRef<HTMLDivElement>(null);

  const columns = useMemo(() => buildRequirementColumns(blueprint, candidates), [blueprint, candidates]);

  // Base: candidates after collected filter only (used for grade counts)
  const baseFilteredCandidates = useMemo(() => {
    if (collectedFilter === "collected") return candidates.filter((c) => c.card.collected);
    if (collectedFilter === "not_collected") return candidates.filter((c) => !c.card.collected);
    return candidates;
  }, [candidates, collectedFilter]);

  // Grade counts from base (reflect collected filter)
  const gradeCounts = useMemo(() => {
    const counts: Record<string, number> = { S: 0, A: 0, B: 0, C: 0 };
    baseFilteredCandidates.forEach((c) => { if (c.card.grade in counts) counts[c.card.grade]++; });
    return counts;
  }, [baseFilteredCandidates]);

  const filteredCandidates = useMemo(
    () => selectedGrades.length === 0 ? baseFilteredCandidates : baseFilteredCandidates.filter((c) => selectedGrades.includes(c.card.grade)),
    [baseFilteredCandidates, selectedGrades],
  );

  const totalPages = Math.max(1, Math.ceil(filteredCandidates.length / pageSize));
  const safeCurrentPage = Math.min(currentPage, totalPages);
  const pageStart = (safeCurrentPage - 1) * pageSize;
  const pageCandidates = filteredCandidates.slice(pageStart, pageStart + pageSize);
  const isLatestPage = safeCurrentPage === totalPages;
  const selectedCandidate = selectedCandidateId
    ? candidates.find((item) => item.card.id === selectedCandidateId) ?? null
    : null;

  function toggleGrade(grade: string) {
    setSelectedGrades((prev) =>
      prev.includes(grade) ? prev.filter((g) => g !== grade) : [...prev, grade],
    );
    setCurrentPage(1);
  }

  useEffect(() => {
    if (currentPage !== safeCurrentPage) {
      setCurrentPage(safeCurrentPage);
    }
  }, [currentPage, safeCurrentPage]);

  useEffect(() => {
    if (selectedCandidateId && !candidates.some((item) => item.card.id === selectedCandidateId)) {
      setSelectedCandidateId(null);
    }
  }, [candidates, selectedCandidateId]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (gradeDropdownRef.current && !gradeDropdownRef.current.contains(event.target as Node)) {
        setGradeFilterOpen(false);
      }
    }
    if (gradeFilterOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [gradeFilterOpen]);

  // Sticky horizontal scrollbar: sync scroll between table and sticky bar
  useEffect(() => {
    const table = tableScrollRef.current;
    const bar = stickyBarRef.current;
    if (!table || !bar) return;
    let busy = false;
    const fromTable = () => { if (!busy) { busy = true; bar.scrollLeft = table.scrollLeft; busy = false; } };
    const fromBar = () => { if (!busy) { busy = true; table.scrollLeft = bar.scrollLeft; busy = false; } };
    table.addEventListener("scroll", fromTable, { passive: true });
    bar.addEventListener("scroll", fromBar, { passive: true });
    return () => {
      table.removeEventListener("scroll", fromTable);
      bar.removeEventListener("scroll", fromBar);
    };
  }, []);

  // Sticky horizontal scrollbar: keep inner width in sync with table scroll width
  useEffect(() => {
    const table = tableScrollRef.current;
    const inner = stickyInnerRef.current;
    if (!table || !inner) return;
    const update = () => { inner.style.width = table.scrollWidth + "px"; };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(table);
    return () => ro.disconnect();
  }, [pageCandidates, columns]);

  return (
    <>
      <section className="panel candidate-table-panel">
        <div className="section-title">
          <div>
            <h2>候选人筛选表</h2>
            <div className="muted" style={{ marginTop: 8 }}>
              新简历会持续追加到后面。分页只影响当前展示，不会打断前面页里的查看和手动操作。
            </div>
          </div>
          <div className="pill-row">
            <span className="pill">{taskStatusLabel(task)}</span>
            <span className="pill">{candidates.length} 人</span>
            {blueprint?.profile_version_id ? <span className="pill good">画像版本 {blueprint.profile_version_id}</span> : null}
          </div>
        </div>

        <div
          className="toolbar"
          style={{ marginTop: 12, marginBottom: 12, justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}
        >
          <div className="pill-row" style={{ alignItems: "center", gap: 8 }}>
            <span className="pill">
              第 {safeCurrentPage} / {totalPages} 页
            </span>
            <span className={`pill ${isLatestPage ? "good" : ""}`}>
              {isLatestPage ? "当前在最新页" : "停留在前面页"}
            </span>
            {(selectedGrades.length > 0 || collectedFilter !== "all") && (
              <span className="pill warn">
                已筛选 {filteredCandidates.length} / {candidates.length} 人
              </span>
            )}
            {/* 等级筛选 */}
            <div ref={gradeDropdownRef} style={{ position: "relative" }}>
              <button
                type="button"
                className={selectedGrades.length > 0 ? "primary" : ""}
                onClick={() => setGradeFilterOpen((v) => !v)}
                style={{ minWidth: 100 }}
              >
                等级筛选{selectedGrades.length > 0 ? `：${selectedGrades.sort().join("/")}` : "（全部）"} ▾
              </button>
              {gradeFilterOpen && (
                <div
                  style={{
                    position: "absolute",
                    top: "calc(100% + 4px)",
                    left: 0,
                    zIndex: 100,
                    background: "var(--color-bg, #fff)",
                    border: "1px solid var(--color-border, #e5e7eb)",
                    borderRadius: 6,
                    padding: "8px 0",
                    minWidth: 140,
                    boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
                  }}
                >
                  {(["S", "A", "B", "C"] as const).map((grade) => (
                    <label
                      key={grade}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        padding: "6px 14px",
                        cursor: "pointer",
                        userSelect: "none",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={selectedGrades.includes(grade)}
                        onChange={() => toggleGrade(grade)}
                        style={{ cursor: "pointer" }}
                      />
                      <span>{grade} 级</span>
                      <span className="muted" style={{ marginLeft: "auto", fontSize: 12 }}>{gradeCounts[grade]}</span>
                    </label>
                  ))}
                  {selectedGrades.length > 0 && (
                    <div style={{ borderTop: "1px solid var(--color-border, #e5e7eb)", marginTop: 4, paddingTop: 4 }}>
                      <button
                        type="button"
                        onClick={() => { setSelectedGrades([]); setCurrentPage(1); }}
                        style={{ width: "100%", padding: "6px 14px", textAlign: "left", background: "none", border: "none", cursor: "pointer", color: "var(--color-muted, #6b7280)" }}
                      >
                        清除筛选
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
            {/* 收藏筛选 */}
            <select
              value={collectedFilter}
              onChange={(e) => { setCollectedFilter(e.target.value as "all" | "collected" | "not_collected"); setCurrentPage(1); }}
              style={{ minWidth: 100, border: "1px solid var(--line)", background: "#fff", borderRadius: 8, padding: "10px 12px", cursor: "pointer", font: "inherit" }}
            >
              <option value="all">收藏：全部</option>
              <option value="collected">已收藏</option>
              <option value="not_collected">未收藏</option>
            </select>
          </div>
          <div className="toolbar" style={{ gap: 8, flexWrap: "wrap" }}>
            <label className="muted" htmlFor="candidate-page-size">
              每页
            </label>
            <select
              id="candidate-page-size"
              className="text-input"
              value={pageSize}
              onChange={(event) => {
                setPageSize(Number(event.target.value));
                setCurrentPage(1);
              }}
              style={{ width: 88 }}
            >
              <option value={10}>10</option>
              <option value={20}>20</option>
              <option value={50}>50</option>
            </select>
            <button type="button" onClick={() => setCurrentPage(1)} disabled={safeCurrentPage <= 1}>
              首页
            </button>
            <button type="button" onClick={() => setCurrentPage((page) => Math.max(1, page - 1))} disabled={safeCurrentPage <= 1}>
              上一页
            </button>
            <button
              type="button"
              onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
              disabled={safeCurrentPage >= totalPages}
            >
              下一页
            </button>
            <button type="button" onClick={() => setCurrentPage(totalPages)} disabled={isLatestPage}>
              最新一页
            </button>
          </div>
        </div>

        <div className="candidate-table-scroll" ref={tableScrollRef}>
          <table className="candidate-table">
            <thead>
              <tr>
                <th>候选人</th>
                <th>画像结论</th>
                {columns.map((column) => (
                  <th key={`${column.kind}-${column.key}`}>
                    <div className="table-col-title">{column.label}</div>
                    <div className="table-col-sub">
                      {column.kind === "dimension" ? `核心维度 ${column.weight}` : "硬门槛"}
                    </div>
                  </th>
                ))}
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {pageCandidates.length === 0 ? (
                <tr>
                  <td className="muted" colSpan={columns.length + 3}>
                    当前还没有筛选结果。开始筛选后，这里会按最终执行画像逐条追加已完成筛选的候选人。
                  </td>
                </tr>
              ) : (
                pageCandidates.map((candidate) => (
                  <tr key={candidate.card.id}>
                    <td className="candidate-main-cell">
                      <button
                        type="button"
                        className="candidate-link-button"
                        onClick={() => setSelectedCandidateId(candidate.card.id)}
                      >
                        <strong>{candidate.card.name}</strong>
                      </button>
                      {candidate.card.current_company !== "Unknown" && candidate.card.current_position !== "Unknown" ? (
                        <div className="muted" style={{ marginTop: 6 }}>
                          {candidate.card.current_company} | {candidate.card.current_position}
                        </div>
                      ) : null}
                      <div className="pill-row" style={{ marginTop: 8 }}>
                        <span className="pill">{candidate.card.age}岁</span>
                        <span className="pill">{candidate.card.education}</span>
                        <span className="pill">{candidate.card.work_years}年</span>
                      </div>
                    </td>
                    <td>
                      <div className="table-grade-cell">
                        <CandidateGrade grade={candidate.card.grade} />
                        <span className={`pill ${candidate.analysis.pass_flag ? "good" : "warn"}`}>
                          {candidate.analysis.pass_flag ? "自动通过" : "待复核"}
                        </span>
                        <span className="pill">{candidate.card.score}分</span>
                        {candidate.analysis.summary ? (
                          <span className="tip-trigger" title={candidate.analysis.summary}>
                            详情
                          </span>
                        ) : null}
                      </div>
                    </td>
                    {columns.map((column) => {
                      // Treat as old version if: current blueprint has a version AND either the
                      // candidate has no screening_blueprint/version_id (screened before versioning
                      // was added) OR the version_ids differ.
                      const isOldVersion =
                        !!blueprint?.profile_version_id &&
                        (
                          !candidate.screening_blueprint?.profile_version_id ||
                          candidate.screening_blueprint.profile_version_id !== blueprint.profile_version_id
                        );

                      if (column.kind === "hard") {
                        const item = hardCheckStatus(candidate, column.key);
                        const isEmpty = !item;
                        return (
                          <td key={`${candidate.card.id}-${column.kind}-${column.key}`} className="status-cell">
                            <span
                              className={`status-icon ${item?.passed ? "good" : item ? "bad" : "warn"}`}
                              title={
                                item?.reason ??
                                (isOldVersion && isEmpty
                                  ? `此候选人使用旧版画像(${candidate.screening_blueprint?.profile_version_id})筛选，当前列不适用`
                                  : "当前还没有这条招聘要求的判断结果")
                              }
                            >
                              {item?.passed ? "✓" : item ? "✕" : isOldVersion && isEmpty ? "—" : "·"}
                            </span>
                          </td>
                        );
                      }

                      const item = dimensionStatus(candidate, column.key);
                      const tone = item ? ratioTone(item.score, item.weight) : "warn";
                      const isEmpty = !item;
                      return (
                        <td key={`${candidate.card.id}-${column.kind}-${column.key}`} className="status-cell">
                          <span
                            className={`status-icon ${tone}`}
                            title={
                              item?.reason ??
                              (isOldVersion && isEmpty
                                ? `此候选人使用旧版画像(${candidate.screening_blueprint?.profile_version_id})筛选，当前列不适用`
                                : "当前还没有这条维度的判断结果")
                            }
                          >
                            {item ? ratioIcon(item.score, item.weight) : isOldVersion && isEmpty ? "—" : "·"}
                          </span>
                          {item ? <span className="status-score">{item.score}</span> : null}
                        </td>
                      );
                    })}
                    <td>
                      <div className="table-actions">
                        <button type="button" onClick={() => setSelectedCandidateId(candidate.card.id)}>
                          查看详情
                        </button>
                        <CandidateManualActions
                          candidateId={candidate.card.id}
                          collected={candidate.card.collected}
                          greeted={candidate.card.greeted}
                          collectedAt={candidate.card.collected_at}
                          greetedAt={candidate.card.greeted_at}
                          jobId={jobId}
                        />
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="candidate-sticky-scrollbar" ref={stickyBarRef}>
          <div className="candidate-sticky-scrollbar-inner" ref={stickyInnerRef} />
        </div>
      </section>

      {selectedCandidate ? (
        <CandidateDetailModal
          candidate={selectedCandidate}
          jobId={jobId}
          onClose={() => setSelectedCandidateId(null)}
        />
      ) : null}
    </>
  );
}
