from __future__ import annotations

import base64
import html
import json
from pathlib import Path

from recon.common.models import RunSummary, TestResult


class HTMLReporter:
    """Generates an interactive, accessible, modern, standalone HTML report."""

    def __init__(self, output_dir: Path | str = "./reports"):
        self.output_dir = Path(output_dir)

    def write_report(self, summary: RunSummary, results: list[TestResult]) -> Path:
        """Renders and saves report.html in run folder and latest.html in root reports folder."""
        run_dir = self.output_dir / f"run-{summary.run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)
        report_file = run_dir / "report.html"

        html_content = self._render_html(summary, results)
        report_file.write_text(html_content, encoding="utf-8")

        latest_file = self.output_dir / "latest.html"
        latest_file.write_text(html_content, encoding="utf-8")

        return report_file

    def _render_html(self, summary: RunSummary, results: list[TestResult]) -> str:
        total = summary.total
        passed = summary.passed
        failed = summary.failed + summary.errors
        pass_rate = round((passed / total * 100) if total > 0 else 0, 1)
        fail_rate = round(100.0 - pass_rate, 1) if total > 0 else 0
        hero_status_color = (
            "#10b981" if failed == 0 and total > 0 else ("#ef4444" if failed > 0 else "#94a3b8")
        )

        # Embed screenshot images as base64 if they exist on disk
        tests_json = []
        for r in results:
            item = r.model_dump(mode="json")
            if r.failure_evidence and r.failure_evidence.screenshots:
                for s_idx, sc in enumerate(r.failure_evidence.screenshots):
                    p = Path(sc.file_path)
                    if p.exists():
                        try:
                            data_b64 = base64.b64encode(p.read_bytes()).decode()
                            item["failure_evidence"]["screenshots"][s_idx]["base64"] = (
                                f"data:image/png;base64,{data_b64}"
                            )
                        except Exception:
                            pass
            tests_json.append(item)

        tests_data_script = json.dumps(tests_json).replace("</script>", "<\\/script>")

        # Escape values for safe HTML rendering
        safe_run_id = html.escape(str(summary.run_id))
        safe_target_url = html.escape(str(summary.target_url))

        # Format taxonomy breakdown
        if summary.failure_breakdown:
            tax_items_html = "".join(
                f'<div class="tax-item"><span class="tax-name">{html.escape(k)}</span>'
                f'<span class="tax-badge app-err" aria-label="{v} occurrences">{v}</span></div>'
                for k, v in summary.failure_breakdown.items()
            )
        else:
            tax_items_html = (
                '<div class="tax-item zero-state"><span class="status-icon" aria-hidden="true">✓</span>'
                '<span style="color: var(--pass); font-weight: 600;">Zero Failures Detected</span></div>'
            )

        # Format category breakdown
        if summary.category_breakdown:
            cat_items_html = "".join(
                f'<div class="tax-item"><span class="tax-name">{html.escape(k)}</span>'
                f'<span class="tax-badge" aria-label="{sum(v.values())} tests">{sum(v.values())} tests</span></div>'
                for k, v in summary.category_breakdown.items()
            )
        else:
            cat_items_html = '<div class="tax-item"><span>General API Suite</span></div>'

        return f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="Recon Automated QA Test Run Execution Report for {safe_target_url}">
    <title>Recon QA Report - {safe_run_id}</title>
    <style>
        :root {{
            --bg: #f8fafc;
            --surface: #ffffff;
            --surface-card: #f1f5f9;
            --surface-hover: #e2e8f0;
            --border: #cbd5e1;
            --border-subtle: #e2e8f0;
            --text: #0f172a;
            --text-muted: #334155;
            --text-dim: #475569;
            --accent: #2563eb;
            --accent-hover: #1d4ed8;
            --accent-glow: rgba(37, 99, 235, 0.15);
            --pass: #047857;
            --pass-bg: rgba(4, 120, 87, 0.1);
            --pass-border: #059669;
            --fail: #b91c1c;
            --fail-bg: rgba(185, 28, 28, 0.1);
            --fail-border: #dc2626;
            --warn: #b45309;
            --warn-bg: rgba(180, 83, 9, 0.1);
            --info: #0284c7;
            --info-bg: rgba(2, 132, 199, 0.1);
            --code-bg: #f1f5f9;
            --code-text: #0f172a;
            --radius-sm: 0.25rem;
            --radius-md: 0.375rem;
            --radius-lg: 0.5rem;
            --radius-full: 9999px;
            --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        }}

        html.dark {{
            --bg: #0b0f19;
            --surface: #111827;
            --surface-card: #182234;
            --surface-hover: #223048;
            --border: #2e3a51;
            --border-subtle: #1f293d;
            --text: #f9fafb;
            --text-muted: #cbd5e1;
            --text-dim: #94a3b8;
            --accent: #3b82f6;
            --accent-hover: #2563eb;
            --accent-glow: rgba(59, 130, 246, 0.2);
            --pass: #10b981;
            --pass-bg: rgba(16, 185, 129, 0.14);
            --pass-border: #059669;
            --fail: #ef4444;
            --fail-bg: rgba(239, 68, 68, 0.14);
            --fail-border: #dc2626;
            --warn: #f59e0b;
            --warn-bg: rgba(245, 158, 11, 0.14);
            --info: #38bdf8;
            --info-bg: rgba(56, 189, 248, 0.14);
            --code-bg: #090d16;
            --code-text: #e2e8f0;
        }}

        *, *::before, *::after {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            background-color: var(--bg);
            color: var(--text);
            font-family: var(--font-sans);
            line-height: 1.5;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            padding: 1.5rem;
            transition: background-color 0.2s ease, color 0.2s ease;
        }}

        /* Skip Link for Keyboard Accessibility */
        .skip-link {{
            position: absolute;
            top: -60px;
            left: 1rem;
            background: var(--text);
            color: var(--bg);
            padding: 0.6rem 1.2rem;
            z-index: 1000;
            border-radius: var(--radius-md);
            font-weight: 700;
            text-decoration: none;
            transition: top 0.2s ease-in-out;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }}
        .skip-link:focus {{
            top: 1rem;
            outline: 3px solid var(--accent);
            outline-offset: 2px;
        }}

        /* High-Contrast Focus Visible Ring */
        :focus-visible {{
            outline: 2px solid var(--accent);
            outline-offset: 2px;
        }}

        .container {{
            max-width: 1280px;
            width: 100%;
            margin: 0 auto;
        }}

        /* Header / Banner */
        .report-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 1.25rem;
            margin-bottom: 1.75rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid var(--border);
        }}
        .brand-cluster {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}
        .badge-logo {{
            background: var(--surface-card);
            border: 1px solid var(--border);
            color: var(--text);
            font-weight: 800;
            font-size: 0.95rem;
            letter-spacing: 0.08em;
            padding: 0.4rem 0.85rem;
            border-radius: var(--radius-md);
        }}
        .title-block h1 {{
            font-size: 1.65rem;
            font-weight: 800;
            letter-spacing: -0.02em;
        }}
        .title-meta {{
            font-size: 0.875rem;
            color: var(--text-muted);
            margin-top: 0.25rem;
            word-break: break-all;
        }}
        .title-meta code {{
            background: var(--surface-card);
            border: 1px solid var(--border);
            padding: 0.15rem 0.4rem;
            border-radius: var(--radius-sm);
            font-family: var(--font-mono);
            font-size: 0.82rem;
            color: var(--text);
        }}
        .header-actions {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            flex-wrap: wrap;
        }}
        .meta-pill {{
            font-size: 0.85rem;
            font-weight: 600;
            padding: 0.4rem 0.85rem;
            border-radius: var(--radius-full);
            background: var(--surface-card);
            border: 1px solid var(--border);
            color: var(--text-muted);
        }}
        .btn-theme {{
            background: var(--surface-card);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 0.45rem 0.85rem;
            border-radius: var(--radius-md);
            cursor: pointer;
            font-size: 0.85rem;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            transition: background 0.15s ease, border-color 0.15s ease;
            min-height: 40px;
        }}
        .btn-theme:hover {{
            background: var(--surface-hover);
            border-color: var(--text-dim);
        }}

        /* Progress Bar */
        .progress-wrapper {{
            margin-bottom: 2rem;
        }}
        .progress-meta {{
            display: flex;
            justify-content: space-between;
            font-size: 0.85rem;
            font-weight: 700;
            margin-bottom: 0.4rem;
            color: var(--text-muted);
        }}
        .progress-bar-container {{
            width: 100%;
            height: 10px;
            background: var(--surface-card);
            border-radius: var(--radius-full);
            overflow: hidden;
            border: 1px solid var(--border);
            display: flex;
        }}
        .progress-fill-pass {{
            background: var(--pass);
            height: 100%;
            transition: width 0.3s ease;
        }}
        .progress-fill-fail {{
            background: var(--fail);
            height: 100%;
            transition: width 0.3s ease;
        }}

        /* Section Headings */
        .section-header {{
            margin-bottom: 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 0.75rem;
        }}
        .section-header h2 {{
            font-size: 1.25rem;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .kbd-hint {{
            font-size: 0.75rem;
            color: var(--text-muted);
            font-family: var(--font-mono);
            background: var(--surface-card);
            padding: 0.25rem 0.6rem;
            border-radius: var(--radius-sm);
            border: 1px solid var(--border);
        }}
        .kbd-pill {{
            display: inline-block;
            padding: 0.1rem 0.35rem;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 3px;
            font-family: var(--font-mono);
            font-size: 0.75rem;
            color: var(--text);
            font-weight: 700;
        }}

        /* Metric Grid */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 1.25rem;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            transition: border-color 0.15s ease;
        }}
        .card:hover {{
            border-color: var(--text-dim);
        }}
        .card-label {{
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: var(--text-muted);
            font-weight: 700;
            margin-bottom: 0.35rem;
        }}
        .card-value {{
            font-size: 2.1rem;
            font-weight: 900;
            line-height: 1.1;
        }}
        .card-value.pass {{ color: var(--pass); }}
        .card-value.fail {{ color: var(--fail); }}
        .card-value.info {{ color: var(--info); }}
        .card-subtext {{
            font-size: 0.8rem;
            color: var(--text-dim);
            margin-top: 0.35rem;
        }}

        /* Breakdown Section */
        .breakdown-section {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
            margin-bottom: 2.5rem;
        }}
        .breakdown-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 1.25rem;
        }}
        .breakdown-card h3 {{
            font-size: 1.05rem;
            font-weight: 700;
            margin-bottom: 1rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 0.6rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .tax-list {{
            display: flex;
            flex-direction: column;
            gap: 0.6rem;
        }}
        .tax-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.6rem 0.85rem;
            background: var(--surface-card);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-sm);
            font-size: 0.875rem;
        }}
        .tax-item.zero-state {{
            background: var(--pass-bg);
            border-color: var(--pass-border);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .tax-name {{
            font-weight: 600;
            color: var(--text);
        }}
        .tax-badge {{
            font-size: 0.75rem;
            font-weight: 700;
            padding: 0.25rem 0.6rem;
            border-radius: var(--radius-sm);
            background: var(--surface-hover);
            color: var(--text);
            border: 1px solid var(--border);
        }}
        .tax-badge.app-err {{
            background: var(--fail-bg);
            color: var(--fail);
            border: 1px solid var(--fail-border);
        }}

        /* Controls Bar */
        .controls {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 1rem;
            margin-bottom: 1.25rem;
            padding: 0.85rem 1rem;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
        }}
        .filter-controls {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            flex-wrap: wrap;
        }}
        .btn-filter {{
            background: var(--surface-card);
            border: 1px solid var(--border);
            color: var(--text-muted);
            padding: 0.5rem 0.95rem;
            border-radius: var(--radius-sm);
            cursor: pointer;
            font-size: 0.875rem;
            font-weight: 600;
            min-height: 40px;
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            transition: all 0.15s ease;
        }}
        .btn-filter:hover {{
            background: var(--surface-hover);
            color: var(--text);
            border-color: var(--text-dim);
        }}
        .btn-filter[aria-pressed="true"], .btn-filter.active {{
            background: var(--accent);
            color: #ffffff;
            border-color: var(--accent);
        }}
        .batch-actions {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            flex-wrap: wrap;
        }}
        .btn-action {{
            background: var(--surface-card);
            border: 1px solid var(--border);
            color: var(--text-muted);
            padding: 0.5rem 0.85rem;
            border-radius: var(--radius-sm);
            cursor: pointer;
            font-size: 0.825rem;
            font-weight: 600;
            min-height: 40px;
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            transition: all 0.15s ease;
        }}
        .btn-action:hover {{
            background: var(--surface-hover);
            color: var(--text);
            border-color: var(--text-dim);
        }}
        .sort-select {{
            background: var(--surface-card);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 0.5rem 0.85rem;
            border-radius: var(--radius-sm);
            font-size: 0.825rem;
            font-weight: 600;
            min-height: 40px;
            cursor: pointer;
        }}
        .search-wrapper {{
            position: relative;
            flex-grow: 1;
            max-width: 340px;
            display: flex;
            align-items: center;
        }}
        .search-box {{
            background: var(--surface-card);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 0.55rem 2rem 0.55rem 0.95rem;
            border-radius: var(--radius-sm);
            font-size: 0.875rem;
            width: 100%;
            min-height: 40px;
            transition: border-color 0.15s ease;
        }}
        .search-box:focus {{
            border-color: var(--accent);
        }}
        .search-box::placeholder {{
            color: var(--text-dim);
        }}
        .btn-clear-search {{
            position: absolute;
            right: 0.5rem;
            background: transparent;
            border: none;
            color: var(--text-dim);
            cursor: pointer;
            font-size: 1.1rem;
            line-height: 1;
            padding: 0.25rem;
            display: none;
        }}
        .btn-clear-search:hover {{
            color: var(--text);
        }}

        /* Test List */
        .test-list {{
            display: flex;
            flex-direction: column;
            gap: 0.85rem;
            list-style: none;
        }}
        .test-row {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            overflow: hidden;
            transition: border-color 0.15s ease;
        }}
        .test-row.failed {{
            border-left: 4px solid var(--fail);
        }}
        .test-row.passed {{
            border-left: 4px solid var(--pass);
        }}
        .test-header-btn {{
            appearance: none;
            background: transparent;
            border: none;
            width: 100%;
            text-align: left;
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem 1.25rem;
            cursor: pointer;
            color: inherit;
            font-family: inherit;
            transition: background 0.15s ease;
        }}
        .test-header-btn:hover {{
            background: var(--surface-hover);
        }}
        .test-info {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            flex-wrap: wrap;
        }}
        .test-id {{
            font-family: var(--font-mono);
            font-size: 0.8rem;
            background: var(--surface-card);
            padding: 0.2rem 0.5rem;
            border-radius: var(--radius-sm);
            border: 1px solid var(--border-subtle);
            color: var(--text);
            font-weight: 700;
        }}
        .test-name {{
            font-weight: 700;
            font-size: 0.95rem;
        }}
        .status-pill {{
            font-size: 0.75rem;
            font-weight: 800;
            letter-spacing: 0.04em;
            padding: 0.2rem 0.6rem;
            border-radius: var(--radius-full);
            text-transform: uppercase;
        }}
        .status-pill.passed {{
            background: var(--pass-bg);
            color: var(--pass);
            border: 1px solid var(--pass-border);
        }}
        .status-pill.failed {{
            background: var(--fail-bg);
            color: var(--fail);
            border: 1px solid var(--fail-border);
        }}
        .status-pill.error {{
            background: var(--fail-bg);
            color: var(--fail);
            border: 1px solid var(--fail-border);
        }}
        .test-tag {{
            font-size: 0.75rem;
            font-weight: 600;
            padding: 0.2rem 0.5rem;
            border-radius: var(--radius-sm);
            background: var(--surface-card);
            border: 1px solid var(--border-subtle);
            color: var(--text-muted);
        }}
        .test-meta-right {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            font-size: 0.85rem;
            color: var(--text-muted);
            white-space: nowrap;
        }}
        .toggle-icon {{
            font-size: 0.75rem;
            transition: transform 0.2s ease;
            display: inline-block;
            color: var(--text-dim);
        }}
        .test-header-btn[aria-expanded="true"] .toggle-icon {{
            transform: rotate(180deg);
        }}

        /* Failure Preview in Header */
        .failure-preview {{
            display: block;
            width: 100%;
            font-size: 0.8rem;
            color: var(--fail);
            font-family: var(--font-mono);
            margin-top: 0.25rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        /* Test Body Region */
        .test-body {{
            padding: 1.25rem;
            border-top: 1px solid var(--border);
            background: var(--surface-card);
        }}
        .test-body[hidden] {{
            display: none;
        }}

        /* RCA Box */
        .rca-box {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-left: 4px solid var(--accent);
            border-radius: var(--radius-sm);
            padding: 1.15rem;
            margin-bottom: 1.25rem;
        }}
        .rca-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-bottom: 0.75rem;
        }}
        .rca-title {{
            font-weight: 800;
            font-size: 0.95rem;
            color: var(--text);
            display: flex;
            align-items: center;
            gap: 0.4rem;
        }}
        .confidence-badge {{
            font-size: 0.75rem;
            font-weight: 700;
            padding: 0.2rem 0.5rem;
            border-radius: var(--radius-full);
            background: var(--surface-hover);
            color: var(--text);
            border: 1px solid var(--border);
        }}
        .rca-section {{
            margin-top: 0.75rem;
            font-size: 0.875rem;
        }}
        .rca-section-title {{
            font-weight: 700;
            color: var(--text);
            margin-bottom: 0.35rem;
        }}
        .rca-facts-list {{
            padding-left: 1.25rem;
            color: var(--text-muted);
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }}
        .rca-hypothesis {{
            color: var(--text-muted);
            line-height: 1.45;
        }}
        .rca-fix-container {{
            margin-top: 0.85rem;
            display: flex;
            flex-direction: column;
            gap: 0.35rem;
        }}
        .rca-fix {{
            background: var(--pass-bg);
            border-left: 3px solid var(--pass);
            border-radius: var(--radius-sm);
            padding: 0.75rem 0.85rem;
            font-size: 0.875rem;
            color: var(--text);
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
        }}
        .btn-copy {{
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text-muted);
            padding: 0.3rem 0.65rem;
            border-radius: var(--radius-sm);
            cursor: pointer;
            font-size: 0.75rem;
            font-weight: 600;
            white-space: nowrap;
            transition: all 0.15s ease;
        }}
        .btn-copy:hover {{
            background: var(--surface-hover);
            color: var(--text);
            border-color: var(--text-dim);
        }}

        /* Steps & Diagnostic Logs */
        .evidence-section {{
            margin-top: 1.25rem;
        }}
        .evidence-heading {{
            font-size: 0.85rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
        }}
        .steps-container {{
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }}
        .step-item {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            padding: 0.85rem 1rem;
        }}
        .step-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-weight: 700;
            font-size: 0.9rem;
            margin-bottom: 0.5rem;
        }}
        .step-error {{
            color: var(--fail);
            background: var(--fail-bg);
            border: 1px solid var(--fail-border);
            border-radius: var(--radius-sm);
            padding: 0.5rem 0.75rem;
            margin-bottom: 0.65rem;
            font-size: 0.85rem;
            font-family: var(--font-mono);
            word-break: break-all;
        }}
        .trace-box {{
            position: relative;
            margin-top: 0.5rem;
        }}
        .trace-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.4rem 0.75rem;
            background: var(--surface-hover);
            border: 1px solid var(--border);
            border-bottom: none;
            border-radius: var(--radius-sm) var(--radius-sm) 0 0;
            font-size: 0.8rem;
            color: var(--text-muted);
            gap: 0.5rem;
            flex-wrap: wrap;
        }}
        .trace-actions {{
            display: flex;
            gap: 0.4rem;
        }}
        pre {{
            background: var(--code-bg);
            color: var(--code-text);
            border: 1px solid var(--border);
            border-radius: 0 0 var(--radius-sm) var(--radius-sm);
            padding: 0.85rem;
            overflow-x: auto;
            font-family: var(--font-mono);
            font-size: 0.825rem;
            line-height: 1.45;
            tab-size: 2;
        }}

        /* Diagnostic Tables */
        .diag-table-wrap {{
            overflow-x: auto;
            border-radius: var(--radius-sm);
            border: 1px solid var(--border);
            margin-top: 0.5rem;
        }}
        .diag-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.825rem;
            text-align: left;
        }}
        .diag-table th {{
            background: var(--surface-hover);
            padding: 0.5rem 0.75rem;
            color: var(--text-muted);
            border-bottom: 1px solid var(--border);
        }}
        .diag-table td {{
            padding: 0.5rem 0.75rem;
            border-bottom: 1px solid var(--border-subtle);
            color: var(--text);
            font-family: var(--font-mono);
            word-break: break-all;
        }}
        .diag-table tr:last-child td {{
            border-bottom: none;
        }}

        /* Collapsible details */
        details.diag-details {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            padding: 0.75rem;
            margin-top: 0.75rem;
        }}
        details.diag-details summary {{
            font-weight: 700;
            font-size: 0.85rem;
            cursor: pointer;
            color: var(--text);
        }}

        /* Screenshot */
        .screenshot-thumb-section {{
            margin-top: 1.25rem;
        }}
        .screenshot-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            padding: 0.75rem;
            display: inline-block;
            max-width: 100%;
        }}
        .screenshot-img-btn {{
            appearance: none;
            background: none;
            border: none;
            padding: 0;
            cursor: pointer;
            display: block;
            border-radius: var(--radius-sm);
            overflow: hidden;
        }}
        .screenshot-img-btn img {{
            max-width: 100%;
            max-height: 360px;
            display: block;
            border-radius: var(--radius-sm);
            border: 1px solid var(--border);
            transition: opacity 0.15s ease;
        }}
        .screenshot-img-btn:hover img {{
            opacity: 0.9;
        }}
        .screenshot-caption {{
            font-size: 0.75rem;
            color: var(--text-dim);
            margin-top: 0.5rem;
            text-align: center;
        }}

        /* Modal Dialog */
        .modal-dialog {{
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            background: var(--surface);
            color: var(--text);
            padding: 1.5rem;
            max-width: 90vw;
            max-height: 90vh;
            margin: auto;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
        }}
        .modal-dialog::backdrop {{
            background: rgba(0, 0, 0, 0.75);
            backdrop-filter: blur(2px);
        }}
        .modal-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
            gap: 1rem;
        }}
        .modal-title {{
            font-size: 1.1rem;
            font-weight: 700;
        }}
        .modal-close-btn {{
            background: var(--surface-card);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 0.4rem 0.8rem;
            border-radius: var(--radius-sm);
            cursor: pointer;
            font-weight: 700;
            font-size: 0.85rem;
        }}
        .modal-close-btn:hover {{
            background: var(--surface-hover);
        }}
        .modal-body img {{
            max-width: 100%;
            max-height: 75vh;
            border-radius: var(--radius-sm);
            border: 1px solid var(--border);
            object-fit: contain;
        }}

        /* Shortcuts Table in Modal */
        .shortcuts-grid {{
            display: grid;
            grid-template-columns: auto 1fr;
            gap: 0.6rem 1.25rem;
            align-items: center;
            font-size: 0.875rem;
            margin-top: 1rem;
            padding: 0.5rem 0;
        }}
        .shortcuts-grid kbd {{
            background: var(--surface-card);
            border: 1px solid var(--border);
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-family: var(--font-mono);
            font-weight: 700;
            text-align: center;
        }}

        /* Empty State */
        .empty-state {{
            text-align: center;
            padding: 3rem 1.5rem;
            color: var(--text-muted);
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 1rem;
        }}

        /* Toast Feedback */
        .toast-notification {{
            position: fixed;
            bottom: 1.5rem;
            right: 1.5rem;
            background: var(--surface);
            color: var(--text);
            border: 1px solid var(--pass-border);
            border-left: 4px solid var(--pass);
            padding: 0.75rem 1.25rem;
            border-radius: var(--radius-sm);
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
            font-size: 0.875rem;
            font-weight: 600;
            z-index: 2000;
            display: none;
        }}

        /* Footer */
        .report-footer {{
            margin-top: auto;
            padding-top: 3rem;
            padding-bottom: 1rem;
            text-align: center;
            color: var(--text-dim);
            font-size: 0.85rem;
            border-top: 1px solid var(--border-subtle);
        }}

        /* Accessibility Utility */
        .sr-only {{
            position: absolute;
            width: 1px;
            height: 1px;
            padding: 0;
            margin: -1px;
            overflow: hidden;
            clip: rect(0, 0, 0, 0);
            white-space: nowrap;
            border: 0;
        }}

        /* Reduced Motion */
        @media (prefers-reduced-motion: reduce) {{
            *, *::before, *::after {{
                animation-duration: 0.01ms !important;
                animation-iteration-count: 1 !important;
                transition-duration: 0.01ms !important;
                scroll-behavior: auto !important;
            }}
        }}

        /* Responsive Breakpoints */
        @media (max-width: 900px) {{
            .breakdown-section {{
                grid-template-columns: 1fr;
            }}
        }}

        @media (max-width: 768px) {{
            body {{
                padding: 1rem;
            }}
            .report-header {{
                flex-direction: column;
                align-items: flex-start;
                gap: 1rem;
            }}
            .stats-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
            .controls {{
                flex-direction: column;
                align-items: stretch;
            }}
            .filter-controls, .batch-actions {{
                width: 100%;
                justify-content: flex-start;
            }}
            .search-wrapper {{
                max-width: 100%;
                width: 100%;
            }}
        }}

        @media (max-width: 480px) {{
            .stats-grid {{
                grid-template-columns: 1fr;
            }}
            .test-header-btn {{
                flex-direction: column;
                align-items: flex-start;
                gap: 0.75rem;
            }}
            .test-meta-right {{
                align-self: flex-start;
            }}
        }}

        /* Print Stylesheet */
        @media print {{
            body {{
                background: #ffffff !important;
                color: #000000 !important;
                padding: 0 !important;
            }}
            .skip-link, .controls, .header-actions, .modal-dialog, .btn-copy, .btn-action, .btn-theme, .toast-notification {{
                display: none !important;
            }}
            .card, .breakdown-card, .test-row, .step-item {{
                background: #ffffff !important;
                border: 1px solid #d1d5db !important;
                color: #000000 !important;
                page-break-inside: avoid;
            }}
            .card-label, .tax-name, .test-name {{
                color: #111827 !important;
            }}
            .test-body {{
                display: block !important;
                background: #ffffff !important;
                color: #000000 !important;
            }}
            pre {{
                background: #f3f4f6 !important;
                color: #111827 !important;
                border: 1px solid #e5e7eb !important;
            }}
        }}
    </style>
