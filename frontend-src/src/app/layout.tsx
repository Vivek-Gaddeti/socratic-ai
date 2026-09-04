import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/context/AuthContext";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "SocraticAI — Learn by Discovery",
  description:
    "An AI tutor that uses the Socratic Method to guide you to answers, powered by RAG and multi-agent AI.",
  keywords: ["AI tutor", "Socratic method", "learning", "RAG", "education"],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className={inter.className}>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
