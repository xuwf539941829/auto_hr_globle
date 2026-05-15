import Link from "next/link";

import { LLMSettingsForm } from "@/components/llm-settings-form";
import { PageHeader } from "@/components/page-header";
import { getLLMSettings, getLLMTraces } from "@/lib/api";

const TRACE_KIND_LABEL: Record<string, string> = {
  jd_translation: "JD 转译",
  sample_resume_analysis: "优秀样本分析",
  candidate_screening: "简历筛选"
};

function getTraceKindLabel(kind?: string) {
  if (!kind) {
    return "未知类型";
  }
  return TRACE_KIND_LABEL[kind] ?? kind;
}

export default async function LLMSettingsPage() {
  const [settings, traces] = await Promise.all([getLLMSettings(), getLLMTraces()]);
  const screeningTraces = traces.filter((trace) => trace.metadata?.kind === "candidate_screening");

  return (
    <>
      <PageHeader
        title="模型设置"
        description="在这里配置模型连接，并直接查看最近的调试日志。现在简历筛选发给 LLM 的请求参数和返回结果，也会在这里统一沉淀。"
        badge={settings.enabled ? "已启用" : "未启用"}
      />

      <div className="settings-grid">
        <LLMSettingsForm initialSettings={settings} />

        <div className="panel">
          <div className="section-title">
            <h2>最近 Trace</h2>
            <Link className="muted" href="/settings/llm/traces">
              打开调试台
            </Link>
          </div>

          <div className="list">
            {traces.slice(0, 8).map((trace) => (
              <div className="list-item" key={trace.trace_id}>
                <div className="card-row">
                  <strong>{trace.trace_id}</strong>
                  <span className={`pill ${trace.error_count > 0 ? "warn" : "good"}`}>
                    {trace.error_count > 0 ? `${trace.error_count} 个错误` : "正常"}
                  </span>
                </div>
                <div className="muted" style={{ marginTop: 8 }}>
                  {getTraceKindLabel(trace.metadata?.kind)} | {trace.updated_at ?? "无时间戳"}
                </div>
                <div style={{ marginTop: 10 }}>
                  <Link href={`/settings/llm/traces/${trace.trace_id}`}>
                    <button type="button">查看 Trace</button>
                  </Link>
                </div>
              </div>
            ))}
            {traces.length === 0 ? <div className="list-item muted">暂时还没有 Trace 记录。</div> : null}
          </div>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <div className="section-title">
          <h2>简历筛选日志</h2>
          <span className="pill">{screeningTraces.length} 条</span>
        </div>
        <div className="muted" style={{ marginBottom: 12 }}>
          这里单独列出“候选人筛选”发给 LLM 的请求参数和返回结果，方便你集中排查筛选逻辑。
        </div>
        <div className="list">
          {screeningTraces.slice(0, 10).map((trace) => (
            <div className="list-item" key={trace.trace_id}>
              <div className="card-row">
                <div>
                  <strong>{trace.trace_id}</strong>
                  <div className="muted" style={{ marginTop: 8 }}>
                    候选人：{trace.metadata?.candidate_id ?? "未知"} | 画像版本：{trace.metadata?.profile_version_id ?? "未知"}
                  </div>
                </div>
                <div className="pill-row">
                  <span className={`pill ${trace.has_response ? "good" : "warn"}`}>
                    {trace.has_response ? "已有返回" : "暂无返回"}
                  </span>
                  <span className={`pill ${trace.error_count > 0 ? "warn" : "good"}`}>
                    {trace.error_count > 0 ? `${trace.error_count} 个错误` : "正常"}
                  </span>
                </div>
              </div>
              <div className="muted" style={{ marginTop: 8 }}>
                {trace.updated_at ?? "无时间戳"}
              </div>
              <div style={{ marginTop: 10 }}>
                <Link href={`/settings/llm/traces/${trace.trace_id}`}>
                  <button type="button">查看请求和返回</button>
                </Link>
              </div>
            </div>
          ))}
          {screeningTraces.length === 0 ? <div className="list-item muted">当前还没有简历筛选日志。</div> : null}
        </div>
      </div>
    </>
  );
}
