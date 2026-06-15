import "./globals.css";
import type { Metadata } from "next";
import { Suspense } from "react";

export const metadata: Metadata = {
  title: "Jirassic Park",
  description: "A Jira-like environment for humans and agents.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="font-sans antialiased text-ink-900">
        <Suspense>{children}</Suspense>
      </body>
    </html>
  );
}
