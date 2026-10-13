from __future__ import annotations

import time
from pathlib import Path

from app.services.foundry_agent import FoundryResumeAgentService
from app.services.resume_extraction import extract_resume


class ResumePipeline:
    def __init__(self, agent: FoundryResumeAgentService) -> None:
        self.agent = agent

    def analyze(self, path: Path, suffix: str, filename: str) -> dict:
        extraction_started = time.perf_counter()
        extraction = extract_resume(path, suffix)
        extraction_seconds = time.perf_counter() - extraction_started

        classification_started = time.perf_counter()
        classification = self.agent.classify(extraction["text"])
        classification_seconds = time.perf_counter() - classification_started

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
