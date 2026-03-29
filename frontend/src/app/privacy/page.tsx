export default function PrivacyPage() {
  return (
    <main className="landing-premium min-h-screen px-6 py-8 sm:px-8">
      <div className="mx-auto max-w-3xl space-y-5 onefile-panel p-6">
        <h1 className="text-2xl font-semibold text-[var(--landing-title)]">隐私政策</h1>
        <p className="text-sm onefile-subtle">生效日期：2026-03-29</p>
        <p className="text-sm onefile-subtle">
          OneFile 仅收集实现登录、项目创建与分享所需的最小信息。上传的 BP 文件仅用于当次文本提取，不长期保存原始文件。
        </p>
        <p className="text-sm onefile-subtle">
          你可以随时通过“导出我的备份”获取自己的项目数据。若需删除账号与数据，请联系：hello@onefile.app。
        </p>
      </div>
    </main>
  );
}
