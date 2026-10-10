import type { Metadata } from "next";

import { AuthHeading } from "@/components/auth/auth-shell";
import { LoginForm } from "@/components/auth/login-form";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <>
      <AuthHeading title="Welcome back" subtitle="Sign in to continue your career journey." />
      <LoginForm />
    </>
  );
}
