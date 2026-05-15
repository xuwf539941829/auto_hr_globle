import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "Auto HR Copilot",
  description: "自动招聘流程控制台"
};

const navItems = [
  { href: "/", label: "工作台" },
  { href: "/boss/connect", label: "Boss 连接" },
  { href: "/jobs/job-001/profile-draft", label: "画像设计" },
  { href: "/jobs/job-001/feedback", label: "反馈学习" },
  { href: "/settings/llm", label: "模型设置" },
  { href: "/settings/llm/traces", label: "模型调试" }
];

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>
        <div className="shell">
          <aside className="sidebar">
            <div className="brand">
              Auto HR Copilot
              <small>自动招聘执行台</small>
            </div>
            <nav className="nav">
              {navItems.map((item) => (
                <Link key={item.href} href={item.href}>
                  {item.label}
                </Link>
              ))}
            </nav>
          </aside>
          <main className="content">{children}</main>
        </div>
      </body>
    </html>
  );
}
