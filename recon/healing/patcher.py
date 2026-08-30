from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from recon.common.logging import logger
from recon.common.models import TestCase, TestResult
from recon.healing.locator import LocatedContext
from recon.llm.provider import LLMProvider, get_llm_provider

SYSTEM_PROMPT = """You are an expert Software Engineer and Autonomous Debugging Agent.
Your job is to fix a bug in the provided source code that caused an automated test failure (such as an unhandled 500 Internal Server Error or missing input validation).

Rules for fixing:
1. Make MINIMAL, targeted changes that directly resolve the defect.
2. Return proper HTTP client error status codes (e.g. 400 Bad Request or 422 Unprocessable Entity with clear error details) rather than crashing or throwing unhandled 500 exceptions.
3. Preserve all existing business logic, imports, comments, and style.
4. Output your response as a valid JSON object with the following schema:
{
  "explanation": "Clear 1-2 sentence explanation of what changed and why.",
  "modified_full_content": "The COMPLETE modified file content with the fix applied."
}

Do NOT wrap the JSON in conversational text. Only return the JSON object.
"""


@dataclass
class ProposedPatch:
    test_id: str
    file_path: Path
    relative_path: str
    explanation: str
    diff: str
    original_content: str
    modified_content: str


class AIPatchGenerator:
    """Uses LLM reasoning to generate source code patches for test failures."""

    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider or get_llm_provider()

    async def generate_patch(
        self,
        result: TestResult,
        context: LocatedContext,
        test: TestCase | None = None,
    ) -> ProposedPatch | None:
        """Generates a proposed patch diff for the located file context."""
        ev = result.failure_evidence
        fail_msg = ev.message if ev else (result.step_results[0].error_message if result.step_results else "Unknown error")
        http_trace = ev.http_traces[0] if (ev and ev.http_traces) else None

        evidence_payload = {
            "test_id": result.test_id,
            "test_name": result.test_name,
            "failure_message": fail_msg,
            "failed_endpoint": result.test_name,
            "http_status_returned": http_trace.response_status if http_trace else None,
            "request_payload": http_trace.request_body if http_trace else None,
            "response_body": http_trace.response_body if http_trace else None,
            "target_file": context.relative_path,
        }

        user_prompt = f"""### Test Failure Evidence:
{json.dumps(evidence_payload, indent=2)}

### Source File: `{context.relative_path}`
```
{context.full_content}
```

Please fix the defect so the endpoint handles this edge-case gracefully without crashing.
"""

        try:
            raw_response = await self.provider.complete(user_prompt, system_prompt=SYSTEM_PROMPT)

            # Clean JSON formatting
            clean_json = raw_response.strip()
            if "```" in clean_json:
                match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_json)
                if match:
                    clean_json = match.group(1)

            json_match = re.search(r"\{[\s\S]*\}", clean_json)
            if json_match:
                clean_json = json_match.group(0)

            data = json.loads(clean_json)
            explanation = data.get("explanation", "Automated bugfix applied.")
            modified_content = data.get("modified_full_content", "")

            if not modified_content or modified_content.strip() == context.full_content.strip():
                logger.warning(f"Patch generator produced empty or identical content for {context.relative_path}")
                return None

            # Generate unified diff
            orig_lines = context.full_content.splitlines(keepends=True)
            mod_lines = modified_content.splitlines(keepends=True)
            diff_lines = list(
                difflib.unified_diff(
                    orig_lines,
                    mod_lines,
                    fromfile=f"a/{context.relative_path}",
                    tofile=f"b/{context.relative_path}",
                )
            )
            unified_diff = "".join(diff_lines)

            return ProposedPatch(
                test_id=result.test_id,
                file_path=context.file_path,
                relative_path=context.relative_path,
                explanation=explanation,
                diff=unified_diff,
                original_content=context.full_content,
                modified_content=modified_content,
            )

        except Exception as e:
            logger.error(f"Error generating patch for {result.test_id}: {e}")
            return None
