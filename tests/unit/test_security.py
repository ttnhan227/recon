import pytest
from recon.common.exceptions import SSRFSecurityError
from recon.common.security import is_safe_target_url, redact_headers, redact_sensitive_data, validate_target_url


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
