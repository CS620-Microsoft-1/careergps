import { ArrowRight } from "lucide-react";

import { Logo } from "@/components/common/logo";

const JOURNEY = ["Your Profile", "Job Market", "Skill Gaps", "Action Plan"];

type AuthShellProps = {
  title: string;
  description: string;
  /** Show the four-step "how CareerGPS works" strip under the description. */
  showJourney?: boolean;
  children: React.ReactNode;
};

/**
 * Split layout shared by login, sign-up and onboarding.
 * Phones/tablets: brand panel stacks above the form.
 * Desktop (lg+): brand panel pins to the viewport while the form column scrolls,
 * so short laptop screens never cut off the form.
 */
export function AuthShell({
  title,
  description,
  showJourney = false,
  children,
}: AuthShellProps) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-2">
      <aside className="flex flex-col bg-deep px-6 py-7 text-deep-foreground sm:px-10 sm:py-10 lg:sticky lg:top-0 lg:h-dvh lg:self-start lg:overflow-y-auto lg:px-16 lg:py-12 2xl:px-24">
        <Logo tone="light" />
        <div className="mt-8 grid max-w-130 gap-5 lg:my-auto lg:py-8">
          <h1 className="text-display tracking-[-0.025em]">
            {title}
          </h1>
          <p className="text-base/relaxed text-deep-muted">{description}</p>
          {showJourney && (
            <ol
              aria-label="How CareerGPS works"
              className="mt-2 flex flex-wrap items-center gap-2 text-control font-semibold text-[#d6e8e3]"
            >
              {JOURNEY.map((step, i) => (
                <li key={step} className="flex items-center gap-2">
                  <span
                    aria-hidden
                    className="grid size-5.5 place-items-center rounded-full bg-white/12 text-[0.6875rem]"
                  >
                    {i + 1}
                  </span>
                  {step}
                  {i < JOURNEY.length - 1 && (
                    <ArrowRight aria-hidden className="size-3.5 text-[#6f968e]" />
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>
        <p className="hidden text-xs text-[#86aaa2] lg:block">
          Built for students at UW–Madison
        </p>
      </aside>
      <main className="flex justify-center px-6 py-10 sm:px-10 lg:items-center lg:py-12">
        <div className="w-full max-w-100">{children}</div>
      </main>
    </div>
  );
}

export function AuthHeading({
  title,
  subtitle,
}: {
  title: string;
  subtitle: string;
}) {
  return (
    <div className="mb-7">
      <h2 className="text-page-title tracking-[-0.02em]">{title}</h2>
      <p className="mt-1.5 text-muted-foreground">{subtitle}</p>
    </div>
  );
}
