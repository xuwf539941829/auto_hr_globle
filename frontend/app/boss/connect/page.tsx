import { BossLaunchCard } from "@/components/boss-launch-card";
import { PageHeader } from "@/components/page-header";

export default function BossConnectPage() {
  return (
    <>
      <PageHeader
        title="Boss 连接向导"
        description="这里不需要你手动复制命令。直接点击按钮，系统就会启动可连接的浏览器。再点状态检测，就能知道 Boss 登录和职位同步有没有真正连上。"
        badge="连接前置"
      />

      <section className="grid two-col">
        <div className="panel">
          <div className="section-title">
            <h2>启动与检测</h2>
          </div>
          <BossLaunchCard />
        </div>

        <div className="panel alt">
          <div className="section-title">
            <h2>使用说明</h2>
          </div>
          <div className="list">
            <div className="list-item">
              <strong>点击启动后会发生什么？</strong>
              <div className="muted" style={{ marginTop: 8 }}>
                后端会直接启动 Chrome 或 Edge，并带上 9222 调试端口与专用用户目录，然后打开 Boss 招聘后台页面。
              </div>
            </div>
            <div className="list-item">
              <strong>接下来做什么？</strong>
              <div className="muted" style={{ marginTop: 8 }}>
                在新打开的浏览器里登录 Boss。登录完成后点击“检测连接状态”，页面会告诉你是否已经能读到职位列表。
              </div>
            </div>
            <div className="list-item">
              <strong>如果检测失败？</strong>
              <div className="muted" style={{ marginTop: 8 }}>
                通常是后端还没重启到最新代码、浏览器未启动成功，或者你还没有在新窗口里完成 Boss 登录。
              </div>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
