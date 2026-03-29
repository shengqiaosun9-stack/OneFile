import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import { DemoEnvNotice } from "@/components/onefile/demo-env-notice";
import { Toaster } from "@/components/ui/sonner";

import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "OneFile",
  description: "把想法转化为可演化、可分享的项目资产。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" data-scroll-behavior="smooth" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <DemoEnvNotice />
        {children}
        <Toaster />
      </body>
    </html>
  );
}
