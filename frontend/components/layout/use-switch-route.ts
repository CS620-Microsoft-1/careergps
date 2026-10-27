"use client";

import { useAccount } from "@/components/layout/account-provider";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { FAMILY_LABELS } from "@/lib/skill-gap-profile";
import { isActiveSkillGapRun } from "@/lib/skill-gap-session";
import type { JobFamily } from "@/types/api";

/** Switch the selected destination everywhere, and keep it as the account's target role. */
export function useSwitchRoute() {
  const { family, snapshot, submitting, restoring, run, changeFamily } = useSkillGapAnalysis();
  const { update } = useAccount();
  const locked = !snapshot || submitting || restoring || isActiveSkillGapRun(run);
  const switchTo = async (next: JobFamily) => {
    if (locked || next === family) return;
    changeFamily(next);
    // Only remembers the choice for the next visit; the switch itself already happened.
    await update({ target_role: FAMILY_LABELS[next] }).catch(() => {});
  };
  return { family, locked, switchTo };
}
