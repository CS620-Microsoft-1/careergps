import { AskButton } from "@/components/layout/ask-button";
import { BackendStatusProvider } from "@/components/layout/backend-status-provider";
import { OnboardingGuard } from "@/components/layout/onboarding-guard";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { CopilotProvider } from "@/components/panels/copilot-provider";
import { SkillGapProvider } from "@/components/skill-gaps/skill-gap-provider";

/**
 * Signed-in app shell: sidebar (lg+), sticky top bar with mobile nav (<lg),
 * centered page content, and the floating Ask CareerGPS button + Copilot panel.
 */
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <CopilotProvider>
      <BackendStatusProvider>
        <OnboardingGuard />
        <SkillGapProvider>
          <div className="min-h-dvh lg:grid lg:grid-cols-[14.5rem_minmax(0,1fr)]">
            <Sidebar />
            <div className="flex min-w-0 flex-col">
              <Topbar />
              <main className="mx-auto w-full max-w-290 px-4 pt-6 pb-24 sm:px-8 sm:pt-8">
                {children}
              </main>
            </div>
            <AskButton />
          </div>
        </SkillGapProvider>
      </BackendStatusProvider>
    </CopilotProvider>
  );
}
