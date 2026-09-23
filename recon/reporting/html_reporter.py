from __future__ import annotations

import base64
import html
import json
from pathlib import Path

from recon.common.models import RunSummary, TestResult


class HTMLReporter:
    """Generates an interactive, modern, standalone HTML report."""

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
        pass_rate = round((summary.passed / summary.total * 100) if summary.total > 0 else 0, 1)
        hero_status_color = "#10b981" if summary.failed == 0 and summary.errors == 0 else "#ef4444"

        # Embed screenshot images as base64 if they exist
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

        tests_data_script = json.dumps(tests_json)

        return f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Recon QA Report - {html.escape(summary.run_id)}</title>
    <style>
        :root {{
            --bg: #090d16;
            --surface: #111827;
            --surface-hover: #1f2937;
            --border: #374151;
            --text: #f9fafb;
            --text-muted: #9ca3af;
            --accent: #6366f1;
            --accent-hover: #4f46e5;
            --pass: #10b981;
            --fail: #ef4444;
            --warn: #f59e0b;
            --info: #3b82f6;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
        body {{ background-color: var(--bg); color: var(--text); padding: 2rem; line-height: 1.5; }}
        .container {{ max-width: 1300px; margin: 0 auto; }}

        /* Header */
        header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; padding-bottom: 1.5rem; border-bottom: 1px solid var(--border); }}
        .brand {{ display: flex; align-items: center; gap: 0.75rem; }}
        .badge-logo {{ background: linear-gradient(135deg, #6366f1, #a855f7); color: white; font-weight: 800; font-size: 1.1rem; padding: 0.35rem 0.75rem; border-radius: 0.5rem; letter-spacing: 0.05em; }}
        .title h1 {{ font-size: 1.6rem; font-weight: 700; }}
        .title p {{ font-size: 0.9rem; color: var(--text-muted); }}

        /* Metric Grid */
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
        .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 0.75rem; padding: 1.25rem; }}
        .card-label {{ font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); font-weight: 600; margin-bottom: 0.25rem; }}
        .card-value {{ font-size: 1.8rem; font-weight: 800; }}
        .card-value.pass {{ color: var(--pass); }}
        .card-value.fail {{ color: var(--fail); }}
        .card-value.info {{ color: var(--info); }}

        /* Breakdown Section */
        .breakdown-section {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 2rem; }}
        .breakdown-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 0.75rem; padding: 1.25rem; }}
        .breakdown-card h3 {{ font-size: 1.1rem; margin-bottom: 1rem; color: var(--text); border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }}
        .tax-list {{ display: flex; flex-direction: column; gap: 0.5rem; }}
        .tax-item {{ display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0.75rem; background: var(--surface-hover); border-radius: 0.375rem; font-size: 0.875rem; }}
        .tax-badge {{ font-size: 0.75rem; font-weight: 700; padding: 0.2rem 0.5rem; border-radius: 0.25rem; background: #374151; }}
        .tax-badge.app-err {{ background: #7f1d1d; color: #fca5a5; }}
        .tax-badge.assert-err {{ background: #831843; color: #fbcfe8; }}
        .tax-badge.val-err {{ background: #78350f; color: #fde68a; }}
        .tax-badge.auth-err {{ background: #581c87; color: #e9d5ff; }}

        /* Filters & Table */
        .controls {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }}
        .filter-group {{ display: flex; gap: 0.5rem; }}
        .btn-filter {{ background: var(--surface); border: 1px solid var(--border); color: var(--text-muted); padding: 0.4rem 0.85rem; border-radius: 0.375rem; cursor: pointer; font-size: 0.875rem; font-weight: 500; }}
        .btn-filter.active {{ background: var(--accent); color: white; border-color: var(--accent); }}
        .search-box {{ background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 0.4rem 0.85rem; border-radius: 0.375rem; font-size: 0.875rem; width: 260px; }}

        .test-list {{ display: flex; flex-direction: column; gap: 0.75rem; }}
        .test-row {{ background: var(--surface); border: 1px solid var(--border); border-radius: 0.5rem; overflow: hidden; transition: all 0.2s; }}
        .test-row.failed {{ border-left: 4px solid var(--fail); }}
        .test-row.passed {{ border-left: 4px solid var(--pass); }}
        .test-header {{ display: flex; justify-content: space-between; align-items: center; padding: 1rem 1.25rem; cursor: pointer; user-select: none; }}
        .test-header:hover {{ background: var(--surface-hover); }}
        .test-info {{ display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; }}
        .test-id {{ font-family: monospace; font-size: 0.8rem; background: #1f2937; padding: 0.2rem 0.4rem; border-radius: 0.25rem; color: #9ca3af; }}
        .test-name {{ font-weight: 600; font-size: 0.95rem; }}
        .status-pill {{ font-size: 0.75rem; font-weight: 700; padding: 0.2rem 0.6rem; border-radius: 9999px; text-transform: uppercase; }}
        .status-pill.passed {{ background: rgba(16, 185, 129, 0.2); color: #34d399; }}
        .status-pill.failed {{ background: rgba(239, 68, 68, 0.2); color: #f87171; }}
        .status-pill.error {{ background: rgba(239, 68, 68, 0.3); color: #fca5a5; }}

        .test-body {{ display: none; padding: 1.25rem; border-top: 1px solid var(--border); background: #0c111d; }}
        .test-body.open {{ display: block; }}

        /* RCA Box */
        .rca-box {{ background: rgba(99, 102, 241, 0.1); border: 1px solid rgba(99, 102, 241, 0.3); border-radius: 0.5rem; padding: 1rem; margin-bottom: 1.25rem; }}
        .rca-title {{ font-weight: 700; font-size: 0.9rem; color: #a5b4fc; margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.5rem; }}
        .rca-section {{ margin-top: 0.5rem; font-size: 0.875rem; }}
        .rca-section-title {{ font-weight: 600; color: #e0e7ff; margin-bottom: 0.25rem; }}
        .rca-fix {{ background: rgba(16, 185, 129, 0.1); border-left: 3px solid var(--pass); padding: 0.5rem 0.75rem; border-radius: 0.25rem; margin-top: 0.5rem; font-size: 0.875rem; color: #a7f3d0; }}

        /* Traces & Code */
        pre {{ background: #111827; border: 1px solid var(--border); border-radius: 0.375rem; padding: 0.75rem; overflow-x: auto; font-family: monospace; font-size: 0.82rem; color: #e5e7eb; }}
        .step-item {{ background: #111827; border: 1px solid var(--border); border-radius: 0.375rem; padding: 0.75rem; margin-bottom: 0.75rem; }}
        .step-header {{ display: flex; justify-content: space-between; font-weight: 600; font-size: 0.875rem; margin-bottom: 0.5rem; }}

        /* Screenshot Thumbnail */
        .screenshot-thumb {{ margin-top: 1rem; }}
        .screenshot-thumb img {{ max-width: 100%; max-height: 400px; border-radius: 0.375rem; border: 1px solid var(--border); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.5); cursor: pointer; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="brand">
                <div class="badge-logo">RECON</div>
                <div class="title">
                    <h1>QA Test Report</h1>
                    <p>Target: <strong>{html.escape(summary.target_url)}</strong> &bull; Run ID: <code>{html.escape(summary.run_id)}</code></p>
                </div>
            </div>
            <div>
                <span class="tax-badge" style="font-size: 0.9rem; padding: 0.5rem 1rem;">Duration: {summary.duration_seconds:.2f}s</span>
            </div>
        </header>

        <!-- Metric Grid -->
        <div class="stats-grid">
            <div class="card">
                <div class="card-label">Total Tests</div>
                <div class="card-value">{summary.total}</div>
            </div>
            <div class="card">
                <div class="card-label">Passed</div>
                <div class="card-value pass">{summary.passed}</div>
            </div>
            <div class="card">
                <div class="card-label">Failed</div>
                <div class="card-value fail">{summary.failed + summary.errors}</div>
            </div>
            <div class="card">
                <div class="card-label">Pass Rate</div>
                <div class="card-value" style="color: {hero_status_color};">{pass_rate}%</div>
            </div>
        </div>

        <!-- Breakdown Section -->
        <div class="breakdown-section">
            <div class="breakdown-card">
                <h3>Failure Taxonomy Breakdown</h3>
                <div class="tax-list">
                    {"".join(f'<div class="tax-item"><span>{html.escape(k)}</span><span class="tax-badge app-err">{v}</span></div>' for k, v in summary.failure_breakdown.items()) if summary.failure_breakdown else '<div class="tax-item"><span style="color: var(--pass);">Zero Failures Detected 🎉</span></div>'}
                </div>
            </div>
            <div class="breakdown-card">
                <h3>Category Distribution</h3>
                <div class="tax-list">
                    {"".join(f'<div class="tax-item"><span>{html.escape(k)}</span><span class="tax-badge">{sum(v.values())} tests</span></div>' for k, v in summary.category_breakdown.items()) if summary.category_breakdown else '<div class="tax-item"><span>General API Suite</span></div>'}
                </div>
            </div>
        </div>

        <!-- Controls -->
        <div class="controls">
            <div class="filter-group">
                <button class="btn-filter active" onclick="setFilter('ALL')">All ({summary.total})</button>
                <button class="btn-filter" onclick="setFilter('FAILED')">Failed ({summary.failed + summary.errors})</button>
                <button class="btn-filter" onclick="setFilter('PASSED')">Passed ({summary.passed})</button>
            </div>
            <input type="text" id="searchInput" class="search-box" placeholder="Filter by test name or ID..." oninput="filterTests()">
        </div>

        <!-- Test List Container -->
        <div class="test-list" id="testList"></div>
    </div>

    <script>
        const tests = {tests_data_script};
        let currentFilter = 'ALL';

        function renderTests() {{
            const listEl = document.getElementById('testList');
            const search = (document.getElementById('searchInput').value || '').toLowerCase();
            listEl.innerHTML = '';

            const filtered = tests.filter(t => {{
                const statusMatch = currentFilter === 'ALL' ||
                    (currentFilter === 'PASSED' && t.status === 'PASSED') ||
                    (currentFilter === 'FAILED' && (t.status === 'FAILED' || t.status === 'ERROR'));
                const searchMatch = t.test_name.toLowerCase().includes(search) || t.test_id.toLowerCase().includes(search);
                return statusMatch && searchMatch;
            }});

            if (filtered.length === 0) {{
                listEl.innerHTML = '<div style="text-align: center; padding: 3rem; color: var(--text-muted);">No tests match the current filter.</div>';
                return;
            }}

            filtered.forEach((t, idx) => {{
                const isFail = t.status === 'FAILED' || t.status === 'ERROR';
                const el = document.createElement('div');
                el.className = `test-row ${{isFail ? 'failed' : 'passed'}}`;

                let rcaHtml = '';
                if (t.failure_analysis) {{
                    const fa = t.failure_analysis;
                    rcaHtml = `
                        <div class="rca-box">
                            <div class="rca-title">⚡ AI / Root Cause Analysis (Confidence: ${{Math.round(fa.confidence_score * 100)}}%)</div>
                            ${{fa.observed_facts && fa.observed_facts.length ? `
                                <div class="rca-section">
                                    <div class="rca-section-title">Observed Facts:</div>
                                    <ul style="padding-left: 1.25rem;">${{fa.observed_facts.map(f => `<li>${{escapeHtml(f)}}</li>`).join('')}}</ul>
                                </div>
                            ` : ''}}
                            ${{fa.hypotheses && fa.hypotheses.length ? `
                                <div class="rca-section" style="margin-top: 0.5rem;">
                                    <div class="rca-section-title">Hypothesis:</div>
                                    <p>${{escapeHtml(fa.hypotheses[0].hypothesis)}}</p>
                                </div>
                            ` : ''}}
                            ${{fa.suggested_fix ? `
                                <div class="rca-fix">
                                    <strong>Suggested Fix:</strong> ${{escapeHtml(fa.suggested_fix)}}
                                </div>
                            ` : ''}}
                        </div>
                    `;
                }}

                let stepsHtml = '';
                if (t.step_results && t.step_results.length) {{
                    stepsHtml = t.step_results.map(s => `
                        <div class="step-item">
                            <div class="step-header">
                                <span>${{escapeHtml(s.step_name)}}</span>
                                <span>${{s.duration_ms}}ms &bull; <strong style="color: ${{s.status === 'PASSED' ? 'var(--pass)' : 'var(--fail)'}}">${{s.status}}</strong></span>
                            </div>
                            ${{s.error_message ? `<div style="color: var(--fail); margin-bottom: 0.5rem; font-size: 0.85rem;">❌ ${{escapeHtml(s.error_message)}}</div>` : ''}}
                            ${{s.http_trace ? `
                                <pre><strong>${{s.http_trace.request_method}} ${{escapeHtml(s.http_trace.request_url)}}</strong> &rarr; Status: ${{s.http_trace.response_status || 'Network Error'}}\n\nResponse Body:\n${{escapeHtml(JSON.stringify(s.http_trace.response_body, null, 2))}}</pre>
                            ` : ''}}
                        </div>
                    `).join('');
                }}

                let screenshotHtml = '';
                if (t.failure_evidence && t.failure_evidence.screenshots && t.failure_evidence.screenshots.length) {{
                    const sc = t.failure_evidence.screenshots[0];
                    if (sc.base64) {{
                        screenshotHtml = `
                            <div class="screenshot-thumb">
                                <div class="card-label">Browser Failure Screenshot</div>
                                <img src="${{sc.base64}}" alt="Failure Screenshot" />
                            </div>
                        `;
                    }}
                }}

                el.innerHTML = `
                    <div class="test-header" onclick="toggleTest(${{idx}})">
                        <div class="test-info">
                            <span class="test-id">${{escapeHtml(t.test_id)}}</span>
                            <span class="status-pill ${{t.status.toLowerCase()}}">${{t.status}}</span>
                            <span class="test-name">${{escapeHtml(t.test_name)}}</span>
                            <span class="tax-badge">${{t.test_type}}</span>
                            <span class="tax-badge">${{t.category}}</span>
                        </div>
                        <div style="font-size: 0.85rem; color: var(--text-muted);">${{t.duration_ms}}ms</div>
                    </div>
                    <div class="test-body" id="body-${{idx}}">
                        ${{rcaHtml}}
                        <div class="card-label" style="margin-bottom: 0.5rem;">Execution Steps & Traces</div>
                        ${{stepsHtml}}
                        ${{screenshotHtml}}
                    </div>
                `;
                listEl.appendChild(el);
            }});
        }}

        function toggleTest(idx) {{
            const bodyEl = document.getElementById(`body-${{idx}}`);
            if (bodyEl) {{
                bodyEl.classList.toggle('open');
            }}
        }}

        function setFilter(filter) {{
            currentFilter = filter;
            document.querySelectorAll('.btn-filter').forEach(btn => {{
                btn.classList.toggle('active', btn.textContent.startsWith(filter === 'ALL' ? 'All' : filter === 'PASSED' ? 'Passed' : 'Failed'));
            }});
            renderTests();
        }}

        function filterTests() {{
            renderTests();
        }}

        function escapeHtml(str) {{
            if (!str) return '';
            return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }}

        // Initial render
        renderTests();
    </script>
</body>
</html>
"""
