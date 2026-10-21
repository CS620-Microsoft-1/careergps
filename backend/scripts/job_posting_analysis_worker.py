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

    def enqueue_missing(self, *, batch_size: int = 500, limit: int | None = None) -> int: ...

    def process_next(self) -> dict[str, Any] | None: ...


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
    poll_seconds: float = 2.0,
    scan_seconds: float = 60.0,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Recover expired work and discover IDs on each scan, then process local work."""
    if not math.isfinite(poll_seconds) or poll_seconds <= 0:
        raise ValueError("poll_seconds must be finite and greater than zero.")

    if not math.isfinite(scan_seconds) or scan_seconds <= 0:
        raise ValueError("scan_seconds must be finite and greater than zero.")
    next_scan = float("-inf")
    try:
        while True:
            if monotonic() >= next_scan:
                pipeline.recover_interrupted()
                pipeline.enqueue_missing()
                next_scan = monotonic() + scan_seconds
            try:
                result = pipeline.process_next()
            except LocalAnalysisStateError:
                print(
                    "A job analysis lost its local lease; the queue will be checked again.",
                    file=sys.stderr,
                )
                if once:
                    return 1
                sleep(poll_seconds)
                next_scan = float("-inf")
                continue
            if result is None:
                if once:
                    return 0
                sleep(poll_seconds)
                continue

            failed = result.get("status") == "failed"
            if failed:
                print(
                    "A job analysis failed; its status is saved in the local analysis queue.",
                    file=sys.stderr,
                )
            if once:
                return 1 if failed else 0
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
    parser = argparse.ArgumentParser(description="Process queued version 13 job analyses.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Process at most one queued request.")
    mode.add_argument(
        "--enqueue-only", action="store_true",
        help="Read source JP IDs and enqueue missing jobs locally without calling the Agent.",
    )
    parser.add_argument(
        "--batch-size", type=_positive_int,
        help="JP ID read batch size for --enqueue-only (default: 500).",
    )
    parser.add_argument(
        "--limit", type=_positive_int,
        help="Maximum number of new local jobs for --enqueue-only.",
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

    if args.enqueue_only:
        try:
            added = _build_pipeline().enqueue_missing(
                batch_size=args.batch_size if args.batch_size is not None else 500,
                limit=args.limit,
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
        pipeline, once=args.once, poll_seconds=args.poll_seconds, scan_seconds=args.scan_seconds
    )


if __name__ == "__main__":
    raise SystemExit(main())
