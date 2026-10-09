import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Dashboard" };

// Placeholder target for the auth flow; the real app shell and dashboard come in Step 4.
export default function DashboardPage() {
  return (
    <main className="mx-auto grid w-full max-w-290 gap-2 px-4 py-8 sm:px-8">
      <h1 className="text-page-title tracking-[-0.02em]">Dashboard</h1>
      <p className="text-muted-foreground">
        The app shell and dashboard are coming next.{" "}
        <Link href="/login" className="font-semibold text-primary hover:underline">
          Back to sign in
        </Link>
      </p>
    </main>
  );
}
