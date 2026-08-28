from __future__ import annotations

import json
from pathlib import Path
from recon.common.models import RunSummary, TestResult


class JSONReporter:
    """Generates machine-readable JSON reports."""

    def __init__(self, output_dir: Path | str = "./reports"):
        self.output_dir = Path(output_dir)

    def write_reports(self, summary: RunSummary, results: list[TestResult]) -> Path:
        """Writes summary.json and results.json to the run output directory."""
        run_dir = self.output_dir / f"run-{summary.run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)

        summary_file = run_dir / "summary.json"
        results_file = run_dir / "results.json"

        # Write summary.json
        summary_file.write_text(summary.model_dump_json(indent=2), encoding="utf-8")

        # Write results.json
        results_data = [r.model_dump(mode="json") for r in results]
        results_file.write_text(json.dumps(results_data, indent=2), encoding="utf-8")

        # Also write reports/latest.json for CLI convenience
        latest_file = self.output_dir / "latest.json"
        latest_file.write_text(
            json.dumps({"summary": summary.model_dump(mode="json"), "results": results_data}, indent=2),
            encoding="utf-8",
        )

        return run_dir
