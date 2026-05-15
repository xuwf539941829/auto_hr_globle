import Link from "next/link";

import { CandidateGrade } from "@/components/candidate-grade";
import { CandidateManualActions } from "@/components/candidate-manual-actions";
import { PageHeader } from "@/components/page-header";
import { getCandidate, getLLMTrace } from "@/lib/api";

export default async function CandidateDetailPage({
  params,
  searchParams
}: {
  params: Promise<{ candidateId: string }>;
  searchParams: Promise<{ job_id?: string }>;
}) {
  const { candidateId } = await params;
  const { job_id } = await searchParams;
  const jobId = job_id ?? "job-001";
  const candidate = await getCandidate(candidateId, jobId);
  const trace = candidate.analysis.llm_trace_id ? await getLLMTrace(candidate.analysis.llm_trace_id) : null;

  return (
    <>
      <PageHeader
        title={`候选人详情 - ${candidate.card.name}`}
        description="这里把最终执行画像、结构化简历、逐条标准判断，以及这份简历对应的 LLM 审计日志放在一起，方便直接复核。"
        badge={`${candidate.card.score} 分`}
      />

      <section className="grid two-col">
        <div className="panel">
          <div className="section-title">
            <h2>简历时间线</h2>
            <CandidateGrade grade={candidate.card.grade} />
          </div>

          <div className="timeline">
            {candidate.timeline.map((item) => (
              <div key={item} className="timeline-item">
                {item}
              </div>
            ))}
          </div>

          <div className="panel alt" style={{ marginTop: 16 }}>
            <h3>原始简历摘要</h3>
            <p className="muted">{candidate.original_resume}</p>
          </div>

          {candidate.parsed_resume ? (
            <>
              <div className="panel alt" style={{ marginTop: 16 }}>
                <h3>结构化工作经历</h3>
                <div className="list">
                  {candidate.parsed_resume.work_experiences.map((item) => (
                    <div key={`${item.company}-${item.start}`} className="list-item">
                      <strong>
                        {item.company} | {item.position}
                      </strong>
                      <div className="muted" style={{ marginTop: 6 }}>
                        {item.start} - {item.end || "至今"}
                      </div>
                      {item.summary ? <div style={{ marginTop: 6 }}>{item.summary}</div> : null}
                    </div>
                  ))}
                </div>
              </div>

              <div className="panel alt" style={{ marginTop: 16 }}>
                <h3>结构化证据</h3>
                <div className="pill-row">
                  {candidate.parsed_resume.action_terms.map((item) => (
                    <span className="pill" key={item}>
                      {item}
                    </span>
                  ))}
                  {candidate.parsed_resume.numeric_evidence.map((item) => (
                    <span className="pill good" key={item}>
                      {item}
                    </span>
                  ))}
                  {candidate.parsed_resume.risk_signals.map((item) => (
                    <span className="pill warn" key={item}>
                      {item}
                    </span>
                  ))}
                </div>
              </div>
            </>
          ) : null}
        </div>

        <div className="panel">
          <h2>筛选判断</h2>
          <div className="list">
            <div className="list-item">
              <div className="card-row">
                <strong>{candidate.analysis.summary}</strong>
                <span className={`pill ${candidate.analysis.pass_flag ? "good" : "bad"}`}>
                  {candidate.analysis.pass_flag ? "自动通过" : "未自动通过"}
                </span>
              </div>
              <div className="muted" style={{ marginTop: 8 }}>
                {candidate.analysis.reasoning_summary}
              </div>
            </div>

            <div className="list-item">
              <strong>逐条标准审计</strong>
              <div className="standard-check-list" style={{ marginTop: 10 }}>
                {candidate.analysis.hard_constraint_check.map((item) => (
                  <div key={item.item} className={`standard-check ${item.passed ? "pass" : "fail"}`}>
                    <div className="card-row">
                      <strong>{item.item}</strong>
                      <span className={`pill ${item.passed ? "good" : "bad"}`}>{item.passed ? "通过" : "未过"}</span>
                    </div>
                    <div className="muted" style={{ marginTop: 6 }}>
                      {item.reason}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="list-item">
              <strong>能力维度评分</strong>
              <div className="standard-check-list" style={{ marginTop: 10 }}>
                {candidate.analysis.dimension_checks.map((item) => (
                  <div key={item.key} className="standard-check pass">
                    <div className="card-row">
                      <strong>{item.label}</strong>
                      <span className="pill">
                        {item.score}/{item.weight}
                      </span>
                    </div>
                    <div className="muted" style={{ marginTop: 6 }}>
                      {item.reason}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="list-item">
              <strong>通过依据</strong>
              <div className="list" style={{ marginTop: 10 }}>
                {candidate.analysis.evidence_items.map((item) => (
                  <div key={item.title} className="standard-check pass">
                    <strong>{item.title}</strong>
                    <div className="muted" style={{ marginTop: 6 }}>
                      {item.content}
                    </div>
                    <div className="pill-row" style={{ marginTop: 8 }}>
                      <span className="pill good">{item.impact}</span>
                      <span className="pill">置信度 {Math.round(item.confidence * 100)}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="list-item">
              <strong>未通过或待复核原因</strong>
              <ul style={{ marginTop: 10 }}>
                {[...candidate.analysis.timeline_risks, ...candidate.analysis.risk_items].map((item) => (
                  <li key={item} style={{ marginTop: 8 }}>
                    {item}
                  </li>
                ))}
              </ul>
            </div>

            <div className="list-item">
              <strong>待确认问题</strong>
              <ul style={{ marginTop: 10 }}>
                {candidate.analysis.uncertainties.map((item) => (
                  <li key={item} style={{ marginTop: 8 }}>
                    {item}
                  </li>
                ))}
              </ul>
            </div>

            <div className="list-item">
              <strong>面试追问重点</strong>
              <ul style={{ marginTop: 10 }}>
                {candidate.analysis.interview_focus.map((item) => (
                  <li key={item} style={{ marginTop: 8 }}>
                    {item}
                  </li>
                ))}
              </ul>
            </div>

            {candidate.screening_blueprint ? (
              <div className="list-item">
                <strong>本次使用的最终执行画像</strong>
                <div className="list" style={{ marginTop: 10 }}>
                  <div className="standard-check pass">
                    <strong>硬性门槛</strong>
                    <ul style={{ marginTop: 8 }}>
                      {candidate.screening_blueprint.hard_filters.map((item) => (
                        <li key={item} style={{ marginTop: 6 }}>
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="standard-check pass">
                    <strong>重点维度</strong>
                    <div className="pill-row" style={{ marginTop: 8 }}>
                      {candidate.screening_blueprint.scoring_dimensions.map((item) => (
                        <span className="pill" key={item.key}>
                          {item.label} {item.weight}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="standard-check pass">
                    <strong>目标 / 可迁移场景</strong>
                    <div className="pill-row" style={{ marginTop: 8 }}>
                      {candidate.screening_blueprint.industry_targets.map((item) => (
                        <span className="pill" key={item}>
                          {item}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="standard-check fail">
                    <strong>排除项</strong>
                    <ul style={{ marginTop: 8 }}>
                      {candidate.screening_blueprint.exclude_rules.map((item) => (
                        <li key={item} style={{ marginTop: 6 }}>
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>

                  {candidate.screening_blueprint.private_notes.length > 0 ? (
                    <div className="standard-check pass">
                      <strong>HR 私房标准 / 面试提醒</strong>
                      <ul style={{ marginTop: 8 }}>
                        {candidate.screening_blueprint.private_notes.map((item) => (
                          <li key={item} style={{ marginTop: 6 }}>
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              </div>
            ) : null}

            <div className="list-item">
              <div className="section-title">
                <strong>LLM 审计日志</strong>
                {candidate.analysis.llm_trace_id ? (
                  <Link href={`/settings/llm/traces/${candidate.analysis.llm_trace_id}`} className="muted">
                    打开独立日志页
                  </Link>
                ) : null}
              </div>

              {candidate.analysis.llm_trace_id ? (
                trace ? (
                  <div className="list" style={{ marginTop: 10 }}>
                    <div className="standard-check pass">
                      <strong>请求参数</strong>
                      <pre className="code-block">{JSON.stringify(trace.request ?? {}, null, 2)}</pre>
                    </div>
                    <div className="standard-check pass">
                      <strong>返回结果</strong>
                      <pre className="code-block">{trace.response ?? "没有记录到返回内容。"}</pre>
                    </div>
                    <div className="standard-check fail">
                      <strong>错误日志</strong>
                      {(trace.errors ?? []).length > 0 ? (
                        <pre className="code-block">{JSON.stringify(trace.errors ?? [], null, 2)}</pre>
                      ) : (
                        <div className="muted" style={{ marginTop: 8 }}>
                          这一轮没有记录到错误。
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="muted" style={{ marginTop: 10 }}>
                    已记录 trace_id，但还没有读取到对应日志文件。
                  </div>
                )
              ) : (
                <div className="muted" style={{ marginTop: 10 }}>
                  这份简历当前不是 LLM 审计结果，或本轮走的是规则兜底，所以没有对应的请求/返回日志。
                </div>
              )}
            </div>

            <div className="list-item">
              <strong>人工接管</strong>
              <div style={{ marginTop: 10 }}>
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
        </div>
      </section>
    </>
  );
}
