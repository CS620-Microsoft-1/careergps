from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from scripts import job_posting_analysis_worker as worker


class JobPostingAnalysisWorkerTests(unittest.TestCase):
    def test_once_processes_at_most_one_request_without_sleeping(self) -> None:
        for result, expected in ((None, 0), ({"status": "succeeded"}, 0), ({"status": "failed"}, 1)):
            with self.subTest(result=result), redirect_stderr(io.StringIO()):
                pipeline = Mock()
                pipeline.process_next.return_value = result
                sleep = Mock()
                self.assertEqual(worker.run_worker(pipeline, once=True, sleep=sleep), expected)
                pipeline.process_next.assert_called_once_with()
                self.assertEqual(pipeline.mock_calls, [
                    call.recover_interrupted(), call.enqueue_missing(), call.process_next(),
                ])
                sleep.assert_not_called()

    def test_continuous_empty_queue_sleeps_and_interrupt_stops_cleanly(self) -> None:
        pipeline = Mock()
        pipeline.process_next.return_value = None
        sleep = Mock(side_effect=KeyboardInterrupt)
        self.assertEqual(worker.run_worker(pipeline, poll_seconds=0.25, sleep=sleep), 0)
        pipeline.process_next.assert_called_once_with()
        sleep.assert_called_once_with(0.25)

    def test_continuous_failure_does_not_block_the_next_job(self) -> None:
        pipeline = Mock()
        pipeline.process_next.side_effect = [{"status": "failed"}, {"status": "succeeded"}, None]
        sleep = Mock(side_effect=KeyboardInterrupt)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(worker.run_worker(pipeline, sleep=sleep), 0)
        self.assertEqual(pipeline.process_next.call_count, 3)
        sleep.assert_called_once_with(2.0)

    def test_queue_error_stops_without_disclosing_exception(self) -> None:
        pipeline = Mock()
        pipeline.process_next.side_effect = RuntimeError("secret database connection string")
        output = io.StringIO()
        with redirect_stderr(output):
            self.assertEqual(worker.run_worker(pipeline), 1)
        self.assertIn("could not process the queue", output.getvalue())
        self.assertNotIn("secret", output.getvalue())

    def test_run_worker_rejects_invalid_poll_interval(self) -> None:
        for value in (0, -1, float("inf"), float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                worker.run_worker(Mock(), poll_seconds=value)

    def test_worker_scans_on_start_and_after_interval_without_resetting_per_job(self) -> None:
        pipeline = Mock()
        pipeline.process_next.side_effect = [{"status": "succeeded"}, None, KeyboardInterrupt]
        times = iter((0.0, 0.0, 1.0, 61.0, 61.0))
        sleep = Mock()
        self.assertEqual(worker.run_worker(
            pipeline, monotonic=lambda: next(times), sleep=sleep,
        ), 0)
        self.assertEqual(pipeline.mock_calls, [
            call.recover_interrupted(), call.enqueue_missing(), call.process_next(),
            call.process_next(),
            call.recover_interrupted(), call.enqueue_missing(), call.process_next(),
        ])
        self.assertEqual(2, pipeline.enqueue_missing.call_count)
        self.assertEqual(3, pipeline.process_next.call_count)
        sleep.assert_called_once_with(2.0)

    def test_recovery_error_stops_before_enqueue_or_processing_and_hides_details(self) -> None:
        pipeline = Mock()
        pipeline.recover_interrupted.side_effect = RuntimeError("private local database path")
        output = io.StringIO()
        with redirect_stderr(output):
            self.assertEqual(worker.run_worker(pipeline, once=True), 1)
        pipeline.recover_interrupted.assert_called_once_with()
        pipeline.enqueue_missing.assert_not_called()
        pipeline.process_next.assert_not_called()
        self.assertIn("could not process the queue", output.getvalue())
        self.assertNotIn("private", output.getvalue())

    def test_periodic_recovery_error_stops_before_more_enqueue_or_processing(self) -> None:
        pipeline = Mock()
        pipeline.recover_interrupted.side_effect = [1, RuntimeError("private state error")]
        pipeline.process_next.return_value = {"status": "succeeded"}
        times = iter((0.0, 0.0, 61.0))
        sleep = Mock()
        with redirect_stderr(io.StringIO()):
            self.assertEqual(worker.run_worker(
                pipeline, monotonic=lambda: next(times), sleep=sleep,
            ), 1)
        self.assertEqual(pipeline.mock_calls, [
            call.recover_interrupted(), call.enqueue_missing(), call.process_next(),
            call.recover_interrupted(),
        ])
        sleep.assert_not_called()

    def test_lost_lease_waits_then_recovers_and_continues_processing(self) -> None:
        pipeline = Mock()
        pipeline.process_next.side_effect = [
            worker.LocalAnalysisStateError("private prior attempt"),
            {"status": "succeeded"},
            None,
        ]
        times = iter((0.0, 0.0, 1.0, 1.0, 2.0))
        sleep = Mock(side_effect=[None, KeyboardInterrupt])
        output = io.StringIO()
        with redirect_stderr(output):
            self.assertEqual(worker.run_worker(
                pipeline, poll_seconds=0.25, monotonic=lambda: next(times), sleep=sleep,
            ), 0)
        self.assertEqual(pipeline.mock_calls, [
            call.recover_interrupted(), call.enqueue_missing(), call.process_next(),
            call.recover_interrupted(), call.enqueue_missing(), call.process_next(),
            call.process_next(),
        ])
        self.assertEqual(sleep.mock_calls, [call(0.25), call(0.25)])
        self.assertIn("lost its local lease", output.getvalue())
        self.assertNotIn("private", output.getvalue())

    def test_once_lost_lease_returns_failure_without_retry_or_sleep(self) -> None:
        pipeline = Mock()
        pipeline.process_next.side_effect = worker.LocalAnalysisStateError("old attempt")
        sleep = Mock()
        with redirect_stderr(io.StringIO()):
            self.assertEqual(worker.run_worker(pipeline, once=True, sleep=sleep), 1)
        self.assertEqual(pipeline.mock_calls, [
            call.recover_interrupted(), call.enqueue_missing(), call.process_next(),
        ])
        sleep.assert_not_called()

    def test_main_requires_endpoint_before_building_dependencies(self) -> None:
        for endpoint in (None, "", "   "):
            with (
                self.subTest(endpoint=endpoint),
                patch.object(worker, "_load_settings", return_value=SimpleNamespace(job_analysis_project_endpoint=endpoint)),
                patch.object(worker, "_build_pipeline") as build,
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(worker.main(["--once"]), 1)
                build.assert_not_called()

    def test_main_passes_arguments_to_worker_without_real_dependencies(self) -> None:
        pipeline = Mock()
        with (
            patch.object(worker, "_load_settings", return_value=SimpleNamespace(job_analysis_project_endpoint="https://example.invalid/project")),
            patch.object(worker, "_build_pipeline", return_value=pipeline) as build,
            patch.object(worker, "run_worker", return_value=0) as run,
        ):
            self.assertEqual(worker.main(["--once", "--poll-seconds", "0.5"]), 0)
        build.assert_called_once_with()
        run.assert_called_once_with(pipeline, once=True, poll_seconds=0.5, scan_seconds=60.0)

    def test_main_rejects_invalid_poll_interval_before_loading_settings(self) -> None:
        for value in ("0", "-1", "nan", "inf", "not-a-number"):
            with (
                self.subTest(value=value),
                patch.object(worker, "_load_settings") as load,
                redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as error,
            ):
                worker.main(["--poll-seconds", value])
            self.assertEqual(error.exception.code, 2)
            load.assert_not_called()


# Both CLI modes share the worker entry point.
command = worker


class EnqueueCommandTests(unittest.TestCase):
    def test_backfill_defaults_only_enqueue_and_do_not_analyze(self):
        pipeline = Mock()
        pipeline.enqueue_missing.return_value = 17
        output = io.StringIO()
        with (
            patch.object(command, "_build_pipeline", return_value=pipeline),
            patch.object(command, "_load_settings", side_effect=AssertionError("Azure configuration must not be required")) as load,
            redirect_stdout(output),
        ):
            self.assertEqual(0, command.main(["--enqueue-only"]))
        load.assert_not_called()
        pipeline.enqueue_missing.assert_called_once_with(batch_size=500, limit=None)
        pipeline.analyze.assert_not_called()
        pipeline.process_next.assert_not_called()
        self.assertIn("17 new local", output.getvalue())

    def test_limit_and_batch_size_are_forwarded(self):
        pipeline = Mock()
        pipeline.enqueue_missing.return_value = 2
        with patch.object(command, "_build_pipeline", return_value=pipeline), redirect_stdout(io.StringIO()):
            self.assertEqual(0, command.main(["--enqueue-only", "--batch-size", "1", "--limit", "2"]))
        pipeline.enqueue_missing.assert_called_once_with(batch_size=1, limit=2)

    def test_invalid_options_do_not_construct_resources(self):
        for option in ("--batch-size", "--limit"):
            for value in ("0", "-1", "not-a-number"):
                with (
                    self.subTest(option=option, value=value),
                    patch.object(command, "_build_pipeline") as build,
                    redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit),
                ):
                    command.main(["--enqueue-only", option, value])
                build.assert_not_called()

    def test_failure_does_not_disclose_source_credentials(self):
        output = io.StringIO()
        with (
            patch.object(command, "_build_pipeline", side_effect=RuntimeError("SECRET_DSN")),
            redirect_stderr(output),
        ):
            self.assertEqual(1, command.main(["--enqueue-only"]))
        self.assertNotIn("SECRET_DSN", output.getvalue())

    def test_enqueue_only_and_once_are_mutually_exclusive(self):
        with (
            patch.object(command, "_load_settings") as load,
            patch.object(command, "_build_pipeline") as build,
            redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as error,
        ):
            command.main(["--enqueue-only", "--once"])
        self.assertEqual(2, error.exception.code)
        load.assert_not_called()
        build.assert_not_called()

    def test_enqueue_options_require_enqueue_only_before_loading_resources(self):
        for option in ("--batch-size", "--limit"):
            with (
                self.subTest(option=option),
                patch.object(command, "_load_settings") as load,
                patch.object(command, "_build_pipeline") as build,
                redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as error,
            ):
                command.main([option, "1"])
            self.assertEqual(2, error.exception.code)
            load.assert_not_called()
            build.assert_not_called()


if __name__ == "__main__":
    unittest.main()
