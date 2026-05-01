import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RaceQuant Lab",
  description: "Python ML の競馬予測を Next.js で可視化する予想ワークベンチ。",
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
