from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Coroutine, Any

from recon.analysis.classifier import DeterministicFailureClassifier
from recon.analysis.rca_engine import RootCauseAnalyzer
from recon.common.config import settings
from recon.common.logging import current_run_id, logger
from recon.common.models import (
    FailureCategory,
    RunSummary,
    TestCase,
    TestResult,
    TestStatus,
)
from recon.discovery.endpoint_detector import discover_application
from recon.discovery.models import DiscoveredApplication
from recon.llm.failure_analyzer import AIFailureAnalyzer
from recon.llm.test_generator import AITestGenerator
from recon.orchestration.worker_pool import WorkerPool
from recon.persistence.database import DatabaseManager
from recon.planning.generator import TestSuiteGenerator
from recon.reporting.html_reporter import HTMLReporter
from recon.reporting.json_reporter import JSONReporter


class TestOrchestrator:
    """End-to-end Test Orchestration Coordinator."""
    __test__ = False

    def __init__(
        self,
        concurrency: int = 4,
        output_dir: Path | str = "./reports",
        enable_ai: bool = True,
        db_url: str | None = None,
        external_api_client: Any = None,
    ):
        self.concurrency = concurrency
        self.output_dir = Path(output_dir)
        self.enable_ai = enable_ai
        self.db = DatabaseManager(db_url)
        self.json_reporter = JSONReporter(self.output_dir)
        self.html_reporter = HTMLReporter(self.output_dir)
        self.ai_analyzer = AIFailureAnalyzer()
        self.ai_generator = AITestGenerator()
        self.external_api_client = external_api_client

    async def run_pipeline(
        self,
        target_url: str,
        spec_path_or_url: str | None = None,
        enable_browser: bool = False,
        headers: dict[str, str] | None = None,
        include_paths: list[str] | None = None,
        exclude_paths: list[str] | None = None,
        tags: list[str] | None = None,
        custom_tests: list[TestCase] | None = None,
        on_progress: Callable[[TestCase, TestResult], Coroutine[Any, Any, None]] | None = None,
    ) -> tuple[RunSummary, list[TestResult]]:
        """
        Full orchestration pipeline:
        1. Discover Application
        2. Plan Test Suite
        3. Execute Test Suite Concurrently
        4. Classify Failures
        5. Apply AI Root-Cause Analysis
        6. Persist results
        7. Generate JSON & HTML reports
        """
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        current_run_id.set(run_id)
        started_at = datetime.now(timezone.utc)
        start_time = time.perf_counter()

        logger.info(f"Starting Recon test run: run_id={run_id}, target={target_url}")

        # 1. Discover or use provided tests
        tests_to_run: list[TestCase] = []
        if custom_tests:
            tests_to_run = list(custom_tests)
        else:
            logger.info(f"Initiating discovery for target: {target_url}")
            app = await discover_application(
                target_url=target_url,
                spec_path_or_url=spec_path_or_url,
                enable_browser=enable_browser,
            )
            planner = TestSuiteGenerator(app, default_headers=headers)
            tests_to_run = planner.generate_suite()

            # AI exploratory test generation
            if self.enable_ai:
                logger.info("Generating exploratory test cases with AI...")
                ai_tests = await self.ai_generator.generate_exploratory_tests(app)
                tests_to_run.extend(ai_tests)

        # Filter by tags if provided
        if tags:
            tag_set = {t.lower() for t in tags}
            tests_to_run = [
                t for t in tests_to_run if any(tag.lower() in tag_set for tag in t.tags)
            ]

        # Filter by include_paths
        if include_paths:
            import fnmatch
            filtered = []
            for t in tests_to_run:
                for pattern in include_paths:
                    pattern_clean = pattern.strip()
                    if fnmatch.fnmatch(t.target, f"*{pattern_clean}*") or any(
                        fnmatch.fnmatch(s.endpoint or "", f"*{pattern_clean}*") for s in t.steps
                    ):
                        filtered.append(t)
                        break
            tests_to_run = filtered

        # Filter by exclude_paths
        if exclude_paths:
            import fnmatch
            tests_to_run = [
                t
                for t in tests_to_run
                if not any(
                    fnmatch.fnmatch(t.target, f"*{p.strip()}*")
                    or any(fnmatch.fnmatch(s.endpoint or "", f"*{p.strip()}*") for s in t.steps)
                    for p in exclude_paths
                )
            ]

        # 2. Execute tests concurrently
        test_map = {t.id: t for t in tests_to_run}
        worker_pool = WorkerPool(
            concurrency=self.concurrency,
            run_id=run_id,
            output_dir=self.output_dir,
            api_client=self.external_api_client,
            on_test_complete=on_progress,
        )

        logger.info(f"Executing {len(tests_to_run)} tests with concurrency={self.concurrency}")
        results = await worker_pool.execute_suite(tests_to_run)

        # 3. Classify Failures & Run Root Cause Analysis
        failure_breakdown: dict[str, int] = {}
        category_breakdown: dict[str, dict[str, int]] = {}
        failed_items: list[tuple[TestResult, TestCase | None]] = []

        for res in results:
            cat_name = res.category.value
            if cat_name not in category_breakdown:
                category_breakdown[cat_name] = {"passed": 0, "failed": 0}

            if res.status in (TestStatus.FAILED, TestStatus.ERROR):
                category_breakdown[cat_name]["failed"] += 1
                # Deterministic classification
                classified_cat = DeterministicFailureClassifier.classify(res)
                if res.failure_evidence:
                    res.failure_evidence.failure_category = classified_cat

                fail_key = classified_cat.value
                failure_breakdown[fail_key] = failure_breakdown.get(fail_key, 0) + 1

                # Deterministic baseline analysis immediately for all failed tests
                orig_test = test_map.get(res.test_id)
                res.failure_analysis = RootCauseAnalyzer.analyze(res, orig_test)
                failed_items.append((res, orig_test))
            else:
                category_breakdown[cat_name]["passed"] += 1

        # Deep AI RCA on sampled distinct failures concurrently (capped at 5 to ensure fast execution)
        if self.enable_ai and failed_items:
            seen_signatures: set[str] = set()
            sampled: list[tuple[TestResult, TestCase | None]] = []

            for res, orig_test in failed_items:
                cat_val = res.failure_evidence.failure_category.value if res.failure_evidence else "UNKNOWN"
                target_str = orig_test.target if orig_test else res.test_name
                sig = f"{cat_val}:{target_str}"
                if sig not in seen_signatures or len(sampled) < 3:
                    seen_signatures.add(sig)
                    sampled.append((res, orig_test))
                if len(sampled) >= 5:
                    break

            async def _run_ai_rca(r: TestResult, t: TestCase | None):
                try:
                    r.failure_analysis = await self.ai_analyzer.analyze_failure(r, t)
                except Exception as e:
                    logger.debug(f"AI RCA failed for {r.test_id}: {e}")

            await asyncio.gather(*[_run_ai_rca(r, t) for r, t in sampled])

        duration_seconds = round(time.perf_counter() - start_time, 2)
        completed_at = datetime.now(timezone.utc)

        passed_count = sum(1 for r in results if r.status == TestStatus.PASSED)
        failed_count = sum(1 for r in results if r.status == TestStatus.FAILED)
        error_count = sum(1 for r in results if r.status == TestStatus.ERROR)
        skipped_count = sum(1 for r in results if r.status == TestStatus.SKIPPED)

        exit_code = 0 if (failed_count == 0 and error_count == 0) else 1

        summary = RunSummary(
            run_id=run_id,
            target_url=target_url,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration_seconds,
            total=len(results),
            passed=passed_count,
            failed=failed_count,
            skipped=skipped_count,
            errors=error_count,
            failure_breakdown=failure_breakdown,
            category_breakdown=category_breakdown,
            exit_code=exit_code,
        )

        # 4. Save to Database
        try:
            await self.db.save_run(summary, results)
        except Exception as e:
            logger.warning(f"Database persistence warning: {e}")
        finally:
            await self.db.close()

        # 5. Write Reports
        self.json_reporter.write_reports(summary, results)
        self.html_reporter.write_report(summary, results)

        logger.info(
            f"Run completed: total={summary.total}, passed={summary.passed}, failed={summary.failed}, duration={summary.duration_seconds}s"
        )
        return summary, results
