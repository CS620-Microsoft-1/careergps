import { SetupHeader } from "@/components/setup/setup-shell";

/** Setup: résumé, your info, target role, then the first route. */
export default function SetupLayout({ children }: LayoutProps<"/onboarding">) {
  return (
    <div className="flex min-h-dvh flex-col">
      <SetupHeader />
      <main className="flex flex-1 flex-col">{children}</main>
    </div>
  );
}
