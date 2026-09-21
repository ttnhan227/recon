from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Coroutine

from recon.common.logging import current_worker_id, logger
from recon.common.models import TestCase, TestResult, TestType
from recon.execution.api.runner import APITestRunner
from recon.execution.browser.runner import BrowserTestRunner


class WorkerPool:
    """Bounded asynchronous worker pool for executing test cases concurrently."""

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

    async def execute_suite(self, tests: list[TestCase]) -> list[TestResult]:
        """Executes a list of TestCases concurrently across the worker pool."""
        queue: asyncio.Queue[TestCase | None] = asyncio.Queue()
        results: list[TestResult] = []
        results_lock = asyncio.Lock()

        for t in tests:
            await queue.put(t)

        # Worker coroutine
        async def worker(worker_num: int):
            worker_id = f"worker-{worker_num}"
            current_worker_id.set(worker_id)

            while not self._cancelled:
                try:
                    test = await queue.get()
                    if test is None:
                        queue.task_done()
                        break

                    if self.on_test_start:
                        await self.on_test_start(test)

                    # Execute depending on test type
                    if test.test_type == TestType.BROWSER:
                        res = await self.browser_runner.execute_test(test)
                    else:
                        res = await self.api_runner.execute_test(test)

                    async with results_lock:
                        results.append(res)

                    if self.on_test_complete:
                        await self.on_test_complete(test, res)

                    queue.task_done()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Worker {worker_id} exception: {e}")
                    queue.task_done()

        # Launch workers
        worker_tasks = [
            asyncio.create_task(worker(i + 1))
            for i in range(min(self.concurrency, len(tests) or 1))
        ]

        await queue.join()

        # Signal workers to exit
        for _ in worker_tasks:
            await queue.put(None)

        await asyncio.gather(*worker_tasks, return_exceptions=True)
        return results

    def cancel(self):
        """Cancels remaining test executions."""
        self._cancelled = True
