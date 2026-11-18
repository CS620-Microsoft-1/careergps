import { createElement, type ReactNode } from "react";

/** Render paired, single-line bold spans only. All content stays escaped React text. */
export function renderCopilotText(text: string): ReactNode[] {
  return text.split(/(?<!\\)\*\*([^*\n]+?)(?<!\\)\*\*/g).map((part, index) =>
    index % 2 === 1 ? createElement("strong", { key: index }, part) : part,
  );
}
