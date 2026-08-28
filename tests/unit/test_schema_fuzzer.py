import pytest
from recon.planning.schema_fuzzer import SchemaFuzzer

SCHEMA = {
    "type": "object",
    "required": ["email", "age"],
    "properties": {
        "name": {"type": "string"},
        "email": {"type": "string", "format": "email"},
        "age": {"type": "integer", "minimum": 18},
        "is_active": {"type": "boolean"},
    },
}


def test_schema_fuzzer_valid_payload():
    payload = SchemaFuzzer.generate_valid_payload(SCHEMA)
    assert "@" in payload["email"]
    assert isinstance(payload["age"], int)
    assert payload["age"] >= 18
    assert isinstance(payload["is_active"], bool)


def test_schema_fuzzer_validation_cases():
    val_cases = SchemaFuzzer.generate_validation_cases(SCHEMA)
    # 2 required fields -> 2 cases
    assert len(val_cases) == 2
    desc1, body1 = val_cases[0]
    assert "email" in desc1
    assert "email" not in body1


def test_schema_fuzzer_boundary_cases():
    boundary_cases = SchemaFuzzer.generate_boundary_payloads(SCHEMA)
    descriptions = [d for d, _ in boundary_cases]
    assert any("empty string" in d for d in descriptions)
    assert any("zero value" in d for d in descriptions)


def test_schema_fuzzer_negative_cases():
    neg_cases = SchemaFuzzer.generate_negative_cases(SCHEMA)
    descriptions = [d for d, _ in neg_cases]
    assert any("string instead of numeric" in d for d in descriptions)
