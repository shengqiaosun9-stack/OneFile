export function DemoEnvNotice() {
  if (process.env.NEXT_PUBLIC_DEMO_MODE !== "1") {
    return null;
  }

  return (
    <div className="demo-env-notice" role="status" aria-live="polite">
      演示环境：请定期在项目库导出备份
    </div>
  );
}
