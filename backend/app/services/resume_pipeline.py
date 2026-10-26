from __future__ import annotations

import time
from pathlib import Path

from app.services.foundry_agent import FoundryResumeAgentService
from app.services.resume_extraction import StepCallback, extract_resume


class ResumePipeline:
    def __init__(self, agent: FoundryResumeAgentService) -> None:
        self.agent = agent

    def analyze(
        self,
        path: Path,
        suffix: str,
        filename: str,
        on_step: StepCallback | None = None,
    ) -> dict:
        def report(step: str, status: str, detail: dict | None = None) -> None:
            if on_step:
                on_step(step, status, detail)

        report("extract", "started")
        extraction_started = time.perf_counter()
        extraction = extract_resume(path, suffix, on_step=on_step)
        extraction_seconds = time.perf_counter() - extraction_started
        report(
            "extract",
            "done",
            {
                "parser": extraction["parser"],
                "characters": extraction["characters"],
                "ocr_pages": extraction["ocr_pages"],
            },
        )

        # The Agent call also parses and validates the JSON, so "done" means the result is validated.
        report("classify", "started")
        classification_started = time.perf_counter()
        classification = self.agent.classify(extraction["text"])
        classification_seconds = time.perf_counter() - classification_started
        report("classify", "done", {"seconds": round(classification_seconds, 2), "validated": True})

        return {
            "filename": filename,
            "extraction": {
                **extraction,
                "seconds": round(extraction_seconds, 4),
            },
            "agent": {
                "name": self.agent.agent_name,
                "seconds": round(classification_seconds, 4),
                "validated": True,
            },
            "classification": classification,
        }
