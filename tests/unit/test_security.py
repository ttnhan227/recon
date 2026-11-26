import pytest

from recon.common.exceptions import SSRFSecurityError
from recon.common.security import (
    is_safe_target_url,
    redact_headers,
    redact_sensitive_data,
    validate_target_url,
)


def test_ssrf_blocking_cloud_metadata():
    safe, reason = is_safe_target_url("http://169.254.169.254/latest/meta-data")
    assert safe is False
    assert "blocked" in reason.lower()

    safe_gcp, _ = is_safe_target_url("http://metadata.google.internal/computeMetadata/v1/")
    assert safe_gcp is False


def test_ssrf_blocking_invalid_schemes():
    safe, reason = is_safe_target_url("file:///etc/passwd")
    assert safe is False
    assert "scheme" in reason.lower()

    safe_ftp, _ = is_safe_target_url("ftp://server.local/data")
    assert safe_ftp is False


def test_validate_target_url_exception():
    with pytest.raises(SSRFSecurityError):
        validate_target_url("http://169.254.169.254/secret")


def test_secret_redaction_in_headers():
    headers = {
        "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secretpayload",
        "Cookie": "session_id=abcdef123456",
        "X-Api-Key": "my-api-secret-key-12345",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    redacted = redact_headers(headers)
    assert redacted["Authorization"] == "***REDACTED***"
    assert redacted["Cookie"] == "***REDACTED***"
    assert redacted["X-Api-Key"] == "***REDACTED***"
    assert redacted["Content-Type"] == "application/json"
    assert redacted["Accept"] == "application/json"


def test_secret_redaction_in_payloads():
    payload = {
        "user": "alice",
        "password": "myPlainPassword123!",
        "api_key": "sec_88219192",
        "token": "tok_abcdef",
        "details": {
            "credit_card": "4111222233334444",
            "notes": "Bearer my_embedded_token_val_123 in text",
        },
    }
    redacted = redact_sensitive_data(payload)
    assert redacted["password"] == "***REDACTED***"
    assert redacted["api_key"] == "***REDACTED***"
    assert redacted["token"] == "***REDACTED***"
    assert redacted["details"]["credit_card"] == "***REDACTED***"
    assert "***REDACTED***" in redacted["details"]["notes"]
    assert redacted["user"] == "alice"


def test_ssrf_dns_resolution_blocks_link_local_and_private(monkeypatch):
    import socket

    from recon.common.security import validate_redirect_response

    def fake_getaddrinfo_link_local(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo_link_local)
    safe, reason = is_safe_target_url("http://rebind.attacker.example/latest/meta-data")
    assert safe is False
    assert "blocked" in reason.lower()

    def fake_getaddrinfo_private(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo_private)
    safe_priv, _ = is_safe_target_url("http://internal.attacker.example/", allow_localhost=False)
    assert safe_priv is False

    import asyncio

    import httpx

    req = httpx.Request("GET", "https://public.example/start")
    resp = httpx.Response(302, headers={"location": "http://169.254.169.254/latest"}, request=req)
    with pytest.raises(SSRFSecurityError):
        asyncio.run(validate_redirect_response(resp))


@pytest.mark.asyncio
async def test_master_agent_enforces_validate_target_url():
    from recon.agent.master_agent import ReconMasterAgent

    agent = ReconMasterAgent()
    with pytest.raises(SSRFSecurityError):
        await agent._execute_browser("http://169.254.169.254/latest", "inspect")
    with pytest.raises(SSRFSecurityError):
        await agent._execute_scan("http://169.254.169.254/latest")
