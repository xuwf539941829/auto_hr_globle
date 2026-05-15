import Link from "next/link";

import { MetricCard } from "@/components/metric-card";
import { PageHeader } from "@/components/page-header";
import { getCurrentJob, getDashboard, getTask } from "@/lib/api";

export default async function DashboardPage() {
  const [dashboard, job, task] = await Promise.all([getDashboard(), getCurrentJob(), getTask()]);

  return (
    <>
      <PageHeader
        title="自动招聘工作台"
        description="这里把 JD 转译、样本增强、最终执行画像和候选人筛选串成一条主流程。首页只保留和招聘决策直接相关的信息，Boss 连接入口单独放在专门页面里。"
        badge={dashboard.profile_version}
      />

      <section className="grid metrics-grid">
        {dashboard.metrics.map((metric) => (
          <MetricCard key={metric.label} metric={metric} />
        ))}
      </section>

      <section className="grid two-col" style={{ marginTop: 16 }}>
        <div className="panel">
          <div className="section-title">
            <h2>当前岗位与任务</h2>
            <span className="pill good">{job.status}</span>
          </div>

          <div className="list">
            <div className="list-item">
              <strong>{job.name}</strong>
              <div className="muted" style={{ marginTop: 8 }}>
                城市：{job.city} | 最近同步：{dashboard.latest_sync_at}
              </div>
            </div>

            <div className="list-item">
              <div className="card-row">
                <div>
                  <strong>筛选任务状态</strong>
                  <div className="muted" style={{ marginTop: 8 }}>
                    {task.message}
                  </div>
                </div>
                <span className="pill">{task.status}</span>
              </div>

              <div className="progress-bar" style={{ marginTop: 14 }}>
                <div
                  className="progress-fill"
                  style={{ width: `${Math.round((task.progress_current / Math.max(task.progress_total, 1)) * 100)}%` }}
                />
              </div>
              <div className="muted" style={{ marginTop: 8 }}>
                已处理 {task.progress_current} / {task.progress_total}
              </div>
            </div>

            <div className="toolbar">
              <Link href="/jobs/job-001/profile-draft">
                <button className="primary" type="button">
                  继续设计画像
                </button>
              </Link>
              <Link href="/jobs/job-001/candidates">
                <button type="button">进入筛选台</button>
              </Link>
              <Link href="/boss/connect" className="toolbar-link">
                Boss 连接
              </Link>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="section-title">
            <h2>当前执行画像摘要</h2>
            <span className="pill">{job.current_profile.version_name}</span>
          </div>

          <div className="list">
            <div className="list-item">
              <strong>{job.current_profile.hard_constraints.title}</strong>
              <div className="pill-row" style={{ marginTop: 10 }}>
                {job.current_profile.hard_constraints.items.map((item) => (
                  <span className="pill" key={item}>
                    {item}
                  </span>
                ))}
              </div>
            </div>

            <div className="list-item">
              <strong>私房标准</strong>
              <ul>
                {job.current_profile.private_notes.map((item) => (
                  <li key={item} style={{ marginTop: 8 }}>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      <section className="grid two-col" style={{ marginTop: 16 }}>
        <div className="panel">
          <div className="section-title">
            <h2>最近反馈</h2>
            <Link href="/jobs/job-001/feedback" className="muted">
              查看全部
            </Link>
          </div>
          <div className="list">
            {dashboard.recent_feedback.map((item) => (
              <div key={item} className="list-item">
                {item}
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="section-title">
            <h2>下一步建议</h2>
          </div>
          <div className="list">
            <div className="list-item">先确认最终执行画像，再进入候选人筛选。</div>
            <div className="list-item">筛选页里会直接展示逐条标准判断，不需要再翻接口结果。</div>
            <div className="list-item">如果需要重新连接 Boss，单独去“Boss 连接”页面处理即可。</div>
          </div>
        </div>
      </section>
    </>
  );
}
