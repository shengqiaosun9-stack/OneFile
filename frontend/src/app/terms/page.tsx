export default function TermsPage() {
  return (
    <main className="app-shell min-h-screen px-6 py-8 sm:px-8">
      <div className="mx-auto max-w-3xl space-y-5 content-panel p-6">
        <h1 className="text-2xl font-semibold text-[var(--landing-title)]">用户协议</h1>
        <p className="text-sm content-subtle">生效日期：2026-03-29</p>
        <p className="text-sm content-subtle">
          使用 OnePitch · 一眼项目表示你同意仅上传你拥有合法使用权的内容，并对分享内容承担责任。平台不对用户上传内容的真实性与合法性提供担保。
        </p>
        <p className="text-sm content-subtle">
          我们保留在系统稳定性或安全需要下限制频次、暂停异常请求或下线违规内容的权利。
        </p>
      </div>
    </main>
  );
}
