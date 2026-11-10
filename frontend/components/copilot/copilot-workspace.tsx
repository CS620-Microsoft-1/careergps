"use client";

import { useEffect, useRef } from "react";
import { Navbar } from "@/components/layout/navbar";
import { CopilotPanel } from "@/components/copilot/copilot-panel";
import { useCopilot } from "@/components/copilot/copilot-provider";
import { cn } from "@/lib/utils";

/** A layout column, not a modal: the report stays clickable and keyboard-accessible. */
export function CopilotWorkspace({ children }: { children: React.ReactNode }) {
  const { state } = useCopilot();
  const root = useRef<HTMLDivElement>(null);
  const nav = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = nav.current;
    if (!element) return;
    const measure = () => root.current?.style.setProperty("--copilot-nav-height", `${element.getBoundingClientRect().height}px`);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return <div ref={root} className="min-h-dvh [--copilot-nav-height:5rem]">
    <div ref={nav} className="sticky top-0 z-30"><Navbar /></div>
    <div className={cn("grid items-start", state.open && "lg:grid-cols-[minmax(0,1fr)_24rem]")}>
      <main id="career-report" tabIndex={-1} className={cn("mx-auto w-full min-w-0 max-w-300 scroll-mt-32 px-4 pt-8 pb-24 outline-none sm:px-6 sm:pt-10", state.open && "@container")}>
        {children}
      </main>
      {state.open && <CopilotPanel />}
    </div>
  </div>;
}
