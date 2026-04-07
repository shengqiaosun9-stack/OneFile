import type { Metadata } from "next";

import { DemoEnvNotice } from "@/components/onefile/demo-env-notice";
import { Toaster } from "@/components/ui/sonner";

import "./globals.css";

export const metadata: Metadata = {
  title: "OnePitch · 一眼项目",
  description: "把一个模糊想法，立刻压缩成一张能直接发出去的项目卡。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" data-scroll-behavior="smooth">
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <DemoEnvNotice />
        {children}
        <Toaster />
      </body>
    </html>
  );
}
