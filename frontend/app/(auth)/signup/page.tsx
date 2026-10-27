import type { Metadata } from "next";
import Link from "next/link";

import { AuthShell } from "@/components/auth/auth-shell";
import { SignupForm } from "@/components/auth/signup-form";

export const metadata: Metadata = { title: "Sign up" };

export default function SignupPage() {
  return (
    <AuthShell footer={<p>Already have an account? <Link href="/login" className="font-bold underline">Log in</Link></p>}>
      <SignupForm />
    </AuthShell>
  );
}
