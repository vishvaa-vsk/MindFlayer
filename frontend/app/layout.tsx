import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";

export const metadata: Metadata = {
  title: "MindFlayer — AI-Powered Test Intelligence",
  description: "Context-aware test intelligence engine that plans missing API tests from requirements and generates executable test code.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Navbar />
        <main style={{ paddingTop: '70px', minHeight: '100vh' }}>
          {children}
        </main>
      </body>
    </html>
  );
}
