import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { ConfirmEmail } from "@/components/auth/confirm-email";

export const metadata: Metadata = { title: "Confirming your email" };

export default function ConfirmPage() {
  return (
    <AuthShell
      title="Welcome to CareerGPS."
      description="Understand where you stand, what employers are looking for, and what to do next."
    >
      <ConfirmEmail />
    </AuthShell>
  );
}
