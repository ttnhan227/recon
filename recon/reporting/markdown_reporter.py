from __future__ import annotations

import os
from pathlib import Path

from recon.common.models import RunSummary, TestResult, TestStatus


class MarkdownReporter:
    """Generates GitHub-Flavored Markdown summary reports for CI/CD environments."""

    def __init__(self, output_dir: Path | str = "./reports"):
        self.output_dir = Path(output_dir)

    def generate_markdown(self, summary: RunSummary, results: list[TestResult]) -> str:
        """Constructs a clean Markdown summary table and failure diagnostic log."""
        status_icon = "PASS" if summary.exit_code == 0 else "FAIL"
        status_badge = "[PASSED]" if summary.exit_code == 0 else "[FAILED]"

        md = [
            f"# Recon QA Test Run Summary: {status_badge}",
            "",
            f"**Target URL:** `{summary.target_url}`  ",
            f"**Run ID:** `{summary.run_id}`  ",
            f"**Duration:** `{summary.duration_seconds}s`  ",
        ]
        if summary.trace_id:
            md.append(f"**Trace ID:** `{summary.trace_id}`  ")
        md.extend(
            [
                "",
                "## Execution Overview",
                "",
                "| Total Checks | Passed | Failed | Errors | Skipped | Status |",
                "|:---:|:---:|:---:|:---:|:---:|:---:|",
                f"| {summary.total} | {summary.passed} | {summary.failed} | {summary.errors} | {summary.skipped} | **{status_icon}** |",
                "",
            ]
        )

        # Failure classification breakdown
        if summary.failure_breakdown:
            md.extend(
                [
                    "## Defect Classification Breakdown",
                    "",
                    "| Failure Category | Count |",
                    "|---|:---:|",
                ]
            )
            for category, count in sorted(
                summary.failure_breakdown.items(), key=lambda x: x[1], reverse=True
            ):
                md.append(f"| `{category}` | {count} |")
            md.append("")

        # Distributed tracing & latency summary
        if summary.trace_summary:
            md.extend(
                [
                    "## Distributed Tracing & Latency Summary",
                    "",
                ]
            )
            phases = summary.trace_summary.get("phase_durations_ms", {})
            if phases:
                md.extend(
                    [
                        "### Pipeline Phase Durations",
                        "",
                        "| Pipeline Phase | Duration |",
                        "|---|:---:|",
                    ]
                )
                for phase_name, dur_ms in phases.items():
                    md.append(f"| `{phase_name}` | {dur_ms:.2f} ms |")
                md.append("")

            waves = summary.trace_summary.get("wave_durations_ms", {})
            counts = summary.trace_summary.get("wave_counts", {})
            if waves:
                md.extend(
                    [
                        "### Wave Execution Latency",
                        "",
                        "| Wave | Test Count | Duration |",
                        "|---|:---:|:---:|",
                    ]
                )
                for w_key, dur_ms in sorted(waves.items()):
                    c = counts.get(w_key, "-")
                    md.append(f"| `{w_key}` | {c} | {dur_ms:.2f} ms |")
                md.append("")

            p50 = summary.trace_summary.get("http_latency_p50_ms")
            p95 = summary.trace_summary.get("http_latency_p95_ms")
            http_count = summary.trace_summary.get("http_requests_count", 0)
            if http_count:
                p50_str = f"{p50:.2f} ms" if p50 is not None else "N/A"
                p95_str = f"{p95:.2f} ms" if p95 is not None else "N/A"
                md.extend(
                    [
                        "### HTTP Request Latencies",
                        "",
                        f"- **Total HTTP Requests:** `{http_count}`",
                        f"- **p50 Latency:** `{p50_str}`",
                        f"- **p95 Latency:** `{p95_str}`",
                        "",
                    ]
                )

        # Failed checks diagnostics
        failed_results = [r for r in results if r.status in (TestStatus.FAILED, TestStatus.ERROR)]
        if failed_results:
            md.extend(
                [
                    "## Failed Check Diagnostics",
                    "",
                    "| Test Name | Category | Failure Reason |",
                    "|---|---|---|",
                ]
            )
            for res in failed_results[:15]:
                category = (
                    res.failure_evidence.failure_category.value
                    if res.failure_evidence
                    else "UNKNOWN"
                )
                reason = (res.failure_evidence.message if res.failure_evidence else "Check failed")[
                    :120
                ]
                # Sanitize pipes for markdown table
                clean_reason = reason.replace("|", "/")
                clean_name = res.test_name.replace("|", "/")
                md.append(f"| `{clean_name}` | `{category}` | {clean_reason} |")
            md.append("")

        return "\n".join(md)

    def write_report(self, summary: RunSummary, results: list[TestResult]) -> Path:
        """Writes summary.md and latest.md, and appends to GITHUB_STEP_SUMMARY if available."""
        run_dir = self.output_dir / f"run-{summary.run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)

        content = self.generate_markdown(summary, results)

        summary_file = run_dir / "summary.md"
        summary_file.write_text(content, encoding="utf-8")

        latest_file = self.output_dir / "latest.md"
        latest_file.write_text(content, encoding="utf-8")

        # Automatically export to GitHub Actions step summary if running in CI
        step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if step_summary:
            try:
                with open(step_summary, "a", encoding="utf-8") as f:
                    f.write(f"\n{content}\n")
            except Exception:
                pass

        return summary_file
