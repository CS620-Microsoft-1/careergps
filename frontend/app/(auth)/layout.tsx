import { AuthShell } from "@/components/auth/auth-shell";

// Shared by /login and /signup so the brand panel stays put when switching.
export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <AuthShell
      title="Become a stronger candidate."
      description="Understand where you stand, what employers are looking for, and what to do next."
      showJourney
    >
      {children}
    </AuthShell>
  );
}
