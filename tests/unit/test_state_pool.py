from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from recon.common.models import (
    AssertionType,
    StepAssertion,
    TestCase,
    TestCategory,
    TestStatus,
    TestStep,
)
from recon.orchestration.orchestrator import TestOrchestrator
from recon.orchestration.state_pool import StatePool
from recon.orchestration.worker_pool import WorkerPool


def test_substitute_payload_preserves_non_id_keys():
    """Verify keys like category, token, auto_renew, and valid_from are never overwritten."""
    pool = StatePool()
    pool.store_entity("accountId", "acc-111")
    pool.store_entity("accountId", "acc-222")
    pool.store_entity("customerId", "cust-999")

    payload = {
        "category": "electronics",
        "token": "reset-token-abc",
        "auto_renew": "enabled",
        "valid_from": "2026-01-01T00:00:00Z",
        "valid_to": "2026-12-31T23:59:59Z",
        "account_name": "Primary Checking",
        "customer_email": "alice@example.com",
        "nested": {
            "from_date": "2026-02-01",
            "to_email": "bob@example.com",
        },
        "items": [{"category": "books", "token": "item-tok"}],
    }

    result = pool.substitute_payload(payload)
    assert result == payload


def test_substitute_payload_replaces_explicit_id_keys():
    """Verify explicit ID patterns are substituted with harvested entities."""
    pool = StatePool()
    pool.store_entity("accountId", "acc-first")
    pool.store_entity("accountId", "acc-second")
    pool.store_entity("customerId", "cust-42")
    pool.store_entity("userId", "user-77")

    payload = {
        "source_account_id": "placeholder",
        "destination_account_id": "placeholder",
        "from_account_id": "placeholder",
        "to_account_id": "placeholder",
        "sourceAccountId": "placeholder",
        "destinationAccountId": "placeholder",
        "customer_id": "placeholder",
        "account_id": "placeholder",
        "user_id": "placeholder",
        "nested": {"targetAccountId": "placeholder"},
        "transfers": [{"fromAccountId": "placeholder", "toAccountId": "placeholder"}],
    }

    result = pool.substitute_payload(payload)
    assert result["source_account_id"] == "acc-second"
    assert result["destination_account_id"] == "acc-first"
    assert result["from_account_id"] == "acc-second"
    assert result["to_account_id"] == "acc-first"
    assert result["sourceAccountId"] == "acc-second"
    assert result["destinationAccountId"] == "acc-first"
    assert result["customer_id"] == "cust-42"
    assert result["account_id"] == "acc-second"
    assert result["user_id"] == "user-77"
    assert result["nested"]["targetAccountId"] == "acc-first"
    assert result["transfers"][0]["fromAccountId"] == "acc-second"
    assert result["transfers"][0]["toAccountId"] == "acc-first"


@pytest.mark.asyncio
async def test_api_runner_and_worker_pool_use_injected_state_pool():
    """Verify injected StatePool is isolated from the global singleton."""
    global_pool = StatePool.get_instance()
    global_pool.reset()
    global_pool.store_entity("accountId", "global-acc")

    local_pool = StatePool()
    local_pool.store_entity("accountId", "local-acc")

    seen_bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_bodies.append(json.loads(request.content.decode()))
        return httpx.Response(201, json={"accountId": "created-local-acc"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        worker_pool = WorkerPool(concurrency=1, api_client=client, state_pool=local_pool)
        test_case = TestCase(
            id="t-1",
            name="Create Transfer",
            category=TestCategory.HAPPY_PATH,
            target="https://example.com/transfers",
            method="POST",
            steps=[
                TestStep(
                    name="step-1",
                    endpoint="https://example.com/transfers",
                    method="POST",
                    body={"account_id": "placeholder", "category": "wire"},
                    assertions=[
                        StepAssertion(assertion_type=AssertionType.STATUS_CODE, expected=201)
                    ],
                )
            ],
        )
        results = await worker_pool.execute_suite([test_case])

    assert len(results) == 1
    assert results[0].status == TestStatus.PASSED
    assert seen_bodies[0] == {"account_id": "local-acc", "category": "wire"}
    assert local_pool.get_latest("accountId") == "created-local-acc"
    assert global_pool.get_latest("accountId") == "global-acc"


@pytest.mark.asyncio
async def test_concurrent_orchestrator_runs_isolate_state_pools(tmp_path: Path):
    """Verify concurrent TestOrchestrator runs do not leak StatePool state across runs."""

    def make_transport(run_tag: str) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST" and request.url.path == "/accounts":
                return httpx.Response(201, json={"accountId": f"{run_tag}-acc-1"})
            if request.method == "POST" and request.url.path == "/transfers":
                body = json.loads(request.content.decode())
                # Slow down slightly to interleave with the other concurrent run
                if body.get("account_id") != f"{run_tag}-acc-1":
                    return httpx.Response(
                        400,
                        json={"error": f"cross-run leak: {body.get('account_id')}"},
                    )
                if body.get("category") != "payroll" or body.get("valid_from") != "2026-01-01":
                    return httpx.Response(400, json={"error": "non-id fields corrupted"})
                return httpx.Response(200, json={"status": "ok"})
            return httpx.Response(404)

        return httpx.MockTransport(handler)

    def make_tests(tag: str) -> list[TestCase]:
        create_test = TestCase(
            id=f"{tag}-create",
            name=f"Create account {tag}",
            category=TestCategory.HAPPY_PATH,
            target="https://example.com/accounts",
            method="POST",
            steps=[
                TestStep(
                    name="create",
                    endpoint="https://example.com/accounts",
                    method="POST",
                    body={"name": tag},
                    assertions=[
                        StepAssertion(assertion_type=AssertionType.STATUS_CODE, expected=201)
                    ],
                )
            ],
        )
        transfer_test = TestCase(
            id=f"{tag}-transfer",
            name=f"Transfer {tag}",
            category=TestCategory.HAPPY_PATH,
            target="https://example.com/transfers/{accountId}",
            method="POST",
            steps=[
                TestStep(
                    name="transfer",
                    endpoint="https://example.com/transfers",
                    method="POST",
                    body={
                        "account_id": "placeholder",
                        "category": "payroll",
                        "valid_from": "2026-01-01",
                    },
                    assertions=[
                        StepAssertion(assertion_type=AssertionType.STATUS_CODE, expected=200)
                    ],
                )
            ],
        )
        return [create_test, transfer_test]

    async def run_one(tag: str):
        async with httpx.AsyncClient(transport=make_transport(tag)) as client:
            orch = TestOrchestrator(
                concurrency=2,
                output_dir=tmp_path / f"reports-{tag}",
                enable_ai=False,
                db_url=f"sqlite+aiosqlite:///{(tmp_path / f'{tag}.db').as_posix()}",
                external_api_client=client,
            )
            return await orch.run_pipeline(
                target_url="https://example.com",
                custom_tests=make_tests(tag),
            )

    (summary_a, _), (summary_b, _) = await asyncio.gather(run_one("alpha"), run_one("beta"))

    assert summary_a.total == 2
    assert summary_a.passed == 2
    assert summary_a.failed == 0
    assert summary_b.total == 2
    assert summary_b.passed == 2
    assert summary_b.failed == 0
