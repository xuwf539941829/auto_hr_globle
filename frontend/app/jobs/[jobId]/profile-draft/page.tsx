import { PageHeader } from "@/components/page-header";
import { ProfileDraftWorkspace } from "@/components/profile-draft-workspace";
import { getJobs } from "@/lib/api";

export async function generateStaticParams() {
  return [{ jobId: "job-001" }];
}

export default async function ProfileDraftPage({
  params
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;
  const jobs = await getJobs();

  return (
    <>
      <PageHeader
        title="招聘标准设计台"
        description="按步骤完成 JD 转译、优秀样本分析和最终画像校准。每一步左边保留原始输入，右边直接展示结构化结果。"
        badge="画像设计"
      />

      {jobs.length === 0 ? (
        <section className="panel">
          <h2>暂无招聘职位</h2>
          <div className="muted" style={{ marginTop: 8 }}>
            当前还没有从 Boss 读取到真实招聘职位。先到 Boss 连接页确认浏览器登录和职位同步，成功后再回来设计画像。
          </div>
        </section>
      ) : (
        <ProfileDraftWorkspace jobs={jobs} jobId={jobId} />
      )}
    </>
  );
}
