import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { ConfirmEmail } from "@/components/auth/confirm-email";

export const metadata: Metadata = { title: "Confirm your email" };

export default function ConfirmPage() {
  return (
    <AuthShell>
      <ConfirmEmail />
    </AuthShell>
  );
}
