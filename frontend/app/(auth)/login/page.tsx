import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { AccountDeletedNotice } from "@/components/auth/account-deleted-notice";
import { AuthHeading, AuthShell } from "@/components/auth/auth-shell";
import { LoginForm } from "@/components/auth/login-form";

export const metadata: Metadata = { title: "Log in" };

export default function LoginPage() {
  return (
    <AuthShell footer={<p>New to CareerGPS? <Link href="/signup" className="font-bold underline">Create an account</Link></p>}>
      {/* ?deleted=1 is read in the browser (useSearchParams), so the page itself stays static. */}
      <Suspense fallback={null}>
        <AccountDeletedNotice />
      </Suspense>
      <AuthHeading title="Log in" />
      <LoginForm />
    </AuthShell>
  );
}
