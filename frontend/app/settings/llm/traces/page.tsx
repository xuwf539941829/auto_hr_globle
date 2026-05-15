import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { getLLMTraces } from "@/lib/api";

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

export default async function LLMTraceListPage() {
  const traces = await getLLMTraces();

  return (
    <>
      <PageHeader
        title="LLM 调试台"
        description="每条记录都包含请求参数、原始返回和错误信息。这里会把 JD 转译、样本增强和简历筛选三类日志统一列出来。"
        badge={`${traces.length} 条`}
      />

      <div className="panel">
        <div className="list">
          {traces.map((trace) => (
            <div className="list-item" key={trace.trace_id}>
              <div className="card-row">
                <div>
                  <strong>{trace.trace_id}</strong>
                  <div className="muted" style={{ marginTop: 8 }}>
                    {getTraceKindLabel(trace.metadata?.kind)} | {trace.endpoint ?? "无接口地址"} | {trace.updated_at ?? "无时间"}
                  </div>
                  {trace.metadata?.candidate_id ? (
                    <div className="muted" style={{ marginTop: 6 }}>
                      候选人：{trace.metadata.candidate_id} | 画像版本：{trace.metadata.profile_version_id ?? "未知"}
                    </div>
                  ) : null}
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
              <div style={{ marginTop: 10 }}>
                <Link href={`/settings/llm/traces/${trace.trace_id}`}>
                  <button type="button">查看详情</button>
                </Link>
              </div>
            </div>
          ))}
          {traces.length === 0 ? <div className="list-item muted">暂时还没有 LLM Trace 文件。</div> : null}
        </div>
      </div>
    </>
  );
}
