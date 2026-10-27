import type { Metadata } from "next";
import Link from "next/link";

import { AuthHeading, AuthShell } from "@/components/auth/auth-shell";
import { LoginForm } from "@/components/auth/login-form";

export const metadata: Metadata = { title: "Log in" };

export default function LoginPage() {
  return (
    <AuthShell footer={<p>New to CareerGPS? <Link href="/signup" className="font-bold underline">Create an account</Link></p>}>
      <AuthHeading title="Log in" />
      <LoginForm />
    </AuthShell>
  );
}