</head>
<body>
    <a href="#main-content" class="skip-link">Skip to main content</a>

    <header class="report-header" role="banner">
        <div class="brand-cluster">
            <div class="badge-logo" aria-hidden="true">RECON</div>
            <div class="title-block">
                <h1>QA Test Report</h1>
                <p class="title-meta">
                    Target: <strong>{safe_target_url}</strong> &bull; Run ID: <code>{safe_run_id}</code>
                </p>
            </div>
        </div>
        <div class="header-actions">
            <button type="button" class="btn-theme" id="themeToggle" onclick="toggleTheme()" aria-label="Toggle visual theme">🌓 Theme</button>
            <span class="meta-pill" aria-label="Execution duration">⏱ Duration: {summary.duration_seconds:.2f}s</span>
            <span class="meta-pill" aria-label="Pass rate">Pass Rate: {pass_rate}%</span>
        </div>
    </header>

    <main id="main-content" class="container" role="main">
        <!-- Visual Progress Bar -->
        <div class="progress-wrapper" aria-hidden="true">
            <div class="progress-meta">
                <span>Pass Rate: {pass_rate}% ({passed}/{total} Passed)</span>
                <span>Failure Rate: {fail_rate}% ({failed} Failed)</span>
            </div>
            <div class="progress-bar-container" role="progressbar" aria-valuenow="{pass_rate}" aria-valuemin="0" aria-valuemax="100" aria-label="Suite Pass Rate">
                <div class="progress-fill-pass" style="width: {pass_rate}%;"></div>
                <div class="progress-fill-fail" style="width: {fail_rate}%;"></div>
            </div>
        </div>

        <!-- Metric Grid -->
        <section aria-labelledby="heading-metrics" class="section-block">
            <h2 id="heading-metrics" class="sr-only">Execution Metrics</h2>
            <div class="stats-grid">
                <div class="card">
                    <div class="card-label">Total Tests</div>
                    <div class="card-value info">{total}</div>
                    <div class="card-subtext">Executed in wave orchestration</div>
                </div>
                <div class="card">
                    <div class="card-label">Passed</div>
                    <div class="card-value pass">{passed}</div>
                    <div class="card-subtext">Met all assertions</div>
                </div>
                <div class="card">
                    <div class="card-label">Failed & Errors</div>
                    <div class="card-value fail">{failed}</div>
                    <div class="card-subtext">Required attention</div>
                </div>
                <div class="card">
                    <div class="card-label">Overall Pass Rate</div>
                    <div class="card-value" style="color: {hero_status_color};">{pass_rate}%</div>
                    <div class="card-subtext">Target threshold: 100%</div>
                </div>
            </div>
        </section>

        <!-- Breakdown Section -->
        <section aria-labelledby="heading-breakdowns" class="breakdown-section">
            <div class="breakdown-card">
                <h3 id="heading-breakdowns">Failure Taxonomy Breakdown</h3>
                <div class="tax-list">
                    {tax_items_html}
                </div>
            </div>
            <div class="breakdown-card">
                <h3>Category Distribution</h3>
                <div class="tax-list">
                    {cat_items_html}
                </div>
            </div>
        </section>

        <!-- Test Results Section -->
        <section aria-labelledby="heading-results">
            <div class="section-header">
                <h2 id="heading-results">Test Execution Results</h2>
                <div class="kbd-hint" aria-hidden="true">Shortcuts: [/] search &bull; [e] expand all &bull; [c] collapse all &bull; [?] help</div>
            </div>

            <!-- Controls -->
            <div class="controls" role="region" aria-label="Test filters and search">
                <div class="filter-controls" role="group" aria-label="Filter tests by status">
                    <button type="button" class="btn-filter active" id="filter-all" aria-pressed="true" onclick="setFilter('ALL')">All ({total})</button>
                    <button type="button" class="btn-filter" id="filter-failed" aria-pressed="false" onclick="setFilter('FAILED')">Failed ({failed})</button>
                    <button type="button" class="btn-filter" id="filter-passed" aria-pressed="false" onclick="setFilter('PASSED')">Passed ({passed})</button>
                </div>

                <div class="batch-actions" role="group" aria-label="Batch display and sort actions">
                    <button type="button" class="btn-action" id="btnExpandAll" onclick="toggleAllTests(true)">Expand All</button>
                    <button type="button" class="btn-action" id="btnCollapseAll" onclick="toggleAllTests(false)">Collapse All</button>
                    <button type="button" class="btn-action" id="btnExpandFailed" onclick="expandFailedOnly()">Expand Failed Only</button>
                    <button type="button" class="btn-action" id="btnShortcuts" onclick="openShortcutsModal()" aria-label="Show keyboard shortcuts">Shortcuts <kbd class="kbd-pill">?</kbd></button>

                    <label for="sortSelect" class="sr-only">Sort tests</label>
                    <select id="sortSelect" class="sort-select" onchange="setSort(this.value)" aria-label="Sort tests">
                        <option value="default">Sort: Execution Order</option>
                        <option value="duration-desc">Sort: Slowest First</option>
                        <option value="duration-asc">Sort: Fastest First</option>
                        <option value="status">Sort: Failed First</option>
                        <option value="name">Sort: Name (A-Z)</option>
                    </select>
                </div>

                <div class="search-wrapper">
                    <label for="searchInput" class="sr-only">Filter tests by name or ID</label>
                    <input type="search" id="searchInput" class="search-box" placeholder="Filter tests (Press '/' to focus)..." oninput="onSearchInput()" autocomplete="off">
                    <button type="button" class="btn-clear-search" id="btnClearSearch" onclick="clearSearch()" aria-label="Clear search input">&times;</button>
                </div>
            </div>

            <!-- Screen-reader live region for dynamic filtering updates -->
            <div id="filterStatus" class="sr-only" aria-live="polite" aria-atomic="true">Showing all tests</div>

            <!-- Test List Container -->
            <div class="test-list" id="testList" role="region" aria-label="Detailed test cases"></div>
        </section>
    </main>

    <!-- Fullscreen Screenshot Modal Dialog -->
    <dialog id="screenshotModal" class="modal-dialog" aria-labelledby="modalTitle">
        <div class="modal-header">
            <h3 id="modalTitle" class="modal-title">Failure Evidence Screenshot</h3>
            <button type="button" class="modal-close-btn" onclick="closeScreenshotModal()" aria-label="Close screenshot modal">&times; Close</button>
        </div>
        <div class="modal-body" style="text-align: center;">
            <img id="modalImg" src="" alt="Enlarged failure evidence screenshot">
        </div>
    </dialog>

    <!-- Keyboard Shortcuts Help Modal Dialog -->
    <dialog id="shortcutsModal" class="modal-dialog" aria-labelledby="shortcutsTitle">
        <div class="modal-header">
            <h3 id="shortcutsTitle" class="modal-title">Keyboard Shortcuts</h3>
            <button type="button" class="modal-close-btn" onclick="closeShortcutsModal()" aria-label="Close shortcuts dialog">&times; Close</button>
        </div>
        <div class="shortcuts-grid">
            <kbd>/</kbd><span>Focus search filter</span>
            <kbd>e</kbd><span>Expand all tests</span>
            <kbd>c</kbd><span>Collapse all tests</span>
            <kbd>f</kbd><span>Filter failed tests</span>
            <kbd>p</kbd><span>Filter passed tests</span>
            <kbd>a</kbd><span>Show all tests</span>
            <kbd>t</kbd><span>Toggle dark / light theme</span>
            <kbd>?</kbd><span>Open keyboard shortcuts help</span>
            <kbd>Esc</kbd><span>Close dialogs or clear search filter</span>
        </div>
    </dialog>

    <!-- Accessible Notification Toast -->
    <div id="toastNotification" class="toast-notification" role="status" aria-live="polite"></div>

    <footer class="report-footer" role="contentinfo">
        <p>Generated by <strong>Recon Autonomous QA Engine</strong> &bull; Version 0.3.1 &bull; Run <code>recon --help</code> for options</p>
    </footer>

    <script>
        const rawTests = {tests_data_script};
        let currentFilter = 'ALL';
        let currentSort = 'default';
        let searchDebounceTimer = null;

        function toggleTheme() {{
            const isDark = document.documentElement.classList.toggle('dark');
            try {{
                localStorage.setItem('recon-theme', isDark ? 'dark' : 'light');
            }} catch (e) {{}}
        }}

        // Check stored theme
        try {{
            const savedTheme = localStorage.getItem('recon-theme');
            if (savedTheme === 'light') {{
                document.documentElement.classList.remove('dark');
            }}
        }} catch (e) {{}}

        // Global keyboard shortcuts
        document.addEventListener('keydown', (e) => {{
            const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
            const isInput = activeTag === 'input' || activeTag === 'textarea' || activeTag === 'select';

            if (e.key === 'Escape') {{
                const scModal = document.getElementById('screenshotModal');
                const shModal = document.getElementById('shortcutsModal');
                if (scModal && scModal.open) {{
                    scModal.close();
                    return;
                }}
                if (shModal && shModal.open) {{
                    shModal.close();
                    return;
                }}
                if (isInput) {{
                    document.activeElement.blur();
                    clearSearch();
                    return;
                }}
            }}

            if (isInput) return;

            if (e.key === '/') {{
                e.preventDefault();
                const search = document.getElementById('searchInput');
                if (search) {{
                    search.focus();
                    search.select();
                }}
            }} else if (e.key === 'e' || e.key === 'E') {{
                e.preventDefault();
                toggleAllTests(true);
            }} else if (e.key === 'c' || e.key === 'C') {{
                e.preventDefault();
                toggleAllTests(false);
            }} else if (e.key === 'f' || e.key === 'F') {{
                e.preventDefault();
                setFilter('FAILED');
            }} else if (e.key === 'p' || e.key === 'P') {{
                e.preventDefault();
                setFilter('PASSED');
            }} else if (e.key === 'a' || e.key === 'A') {{
                e.preventDefault();
                setFilter('ALL');
            }} else if (e.key === 't' || e.key === 'T') {{
                e.preventDefault();
                toggleTheme();
            }} else if (e.key === '?') {{
                e.preventDefault();
                openShortcutsModal();
            }}
        }});

        function onSearchInput() {{
            const searchInput = document.getElementById('searchInput');
            const clearBtn = document.getElementById('btnClearSearch');
            if (clearBtn) {{
                clearBtn.style.display = searchInput.value ? 'block' : 'none';
            }}
            renderTests();
        }}

        function clearSearch() {{
            const searchInput = document.getElementById('searchInput');
            const clearBtn = document.getElementById('btnClearSearch');
            if (searchInput) {{
                searchInput.value = '';
                searchInput.focus();
            }}
            if (clearBtn) {{
                clearBtn.style.display = 'none';
            }}
            renderTests();
        }}

        function setSort(sortValue) {{
            currentSort = sortValue;
            renderTests();
        }}

        function getSortedTests(testsList) {{
            const list = [...testsList];
            if (currentSort === 'duration-desc') {{
                return list.sort((a, b) => (b.duration_ms || 0) - (a.duration_ms || 0));
            }} else if (currentSort === 'duration-asc') {{
                return list.sort((a, b) => (a.duration_ms || 0) - (b.duration_ms || 0));
            }} else if (currentSort === 'status') {{
                return list.sort((a, b) => {{
                    const aFail = a.status === 'FAILED' || a.status === 'ERROR' ? 0 : 1;
                    const bFail = b.status === 'FAILED' || b.status === 'ERROR' ? 0 : 1;
                    return aFail - bFail;
                }});
            }} else if (currentSort === 'name') {{
                return list.sort((a, b) => (a.test_name || '').localeCompare(b.test_name || ''));
            }}
            return list;
        }}

        function renderTests() {{
            const listEl = document.getElementById('testList');
            const searchInput = document.getElementById('searchInput');
            const search = (searchInput.value || '').toLowerCase().trim();
            listEl.innerHTML = '';

            const filtered = rawTests.filter(t => {{
                const isFail = t.status === 'FAILED' || t.status === 'ERROR';
                const statusMatch = currentFilter === 'ALL' ||
                    (currentFilter === 'PASSED' && t.status === 'PASSED') ||
                    (currentFilter === 'FAILED' && isFail);

                const tName = (t.test_name || '').toLowerCase();
                const tId = (t.test_id || '').toLowerCase();
                const tCategory = (t.category || '').toLowerCase();
                const searchMatch = !search || tName.includes(search) || tId.includes(search) || tCategory.includes(search);

                return statusMatch && searchMatch;
            }});

            const sorted = getSortedTests(filtered);

            const filterStatusEl = document.getElementById('filterStatus');
            if (filterStatusEl) {{
                filterStatusEl.textContent = `Showing ${{sorted.length}} of ${{rawTests.length}} tests`;
            }}

            if (sorted.length === 0) {{
                listEl.innerHTML = `
                    <div class="empty-state">
                        <p>No tests match the current filter or search criteria.</p>
                        <button type="button" class="btn-action" onclick="resetFilters()">Reset All Filters</button>
                    </div>`;
                return;
            }}

            const fragment = document.createDocumentFragment();

            sorted.forEach((t, idx) => {{
                const isFail = t.status === 'FAILED' || t.status === 'ERROR';
                const el = document.createElement('article');
                el.className = `test-row ${{isFail ? 'failed' : 'passed'}}`;

                // Failure message preview in header
                let failurePreview = '';
                if (isFail) {{
                    const msg = (t.failure_evidence && t.failure_evidence.message) ||
                                (t.step_results && t.step_results.find(s => s.error_message)?.error_message) ||
                                'Test assertions failed';
                    failurePreview = `<span class="failure-preview" title="${{escapeHtml(msg)}}">&bull; ${{escapeHtml(msg)}}</span>`;
                }}

                let rcaHtml = '';
                if (t.failure_analysis) {{
                    const fa = t.failure_analysis;
                    const confidence = Math.round((fa.confidence_score || 0) * 100);

                    const factsList = (fa.observed_facts && fa.observed_facts.length)
                        ? `<div class="rca-section">
                             <div class="rca-section-title">Observed Facts:</div>
                             <ul class="rca-facts-list">${{fa.observed_facts.map(f => `<li>${{escapeHtml(f)}}</li>`).join('')}}</ul>
                           </div>`
                        : '';

                    const hypothesis = (fa.hypotheses && fa.hypotheses.length)
                        ? `<div class="rca-section">
                             <div class="rca-section-title">Hypothesis:</div>
                             <p class="rca-hypothesis">${{escapeHtml(fa.hypotheses[0].hypothesis)}}</p>
                           </div>`
                        : '';

                    const suggestedFix = fa.suggested_fix
                        ? `<div class="rca-fix-container">
                             <div class="rca-section-title">Recommended Remediation:</div>
                             <div class="rca-fix">
                               <div class="rca-fix-text" id="fix-text-${{idx}}">${{escapeHtml(fa.suggested_fix)}}</div>
                               <button type="button" class="btn-copy" onclick="copyById(this, 'fix-text-${{idx}}', 'Fix')" aria-label="Copy suggested fix">Copy Fix</button>
                             </div>
                           </div>`
                        : '';

                    rcaHtml = `
                        <div class="rca-box" role="region" aria-label="Root Cause Analysis">
                            <div class="rca-header">
                                <span class="rca-title">Root Cause Analysis</span>
                                <span class="confidence-badge">Confidence: ${{confidence}}%</span>
                            </div>
                            ${{factsList}}
                            ${{hypothesis}}
                            ${{suggestedFix}}
                        </div>
                    `;
                }}

                let stepsHtml = '';
                if (t.step_results && t.step_results.length) {{
                    stepsHtml = t.step_results.map((s, sIdx) => {{
                        let traceSnippet = '';
                        if (s.http_trace) {{
                            const method = s.http_trace.request_method || 'GET';
                            const url = s.http_trace.request_url || '';
                            const status = s.http_trace.response_status || 'Network Error';
                            const bodyJson = JSON.stringify(s.http_trace.response_body, null, 2);
                            const traceRaw = `${{method}} ${{url}}\\nStatus: ${{status}}\\n\\nResponse Body:\\n${{bodyJson}}`;
                            const traceId = `trace-${{idx}}-${{sIdx}}`;

                            // Build cURL command for quick reproduction
                            let curlCmd = `curl -X ${{method}} "${{url}}"`;
                            if (s.http_trace.request_headers) {{
                                for (const [hk, hv] of Object.entries(s.http_trace.request_headers)) {{
                                    curlCmd += ` -H "${{hk}}: ${{hv}}"`;
                                }}
                            }}
                            if (s.http_trace.request_body) {{
                                const reqBodyStr = typeof s.http_trace.request_body === 'string'
                                    ? s.http_trace.request_body
                                    : JSON.stringify(s.http_trace.request_body);
                                curlCmd += ` -H "Content-Type: application/json" -d '${{reqBodyStr.replace(/'/g, "'\\\\''")}}'`;
                            }}

                            traceSnippet = `
                                <div class="trace-box">
                                    <div class="trace-header">
                                        <span><strong>${{escapeHtml(method)}}</strong> ${{escapeHtml(url)}} &rarr; Status: ${{status}}</span>
                                        <div class="trace-actions">
                                            <button type="button" class="btn-copy" onclick="copyRawText(this, ${{JSON.stringify(curlCmd)}}, 'cURL')" aria-label="Copy as cURL command">Copy cURL</button>
                                            <button type="button" class="btn-copy" onclick="copyById(this, '${{traceId}}', 'Trace')" aria-label="Copy HTTP trace">Copy Trace</button>
                                        </div>
                                    </div>
                                    <pre><code id="${{traceId}}">${{escapeHtml(traceRaw)}}</code></pre>
                                </div>
                            `;
                        }}

                        return `
                            <div class="step-item">
                                <div class="step-header">
                                    <span>${{escapeHtml(s.step_name)}}</span>
                                    <span>${{s.duration_ms}}ms &bull; <strong style="color: ${{s.status === 'PASSED' ? 'var(--pass)' : 'var(--fail)'}}">${{s.status}}</strong></span>
                                </div>
                                ${{s.error_message ? `<div class="step-error">Failure: ${{escapeHtml(s.error_message)}}</div>` : ''}}
                                ${{traceSnippet}}
                            </div>
                        `;
                    }}).join('');
                }}

                // Diagnostic Logs: Console errors
                let consoleLogsHtml = '';
                if (t.failure_evidence && t.failure_evidence.console_errors && t.failure_evidence.console_errors.length) {{
                    consoleLogsHtml = `
                        <div class="evidence-section">
                            <div class="evidence-heading">Browser Console Errors (${{t.failure_evidence.console_errors.length}})</div>
                            <div class="diag-table-wrap">
                                <table class="diag-table">
                                    <thead><tr><th>Level</th><th>Message</th><th>Location</th></tr></thead>
                                    <tbody>
                                        ${{t.failure_evidence.console_errors.map(c => `
                                            <tr>
                                                <td><span style="color: var(--fail); font-weight: bold;">${{escapeHtml(c.level || 'error')}}</span></td>
                                                <td>${{escapeHtml(c.text || '')}}</td>
                                                <td>${{escapeHtml(c.location || 'inline')}}</td>
                                            </tr>
                                        `).join('')}}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    `;
                }}

                // Diagnostic Logs: Stack trace
                let stackTraceHtml = '';
                if (t.failure_evidence && t.failure_evidence.stack_trace) {{
                    const st = t.failure_evidence.stack_trace;
                    const stId = `stacktrace-${{idx}}`;
                    stackTraceHtml = `
                        <details class="diag-details" open>
                            <summary>Diagnostic Stack Trace</summary>
                            <div style="margin-top: 0.5rem; display: flex; justify-content: flex-end;">
                                <button type="button" class="btn-copy" onclick="copyById(this, '${{stId}}', 'Stack Trace')" aria-label="Copy stack trace">Copy Stack Trace</button>
                            </div>
                            <pre><code id="${{stId}}">${{escapeHtml(st)}}</code></pre>
                        </details>
                    `;
                }}

                let screenshotHtml = '';
                if (t.failure_evidence && t.failure_evidence.screenshots && t.failure_evidence.screenshots.length) {{
                    const sc = t.failure_evidence.screenshots[0];
                    if (sc.base64) {{
                        screenshotHtml = `
                            <div class="screenshot-thumb-section">
                                <div class="evidence-heading">Browser Failure Screenshot (Click to enlarge)</div>
                                <div class="screenshot-card">
                                    <button type="button" class="screenshot-img-btn" onclick="openScreenshotModal('${{sc.base64}}')" aria-label="Open enlarged screenshot in modal dialog">
                                        <img src="${{sc.base64}}" alt="Browser state at failure for ${{escapeHtml(t.test_id)}}" />
                                    </button>
                                    <div class="screenshot-caption">Captured viewport on assertion failure</div>
                                </div>
                            </div>
                        `;
                    }}
                }}

                el.innerHTML = `
                    <button type="button" class="test-header-btn" id="btn-toggle-${{idx}}" aria-expanded="false" aria-controls="body-${{idx}}" onclick="toggleTest(${{idx}})">
                        <div class="test-info">
                            <span class="test-id">${{escapeHtml(t.test_id)}}</span>
                            <span class="status-pill ${{t.status.toLowerCase()}}">${{t.status}}</span>
                            <span class="test-name">${{escapeHtml(t.test_name)}}</span>
                            <span class="test-tag">${{escapeHtml(t.test_type)}}</span>
                            <span class="test-tag">${{escapeHtml(t.category)}}</span>
                            ${{failurePreview}}
                        </div>
                        <div class="test-meta-right">
                            <span>${{t.duration_ms}}ms</span>
                            <span class="toggle-icon" aria-hidden="true">&#9660;</span>
                        </div>
                    </button>
                    <div class="test-body" id="body-${{idx}}" role="region" aria-labelledby="btn-toggle-${{idx}}" hidden>
                        ${{rcaHtml}}
                        <div class="evidence-heading">Execution Steps & Traces</div>
                        <div class="steps-container">
                            ${{stepsHtml || '<div style="color: var(--text-dim); font-size: 0.85rem;">No individual step logs recorded.</div>'}}
                        </div>
                        ${{consoleLogsHtml}}
                        ${{stackTraceHtml}}
                        ${{screenshotHtml}}
                    </div>
                `;
                fragment.appendChild(el);
            }});

            listEl.appendChild(fragment);
        }}

        function toggleTest(idx) {{
            const bodyEl = document.getElementById(`body-${{idx}}`);
            const btnEl = document.getElementById(`btn-toggle-${{idx}}`);
            if (bodyEl && btnEl) {{
                const isHidden = bodyEl.hasAttribute('hidden');
                if (isHidden) {{
                    bodyEl.removeAttribute('hidden');
                    btnEl.setAttribute('aria-expanded', 'true');
                }} else {{
                    bodyEl.setAttribute('hidden', '');
                    btnEl.setAttribute('aria-expanded', 'false');
                }}
            }}
        }}

        function toggleAllTests(expand) {{
            const buttons = document.querySelectorAll('.test-header-btn');
            buttons.forEach(btn => {{
                const targetId = btn.getAttribute('aria-controls');
                const bodyEl = document.getElementById(targetId);
                if (bodyEl) {{
                    if (expand) {{
                        bodyEl.removeAttribute('hidden');
                        btn.setAttribute('aria-expanded', 'true');
                        bodyEl.querySelectorAll('details').forEach(d => d.open = true);
                    }} else {{
                        bodyEl.setAttribute('hidden', '');
                        btn.setAttribute('aria-expanded', 'false');
                        bodyEl.querySelectorAll('details').forEach(d => d.open = false);
                    }}
                }}
            }});
        }}

        function expandFailedOnly() {{
            const rows = document.querySelectorAll('.test-row');
            rows.forEach(row => {{
                const btn = row.querySelector('.test-header-btn');
                const bodyEl = row.querySelector('.test-body');
                if (!btn || !bodyEl) return;
                if (row.classList.contains('failed')) {{
                    bodyEl.removeAttribute('hidden');
                    btn.setAttribute('aria-expanded', 'true');
                    bodyEl.querySelectorAll('details').forEach(d => d.open = true);
                }} else {{
                    bodyEl.setAttribute('hidden', '');
                    btn.setAttribute('aria-expanded', 'false');
                }}
            }});
            showToast('Expanded failure diagnostics');
        }}

        function setFilter(filter) {{
            currentFilter = filter;
            const filterButtons = [
                {{ id: 'filter-all', key: 'ALL' }},
                {{ id: 'filter-failed', key: 'FAILED' }},
                {{ id: 'filter-passed', key: 'PASSED' }}
            ];

            filterButtons.forEach(f => {{
                const btn = document.getElementById(f.id);
                if (btn) {{
                    const isActive = f.key === filter;
                    btn.classList.toggle('active', isActive);
                    btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
                }}
            }});
            renderTests();
        }}

        function filterTests() {{
            renderTests();
        }}

        function resetFilters() {{
            clearSearch();
            setFilter('ALL');
        }}

        function copyById(buttonEl, elementId, label) {{
            const el = document.getElementById(elementId);
            const text = el ? el.textContent : '';
            copySnippet(buttonEl, text, label);
        }}

        function copyRawText(buttonEl, text, label) {{
            copySnippet(buttonEl, text, label);
        }}

        function copySnippet(buttonEl, text, label = '') {{
            function fallbackCopy() {{
                try {{
                    const textarea = document.createElement('textarea');
                    textarea.value = text;
                    textarea.style.position = 'fixed';
                    textarea.style.opacity = '0';
                    document.body.appendChild(textarea);
                    textarea.focus();
                    textarea.select();
                    const successful = document.execCommand('copy');
                    document.body.removeChild(textarea);
                    showCopiedFeedback(buttonEl, successful ? 'Copied!' : 'Copied');
                    showToast(label ? `Copied ${{label}} to clipboard` : 'Copied to clipboard');
                }} catch (e) {{
                    showCopiedFeedback(buttonEl, 'Copied');
                }}
            }}

            if (navigator.clipboard && window.isSecureContext) {{
                navigator.clipboard.writeText(text).then(() => {{
                    showCopiedFeedback(buttonEl, 'Copied!');
                    showToast(label ? `Copied ${{label}} to clipboard` : 'Copied to clipboard');
                }}).catch(() => {{
                    fallbackCopy();
                }});
            }} else {{
                fallbackCopy();
            }}
        }}

        function showCopiedFeedback(btn, text = 'Copied!') {{
            const orig = btn.textContent;
            btn.textContent = text;
            btn.style.color = 'var(--pass)';
            btn.style.borderColor = 'var(--pass)';
            setTimeout(() => {{
                btn.textContent = orig;
                btn.style.color = '';
                btn.style.borderColor = '';
            }}, 2000);
        }}

        function showToast(message) {{
            const toast = document.getElementById('toastNotification');
            if (!toast) return;
            toast.textContent = message;
            toast.style.display = 'block';
            clearTimeout(window.__toastTimer);
            window.__toastTimer = setTimeout(() => {{
                toast.style.display = 'none';
            }}, 3000);
        }}

        function openScreenshotModal(base64Src) {{
            const dialog = document.getElementById('screenshotModal');
            const img = document.getElementById('modalImg');
            if (dialog && img) {{
                img.src = base64Src;
                dialog.showModal();
            }}
        }}

        function closeScreenshotModal() {{
            const dialog = document.getElementById('screenshotModal');
            if (dialog) {{
                dialog.close();
            }}
        }}

        function openShortcutsModal() {{
            const dialog = document.getElementById('shortcutsModal');
            if (dialog) {{
                dialog.showModal();
            }}
        }}

        function closeShortcutsModal() {{
            const dialog = document.getElementById('shortcutsModal');
            if (dialog) {{
                dialog.close();
            }}
        }}

        // Close modals on outside backdrop click
        ['screenshotModal', 'shortcutsModal'].forEach(modalId => {{
            const dialog = document.getElementById(modalId);
            dialog?.addEventListener('click', (e) => {{
                const rect = dialog.getBoundingClientRect();
                const isInDialog = (rect.top <= e.clientY && e.clientY <= rect.top + rect.height &&
                                    rect.left <= e.clientX && e.clientX <= rect.left + rect.width);
                if (!isInDialog) {{
                    dialog.close();
                }}
            }});
        }});

        function escapeHtml(str) {{
            if (!str) return '';
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }}

        // Initial Render
        renderTests();
    </script>
</body>
</html>
"""
