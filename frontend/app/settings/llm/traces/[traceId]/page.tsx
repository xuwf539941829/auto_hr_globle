import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { TraceAutoRefresh } from "@/components/trace-auto-refresh";
import { getLLMTrace } from "@/lib/api";

export async function generateStaticParams() {
  return [{ traceId: "trace-001" }];
}

export default async function LLMTraceDetailPage({
  params,
}: {
  params: Promise<{ traceId: string }>;
}) {
  const { traceId } = await params;
  const trace = await getLLMTrace(traceId);

  if (trace == null) {
    return (
      <>
        <PageHeader title="LLM Trace 详情" description="没有找到这条日志。" badge="缺失" />
        <div className="panel">
          <Link href="/settings/llm/traces">
            <button type="button">返回 Trace 列表</button>
          </Link>
        </div>
      </>
    );
  }

  const hasResponse = typeof trace.response === "string" && trace.response.trim().length > 0;
  const hasErrors = Array.isArray(trace.errors) && trace.errors.length > 0;

  return (
    <>
      <TraceAutoRefresh enabled={!hasResponse && !hasErrors} />

      <PageHeader
        title={`LLM Trace - ${trace.trace_id}`}
        description="这里会把请求参数、原始返回和错误链放在一起，方便直接核对模型到底看到了什么、回了什么。"
        badge={trace.updated_at ?? "无时间戳"}
      />

      <div className="grid two-col">
        <div className="panel">
          <div className="section-title">
            <h2>请求参数</h2>
            <Link className="muted" href="/settings/llm/traces">
              返回
            </Link>
          </div>
          <div className="muted" style={{ marginBottom: 10 }}>
            {trace.metadata?.kind ?? "unknown"} | {trace.endpoint ?? "无接口地址"}
          </div>
          <pre className="code-block">{JSON.stringify(trace.request ?? {}, null, 2)}</pre>
        </div>

        <div className="panel">
          <h2>返回结果</h2>
          <pre className="code-block">{hasResponse ? trace.response : "没有记录到返回内容。"}</pre>
          {!hasResponse && !hasErrors ? (
            <div className="muted" style={{ marginTop: 10 }}>
              这条日志可能还在写入返回内容，页面会自动短暂刷新。
            </div>
          ) : null}
        </div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <h2>错误信息</h2>
        <div className="list">
          {(trace.errors ?? []).map((item, index) => (
            <div className="list-item" key={`${item.at ?? "na"}-${index}`}>
              <strong>{item.at ?? "未知时间"}</strong>
              <div className="muted" style={{ marginTop: 8 }}>
                {item.message ?? "未知错误"}
              </div>
            </div>
          ))}
          {(trace.errors ?? []).length === 0 ? <div className="list-item muted">没有记录到错误。</div> : null}
        </div>
      </div>
    </>
  );
}
