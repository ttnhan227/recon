from __future__ import annotations

import json
import re
from typing import Any

from recon.analysis.rca_engine import RootCauseAnalyzer
from recon.common.logging import logger
from recon.common.models import FailureAnalysis, Hypothesis, TestCase, TestResult
from recon.llm.provider import LLMProvider, get_llm_provider

SYSTEM_PROMPT = """You are an expert QA Engineer and Systems Debugger.
Analyze the provided test failure data and produce a structured JSON response.

You MUST distinguish strictly between:
1. Observed Facts: What actually happened (status codes, errors, specific payloads).
2. Hypotheses: Your engineering reasoning of the root cause with a confidence score (0.0 to 1.0).
3. Suggested Fix: Actionable recommendation to fix the defect.

Your response MUST be valid JSON conforming to this schema:
{
  "observed_facts": ["fact 1", "fact 2"],
  "hypotheses": [
    {
      "hypothesis": "Root cause hypothesis",
      "confidence": 0.85,
      "explanation": "Why this is likely the cause"
    }
  ],
  "suggested_fix": "Concrete fix recommendation",
  "confidence_score": 0.85
}
Do NOT return markdown formatting or extra text, only valid JSON.
"""


class AIFailureAnalyzer:
    """Enhances deterministic failure analysis with LLM reasoning."""

    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider or get_llm_provider()

    async def analyze_failure(
        self, result: TestResult, test: TestCase | None = None
    ) -> FailureAnalysis:
        """Analyzes a failed TestResult and produces structured root cause analysis."""
        # Start with deterministic baseline
        baseline = RootCauseAnalyzer.analyze(result, test)

        if not result.failure_evidence:
            return baseline

        # Prepare evidence prompt
        ev = result.failure_evidence
        evidence_summary = {
            "test_id": result.test_id,
            "test_name": result.test_name,
            "test_category": result.category.value,
            "failure_category": ev.failure_category.value,
            "failed_step": ev.failed_step,
            "error_message": ev.message,
            "stack_trace": ev.stack_trace,
            "console_errors": [c.text for c in ev.console_errors],
            "network_errors": [f"{n.method} {n.url}: {n.error_text}" for n in ev.network_errors],
        }

        if ev.http_traces:
            last = ev.http_traces[-1]
            evidence_summary["last_http_request"] = {
                "method": last.request_method,
                "url": last.request_url,
                "headers": last.request_headers,
                "body": last.request_body,
            }
            evidence_summary["last_http_response"] = {
                "status": last.response_status,
                "headers": last.response_headers,
                "body": last.response_body,
                "latency_ms": last.latency_ms,
            }

        prompt = f"Analyze this test execution failure:\n\n{json.dumps(evidence_summary, indent=2)}"

        try:
            raw_response = await self.provider.complete(prompt, system_prompt=SYSTEM_PROMPT)
            # Clean markdown code blocks if LLM included them
            clean_json = raw_response.strip()
            if clean_json.startswith("```"):
                clean_json = re.sub(r"^```(?:json)?\n?", "", clean_json)
                clean_json = re.sub(r"\n?```$", "", clean_json)

            data = json.loads(clean_json)

            hypotheses = [
                Hypothesis(
                    hypothesis=h.get("hypothesis", ""),
                    confidence=float(h.get("confidence", 0.7)),
                    explanation=h.get("explanation", ""),
                )
                for h in data.get("hypotheses", [])
            ]

            if not hypotheses and baseline.hypotheses:
                hypotheses = baseline.hypotheses

            return FailureAnalysis(
                observed_facts=data.get("observed_facts", baseline.observed_facts),
                hypotheses=hypotheses,
                suggested_fix=data.get("suggested_fix", baseline.suggested_fix),
                confidence_score=float(data.get("confidence_score", baseline.confidence_score)),
                raw_llm_response=raw_response,
            )

        except Exception as e:
            logger.warning(f"AI Failure analysis fallback to deterministic engine: {e}")
            return baseline
