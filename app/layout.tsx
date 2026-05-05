import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "UmaLab",
  description: "未来レースのAI予測、回収率検証、直前オッズ監視をまとめる競馬予想ワークベンチ。",
  icons: {
    icon: "/racequant-icon.svg",
    apple: "/racequant-icon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
