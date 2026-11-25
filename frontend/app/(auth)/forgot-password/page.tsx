import type { Metadata } from "next";
import Link from "next/link";

import { AuthShell } from "@/components/auth/auth-shell";
import { ForgotPasswordForm } from "@/components/auth/forgot-password-form";

export const metadata: Metadata = { title: "Reset your password" };

export default function ForgotPasswordPage() {
  return (
    <AuthShell footer={<p>Remembered it? <Link href="/login" className="font-bold underline">Back to log in</Link></p>}>
      <ForgotPasswordForm />
    </AuthShell>
  );
}
