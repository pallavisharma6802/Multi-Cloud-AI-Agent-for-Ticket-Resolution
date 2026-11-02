import type { Metadata } from "next";
import "./globals.css";
import NavBar from "@/components/NavBar";
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
    <html lang="en">
      <body>
        <NavBar />
        <main className="app-main">{children}</main>
      </body>
    </html>
  );
}
