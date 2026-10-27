import { AccountProvider } from "@/components/layout/account-provider";
import { BackendStatusProvider } from "@/components/layout/backend-status-provider";
import { Navbar } from "@/components/layout/navbar";
import { OnboardingGuard } from "@/components/layout/onboarding-guard";
import { PlanProvider } from "@/components/plan/plan-provider";
import { SkillGapProvider } from "@/components/skill-gaps/skill-gap-provider";

/** Signed-in app shell: sticky nav bar over centered page content. */
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <BackendStatusProvider>
      <OnboardingGuard />
      <AccountProvider>
        <SkillGapProvider>
          <PlanProvider>
            <div className="min-h-dvh">
              <Navbar />
              <main className="mx-auto w-full max-w-300 px-4 pt-8 pb-24 sm:px-6 sm:pt-10">{children}</main>
            </div>
          </PlanProvider>
        </SkillGapProvider>
      </AccountProvider>
    </BackendStatusProvider>
  );
}
