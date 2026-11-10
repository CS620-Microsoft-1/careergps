"use client";

import { useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { LoaderCircle, RotateCcw } from "lucide-react";

import { AnalysisSteps } from "@/components/career/route-parts";
import { Button } from "@/components/ui/button";
import { retrySetupSave, setupSave } from "@/lib/setup-save";

/**
 * The route page opens as soon as setup's last step is submitted. Until the profile is saved, show
 * that as the first loading step; the route (which loads the saved profile) mounts only after.
 */
export function SetupSaveGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const state = useSyncExternalStore(setupSave.subscribe, setupSave.getSnapshot, setupSave.getServerSnapshot);
  if (state.status === "idle") return children;

  const failed = state.status === "failed";
  return (
    <div className="mx-auto flex w-full max-w-300 flex-1 flex-col px-4 py-6 sm:px-6">
      <div className="grid flex-1 place-items-center">
        <div className="w-full max-w-3xl">
          <div className="grid justify-items-center gap-3 rounded-2xl border border-border bg-card px-6 py-14 text-center" aria-busy={!failed}>
            {!failed && <LoaderCircle aria-hidden className="size-7 motion-safe:animate-spin" />}
            <div role="status" aria-live="polite" className="grid gap-1.5">
              <h2 className="text-section">{failed ? "Couldn’t save your profile" : "Saving your profile"}</h2>
              <p className="mx-auto max-w-lg text-muted-foreground">
                {failed ? state.error : "Your route starts calculating as soon as your résumé is saved."}
              </p>
            </div>
            {!failed && <AnalysisSteps saving />}
            {failed && <div className="mt-2">
              <Button size="lg" onClick={retrySetupSave}><RotateCcw data-icon="inline-start" />Try again</Button>
            </div>}
          </div>
        </div>
      </div>
      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <Button variant="ghost" size="lg" onClick={() => router.back()}>Back</Button>
      </div>
    </div>
  );
}
