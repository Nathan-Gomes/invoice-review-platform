import type { Metadata } from "next";
import "./globals.css";
import QueryProvider from "@/lib/query-provider";
import { Sidebar } from "@/components/layout/sidebar";

export const metadata: Metadata = {
  title: "Invoice Review",
  description: "Portfolio expense monitoring and savings system",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">
        <QueryProvider>
          <div className="flex h-screen overflow-hidden">
            <Sidebar />
            <main className="flex-1 overflow-y-auto bg-[var(--color-page)]">{children}</main>
          </div>
        </QueryProvider>
      </body>
    </html>
  );
}
