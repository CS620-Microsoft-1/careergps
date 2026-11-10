import { AccountProvider } from "@/components/layout/account-provider";
import { BackendStatusProvider } from "@/components/layout/backend-status-provider";
import { CopilotProvider } from "@/components/copilot/copilot-provider";
import { CopilotWorkspace } from "@/components/copilot/copilot-workspace";
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
            <CopilotProvider>
              <CopilotWorkspace>{children}</CopilotWorkspace>
            </CopilotProvider>
          </PlanProvider>
        </SkillGapProvider>
      </AccountProvider>
    </BackendStatusProvider>
  );
}
