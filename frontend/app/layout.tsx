import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import NavBar from "@/components/NavBar";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Resolve — Support workspace",
  description:
    "An AI-assisted support workspace with evidence-backed resolutions and live cloud analytics.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable}>
      <body>
        <NavBar />
        <main className="app-main">{children}</main>
      </body>
    </html>
  );
}
