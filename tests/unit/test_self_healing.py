from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from recon.common.models import (
    FailureCategory,
    FailureEvidence,
    HTTPTrace,
    TestCategory,
    TestResult,
    TestStatus,
    TestType,
)
from recon.healing.applier import PatchApplier
from recon.healing.engine import SelfHealingEngine
from recon.healing.locator import CodeLocator, LocatedContext
from recon.healing.patcher import AIPatchGenerator, ProposedPatch
from recon.llm.provider import MockProvider


def test_code_locator_finds_fastapi_route():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        router_dir = tmp_path / "app" / "controllers"
        router_dir.mkdir(parents=True)

        auth_file = router_dir / "auth.py"
        auth_file.write_text(
            """from fastapi import APIRouter

router = APIRouter(prefix="/auth")

@router.post("/login")
async def login(payload: dict):
    if not payload.get("password"):
        raise ValueError("Password required")
    return {"token": "123"}
""",
            encoding="utf-8",
        )

        locator = CodeLocator(repo_dir=tmp_path)
        contexts = locator.locate_endpoint("POST", "/api/v1/auth/login")

        assert len(contexts) > 0
        ctx = contexts[0]
        assert ctx.file_path == auth_file
        assert "login" in ctx.function_name
        assert ctx.line_number > 0


def test_patch_applier_and_rollback():
    with tempfile.TemporaryDirectory() as tmpdir:
        target_file = Path(tmpdir) / "service.py"
        target_file.write_text("def hello():\n    return 'old'\n", encoding="utf-8")

        patch = ProposedPatch(
            test_id="API-001",
            file_path=target_file,
            relative_path="service.py",
            explanation="Updated hello return value",
            diff="--- a/service.py\n+++ b/service.py\n@@ -1,2 +1,2 @@\n def hello():\n-    return 'old'\n+    return 'new'\n",
            original_content="def hello():\n    return 'old'\n",
            modified_content="def hello():\n    return 'new'\n",
        )

        backup = PatchApplier.apply_patch(patch)
        assert backup is not None
        assert backup.exists()
        assert target_file.read_text(encoding="utf-8") == "def hello():\n    return 'new'\n"

        # Rollback
        success = PatchApplier.rollback(backup, target_file_path=target_file)
        assert success is True
        assert target_file.read_text(encoding="utf-8") == "def hello():\n    return 'old'\n"
        assert not backup.exists()


@pytest.mark.asyncio
async def test_ai_patch_generator_with_mock():
    mock_json = """{
      "explanation": "Added check for empty string password",
      "modified_full_content": "def login(pwd):\\n    if not pwd:\\n        return 422\\n    return 200\\n"
    }"""
    mock_provider = MockProvider(mock_responses=[mock_json])
    generator = AIPatchGenerator(provider=mock_provider)

    context = LocatedContext(
        file_path=Path("dummy.py"),
        relative_path="dummy.py",
        line_number=1,
        matched_pattern="login",
        full_content="def login(pwd):\n    return 200\n",
        snippet="def login(pwd):\n    return 200\n",
    )

    result = TestResult(
        test_id="API-015",
        test_name="[POST /api/v1/auth/login] Boundary - empty password",
        category=TestCategory.BOUNDARY,
        test_type=TestType.API,
        status=TestStatus.FAILED,
        failure_evidence=FailureEvidence(
            failure_category=FailureCategory.APPLICATION_ERROR,
            message="Server returned 500 instead of 422",
            http_traces=[
                HTTPTrace(
                    request_method="POST",
                    request_url="http://localhost:8000/api/v1/auth/login",
                    request_headers={},
                    request_body={"password": ""},
                    response_status=500,
                    response_headers={},
                    response_body={"detail": "Internal Server Error"},
                )
            ],
        ),
    )

    patch = await generator.generate_patch(result, context)
    assert patch is not None
    assert patch.test_id == "API-015"
    assert "empty string password" in patch.explanation
    assert "+    if not pwd:" in patch.diff


def test_extract_method_and_path():
    mp = SelfHealingEngine.extract_method_and_path("[POST /api/v1/auth/login] Boundary - empty string for 'password'")
    assert mp == ("POST", "/api/v1/auth/login")

    mp2 = SelfHealingEngine.extract_method_and_path("[GET /api/v1/documents/{document_id}] Happy Path")
    assert mp2 == ("GET", "/api/v1/documents/{document_id}")

    mp3 = SelfHealingEngine.extract_method_and_path("Invalid Test Format")
    assert mp3 is None
