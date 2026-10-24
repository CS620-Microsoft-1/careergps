"""Discover source JP IDs read-only and consume the local analysis queue."""

from __future__ import annotations

import argparse
import math
import sys
import time
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from app.services.local_job_analysis_store import LocalAnalysisStateError


class AnalysisQueue(Protocol):
    def recover_interrupted(self) -> int: ...

    def enqueue_missing(
        self, *, batch_size: int = 500, limit: int | None = None,
        focused_only: bool = False,
    ) -> int: ...

    def process_next(self, *, focused_only: bool = False) -> dict[str, Any] | None: ...


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a positive integer") from None
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def _positive_seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a finite number greater than zero") from None
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return seconds


def run_worker(
    pipeline: AnalysisQueue,
    *,
    once: bool = False,
    max_jobs: int = 3,
    poll_seconds: float = 2.0,
    scan_seconds: float = 60.0,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Process only focus titles, with per-invocation enqueue and attempt budgets.

    Empty queues wait for new eligible work. Both budgets survive periodic scans;
    failures and lost leases consume attempts even if no result was committed.
    Concurrent workers and repeated invocations each have their own budget.
    """
    if isinstance(max_jobs, bool) or not isinstance(max_jobs, int) or max_jobs < 1:
        raise ValueError("max_jobs must be a positive integer.")
    if not math.isfinite(poll_seconds) or poll_seconds <= 0:
        raise ValueError("poll_seconds must be finite and greater than zero.")

    if not math.isfinite(scan_seconds) or scan_seconds <= 0:
        raise ValueError("scan_seconds must be finite and greater than zero.")
    budget = 1 if once else max_jobs
    attempts = 0
    enqueued = 0
    any_failed = False
    next_scan = float("-inf")
    try:
        while attempts < budget:
            if monotonic() >= next_scan:
                pipeline.recover_interrupted()
                enqueue_capacity = min(budget - enqueued, budget - attempts)
                if enqueue_capacity > 0:
                    enqueued += pipeline.enqueue_missing(
                        limit=enqueue_capacity, focused_only=True,
                    )
                next_scan = monotonic() + scan_seconds
            try:
                result = pipeline.process_next(focused_only=True)
            except LocalAnalysisStateError:
                attempts += 1
                any_failed = True
                print(
                    "A job analysis lost its local lease; this attempt counts toward the run limit.",
                    file=sys.stderr,
                )
                if attempts >= budget:
                    return 1
                sleep(poll_seconds)
                next_scan = float("-inf")
                continue
            if result is None:
                if once:
                    return 0
                sleep(poll_seconds)
                continue

            # A claim race or a changed title can return queued/running instead
            # of calling Azure. Count it anyway: spending must never be undercounted.
            attempts += 1
            failed = result.get("status") == "failed"
            any_failed = any_failed or failed
            if failed:
                print(
                    "A job analysis failed; its status is saved in the local analysis queue.",
                    file=sys.stderr,
                )
        return 1 if any_failed else 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        # Database and state errors must not expose SQL, SDK messages, or credentials.
        print("The job analysis worker could not process the queue.", file=sys.stderr)
        return 1


def _load_settings() -> Any:
    """Delay configuration reads until the CLI is explicitly invoked."""
    from app.core.config import get_settings

    return get_settings()


def _build_pipeline() -> AnalysisQueue:
    """Delay production dependency construction until the CLI is invoked."""
    from app.api.deps import get_job_analysis_pipeline

    return get_job_analysis_pipeline()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Process version 13 analyses for Software Engineer, Data Analyst and AI Engineer titles."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Process at most one queued request.")
    mode.add_argument(
        "--enqueue-only", action="store_true",
        help="Enqueue missing focus-title jobs locally without calling the Agent.",
    )
    parser.add_argument(
        "--batch-size", type=_positive_int,
        help="JP ID read batch size for --enqueue-only (default: 500).",
    )
    parser.add_argument(
        "--limit", type=_positive_int,
        help="Maximum new focus-title jobs for --enqueue-only (default: 3).",
    )
    parser.add_argument(
        "--max-jobs", type=_positive_int,
        help="Maximum processing attempts per invocation, including failures (default: 3; --once: 1).",
    )
    parser.add_argument(
        "--poll-seconds",
        type=_positive_seconds,
        default=2.0,
        help="Seconds to wait when the queue is empty (default: 2).",
    )
    parser.add_argument(
        "--scan-seconds", type=_positive_seconds, default=60.0,
        help="Seconds between read-only scans for new JP IDs (default: 60).",
    )
    args = parser.parse_args(argv)
    if not args.enqueue_only and (args.batch_size is not None or args.limit is not None):
        parser.error("--batch-size and --limit require --enqueue-only")

    if args.enqueue_only and args.max_jobs is not None:
        parser.error("--max-jobs cannot be used with --enqueue-only; use --limit")

    if args.enqueue_only:
        try:
            added = _build_pipeline().enqueue_missing(
                batch_size=args.batch_size if args.batch_size is not None else 500,
                limit=args.limit if args.limit is not None else 3,
                focused_only=True,
            )
        except Exception:
            print("Could not read source postings or update the local queue.", file=sys.stderr)
            return 1
        print(f"Queued {added} new local job analyses; no Agent calls were made.")
        return 0

    try:
        settings = _load_settings()
        endpoint = settings.job_analysis_project_endpoint
        if not isinstance(endpoint, str) or not endpoint.strip():
            print("JOB_ANALYSIS_PROJECT_ENDPOINT must be configured to run the worker.", file=sys.stderr)
            return 1
        pipeline = _build_pipeline()
    except Exception:
        print("The job analysis worker could not load its configuration.", file=sys.stderr)
        return 1

    return run_worker(
        pipeline, once=args.once, max_jobs=args.max_jobs if args.max_jobs is not None else 3,
        poll_seconds=args.poll_seconds, scan_seconds=args.scan_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
