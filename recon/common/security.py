from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import urlparse

from recon.common.config import settings
from recon.common.exceptions import SSRFSecurityError


def is_safe_target_url(url: str, allow_localhost: bool = True) -> tuple[bool, str]:
    """
    Validates a target URL against SSRF rules, IP blacklists, and cloud metadata IPs.
    Returns (is_safe, reason).
    """
    if not url:
        return False, "URL is empty"

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, f"Unsupported scheme: '{parsed.scheme}'. Only http and https are allowed."

    hostname = parsed.hostname
    if not hostname:
        return False, "Invalid URL: missing hostname"

    # Check blocked host list
    if hostname.lower() in [h.lower() for h in settings.blocked_hosts]:
        return (
            False,
            f"Target host '{hostname}' is in the blocked host list (cloud metadata/restricted).",
        )

    # Check allowed hosts if specified
    if settings.allowed_hosts and hostname.lower() not in [
        h.lower() for h in settings.allowed_hosts
    ]:
        return False, f"Target host '{hostname}' is not in the allowed hosts whitelist."

    # Fast path for localhost and standard test hostnames
    if hostname.lower() in ("localhost", "testserver", "test", "127.0.0.1", "::1"):
        if not allow_localhost:
            return False, f"Host '{hostname}' is loopback/test host, which is disallowed."
        return True, "Safe test/local host"

    # Check IP addresses
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_loopback:
            if not allow_localhost:
                return False, f"Loopback address '{hostname}' is not allowed in this configuration."
            return True, "Safe localhost IP"

        if ip.is_private:
            # Allow private IPs in local testing mode if localhost is allowed or explicitly permitted
            if not allow_localhost:
                return False, f"Private network address '{hostname}' is blocked."
            return True, "Private network IP allowed"

        if ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False, f"Restricted IP address '{hostname}' is blocked."

    except ValueError:
        # Not a direct IP, hostname is a domain name.
        pass

    return True, "Target URL is valid and safe."


def validate_target_url(url: str, allow_localhost: bool = True) -> str:
    """Validates URL and raises SSRFSecurityError if unsafe."""
    is_safe, reason = is_safe_target_url(url, allow_localhost=allow_localhost)
    if not is_safe:
        raise SSRFSecurityError(f"Security validation failed for URL '{url}': {reason}")
    return url


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Redacts sensitive header values such as Authorization, Cookie, API tokens."""
    redacted = {}
    sensitive_keys = {k.lower() for k in settings.redact_sensitive_headers}

    for key, value in headers.items():
        if key.lower() in sensitive_keys:
            redacted[key] = "***REDACTED***"
        else:
            redacted[key] = value
    return redacted


def redact_sensitive_data(data: Any) -> Any:
    """Recursively redacts sensitive keys from dicts, lists, or string payloads."""
    sensitive_keys = {k.lower() for k in settings.redact_sensitive_keys}

    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if str(k).lower() in sensitive_keys:
                result[k] = "***REDACTED***"
            else:
                result[k] = redact_sensitive_data(v)
        return result

    if isinstance(data, list):
        return [redact_sensitive_data(item) for item in data]

    if isinstance(data, str):
        # Redact Bearer tokens in text
        redacted_str = re.sub(
            r"(Bearer\s+)[A-Za-z0-9\-\._~\+\/]+=*",
            r"\1***REDACTED***",
            data,
            flags=re.IGNORECASE,
        )
        # Redact basic auth tokens
        redacted_str = re.sub(
            r"(Basic\s+)[A-Za-z0-9\+\/]+=*",
            r"\1***REDACTED***",
            redacted_str,
            flags=re.IGNORECASE,
        )
        return redacted_str

    return data
