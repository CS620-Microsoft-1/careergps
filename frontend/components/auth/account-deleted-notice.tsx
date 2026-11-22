"use client";

import { useSearchParams } from "next/navigation";
import { CircleCheck } from "lucide-react";

/** Shown on /login?deleted=1, where the profile page sends the student after deleting their account. */
export function AccountDeletedNotice() {
  if (useSearchParams().get("deleted") !== "1") return null;
  return (
    <p role="status" className="mb-6 flex items-start gap-2.5 rounded-xl bg-success-soft px-4 py-3 text-sm/6">
      <CircleCheck aria-hidden className="mt-0.5 size-4.5 shrink-0" />
      <span><strong>Your account has been deleted.</strong> All of your data has been removed.</span>
    </p>
  );
}
