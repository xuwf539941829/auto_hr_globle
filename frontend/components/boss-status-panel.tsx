import Link from "next/link";

import type { BossStatus } from "@/lib/types";

export function BossStatusPanel({
  status,
  compact = false
}: {
  status: BossStatus;
  compact?: boolean;
}) {
  return (
    <div className="panel">
      <div className="section-title">
        <h2>Boss 连接状态</h2>
        <Link href="/boss/connect" className="muted">
          打开连接页
        </Link>
      </div>
      <div className="list">
        <div className="list-item">
          <strong>{status.message}</strong>
          <div className="muted" style={{ marginTop: 8 }}>
            调试地址：{status.cdp_url}
          </div>
        </div>
        <div className="pill-row">
          <span className={`pill ${status.cdp_reachable ? "good" : "bad"}`}>9222 端口</span>
          <span className={`pill ${status.browser_connected ? "good" : "bad"}`}>浏览器连接</span>
          <span className={`pill ${status.boss_page_detected ? "good" : "warn"}`}>Boss 页面</span>
          <span className={`pill ${status.login_cookie_detected ? "good" : "warn"}`}>登录态</span>
          <span className={`pill ${status.job_list_available ? "good" : "warn"}`}>职位列表</span>
        </div>
        {!compact ? (
          <div className="list-item">
            <strong>当前同步状态</strong>
            <div className="muted" style={{ marginTop: 8 }}>已读取职位数：{status.job_count}</div>
            <div className="muted" style={{ marginTop: 6 }}>
              没连上时，系统会退回本地 mock 数据；真正开始筛选前，建议先把这里刷成全绿。
            </div>
          </div>
        ) : (
          <div className="muted">已读取职位数：{status.job_count}</div>
        )}
      </div>
    </div>
  );
}
