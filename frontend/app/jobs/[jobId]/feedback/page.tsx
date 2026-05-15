import { PageHeader } from "@/components/page-header";
import { getFeedbackSummary } from "@/lib/api";

export async function generateStaticParams() {
  return [{ jobId: "job-001" }];
}

export default async function FeedbackPage() {
  const feedback = await getFeedbackSummary();

  return (
    <>
      <PageHeader
        title="反馈学习"
        description="这页负责把反馈沉淀成可执行规则。系统会把正负反馈聚类，再反推下一轮画像应该怎么改。"
        badge="闭环学习"
      />

      <section className="grid two-col">
        <div className="panel">
          <h2>反馈聚类</h2>
          <div className="list">
            <div className="list-item">
              <strong>正向信号</strong>
              <div className="pill-row" style={{ marginTop: 10 }}>
                {feedback.positive_clusters.map((item) => (
                  <span key={item} className="pill good">
                    {item}
                  </span>
                ))}
              </div>
            </div>
            <div className="list-item">
              <strong>负向信号</strong>
              <div className="pill-row" style={{ marginTop: 10 }}>
                {feedback.negative_clusters.map((item) => (
                  <span key={item} className="pill bad">
                    {item}
                  </span>
                ))}
              </div>
            </div>
            <div className="list-item">
              <strong>建议画像修正</strong>
              <ul>
                {feedback.suggested_profile_shift.map((item) => (
                  <li key={item} style={{ marginTop: 8 }}>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>

        <div className="panel">
          <h2>反馈明细</h2>
          <div className="list">
            {feedback.items.map((item) => (
              <div key={item.id} className="list-item">
                <div className="card-row">
                  <strong>
                    {item.candidate_name} · {item.reason}
                  </strong>
                  <span className={`pill ${item.feedback_type === "positive" ? "good" : "bad"}`}>
                    {item.feedback_type}
                  </span>
                </div>
                <div className="muted" style={{ marginTop: 8 }}>
                  {item.detail}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
