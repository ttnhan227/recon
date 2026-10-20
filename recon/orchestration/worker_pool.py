from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine

from recon.common.logging import current_worker_id, logger
from recon.common.models import (
    FailureCategory,
    FailureEvidence,
    TestCase,
    TestCategory,
    TestResult,
    TestStatus,
    TestType,
)
from recon.execution.api.runner import APITestRunner
from recon.execution.browser.runner import BrowserTestRunner


class WorkerPool:
    """Bounded asynchronous worker pool for executing test cases concurrently in topological waves."""

    def __init__(
        self,
        concurrency: int = 4,
        run_id: str = "default",
        output_dir: Path | str = "./reports",
        api_client: Any = None,
        on_test_start: Callable[[TestCase], Coroutine[Any, Any, None]] | None = None,
        on_test_complete: Callable[[TestCase, TestResult], Coroutine[Any, Any, None]] | None = None,
    ):
        self.concurrency = max(1, concurrency)
        self.run_id = run_id
        self.output_dir = output_dir
        self.on_test_start = on_test_start
        self.on_test_complete = on_test_complete
        self.api_runner = APITestRunner(client=api_client)
        self.browser_runner = BrowserTestRunner(run_id=run_id, output_dir=output_dir)
        self._cancelled = False

    @staticmethod
    def get_test_wave(test: TestCase) -> int:
        """Determines the execution wave for a test case to prevent race conditions."""
        cat = test.category
        method = (test.method or "GET").upper()
        target = test.target or ""
        has_param = "{" in target or "00000000" in target

        if method == "DELETE":
            return 4  # Wave 4: Destructive cleanups (always run after queries)
        elif method == "POST" and not has_param and cat == TestCategory.HAPPY_PATH:
            return 1  # Wave 1: Root Entity Creation (populates StatePool)
        elif cat == TestCategory.HAPPY_PATH and method in ("GET", "HEAD") and not has_param:
            return 2  # Wave 2: General List Queries (harvests further entities)
        elif test.test_type == TestType.BROWSER:
            return 5  # Wave 5: Browser tests
        else:
            return 3  # Wave 3: Detail queries, validation, boundary, negative, auth

    def _partition_into_waves(self, tests: list[TestCase]) -> list[list[TestCase]]:
        """Groups tests into sequential dependency tiers while preserving concurrency within each tier."""
        waves_dict: dict[int, list[TestCase]] = {}
        for t in tests:
            w = self.get_test_wave(t)
            waves_dict.setdefault(w, []).append(t)
        return [waves_dict[k] for k in sorted(waves_dict.keys())]

    async def _execute_wave(
        self,
        wave_tests: list[TestCase],
        results: list[TestResult],
        results_lock: asyncio.Lock,
    ) -> None:
        """Executes a single wave of tests concurrently."""
        queue: asyncio.Queue[TestCase | None] = asyncio.Queue()
        for t in wave_tests:
            await queue.put(t)

        async def worker(worker_num: int):
            worker_id = f"worker-{worker_num}"
            current_worker_id.set(worker_id)

            while not self._cancelled:
                test: TestCase | None = None
                try:
                    test = await queue.get()
                    if test is None:
                        queue.task_done()
                        break

                    if self.on_test_start:
                        try:
                            await self.on_test_start(test)
                        except Exception as start_err:
                            logger.warning(f"Worker {worker_id} on_test_start warning: {start_err}")

                    # Execute depending on test type
                    if test.test_type == TestType.BROWSER:
                        res = await self.browser_runner.execute_test(test)
                    else:
                        res = await self.api_runner.execute_test(test)

                    async with results_lock:
                        results.append(res)

                    if self.on_test_complete:
                        try:
                            await self.on_test_complete(test, res)
                        except Exception as comp_err:
                            logger.warning(
                                f"Worker {worker_id} on_test_complete warning: {comp_err}"
                            )

                    queue.task_done()
                except asyncio.CancelledError:
                    if test is not None:
                        queue.task_done()
                    break
                except Exception as e:
                    logger.error(f"Worker {worker_id} exception: {e}")
                    if test is not None:
                        now = datetime.now(timezone.utc)
                        err_res = TestResult(
                            test_id=test.id,
                            test_name=test.name,
                            category=test.category,
                            test_type=test.test_type,
                            status=TestStatus.ERROR,
                            duration_ms=0.0,
                            started_at=now,
                            completed_at=now,
                            failure_evidence=FailureEvidence(
                                failure_category=FailureCategory.INFRASTRUCTURE_ERROR,
                                message=f"Worker caught unhandled execution exception: {e}",
                                stack_trace=str(e),
                            ),
                        )
                        async with results_lock:
                            if not any(r.test_id == test.id for r in results):
                                results.append(err_res)
                    queue.task_done()

        worker_count = min(self.concurrency, len(wave_tests) or 1)
        worker_tasks = [asyncio.create_task(worker(i + 1)) for i in range(worker_count)]

        await queue.join()

        for _ in worker_tasks:
            await queue.put(None)

        await asyncio.gather(*worker_tasks, return_exceptions=True)

    async def execute_suite(self, tests: list[TestCase]) -> list[TestResult]:
        """Executes test cases in topological dependency waves with bounded concurrency."""
        results: list[TestResult] = []
        results_lock = asyncio.Lock()
        waves = self._partition_into_waves(tests)

        for wave_tests in waves:
            if self._cancelled:
                break
            await self._execute_wave(wave_tests, results, results_lock)

        return results

    def cancel(self):
        """Cancels remaining test executions."""
        self._cancelled = True
