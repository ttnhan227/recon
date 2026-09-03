from __future__ import annotations

from typing import Any
import uuid


class SchemaFuzzer:
    """Generates valid, boundary, and negative payloads from JSON schemas with strict constraint adherence."""

    @staticmethod
    def generate_valid_value(prop_schema: dict[str, Any], prop_name: str = "") -> Any:
        if not prop_schema or not isinstance(prop_schema, dict):
            return "test_val"

        p_type = prop_schema.get("type", "string")
        p_format = prop_schema.get("format")
        p_enum = prop_schema.get("enum")
        p_default = prop_schema.get("default")

        if p_default is not None:
            return p_default

        # 1. Strict Enum Adherence
        if p_enum and isinstance(p_enum, list) and len(p_enum) > 0:
            return p_enum[0]

        # 2. String Type Fuzzing
        if p_type == "string":
            prop_lower = prop_name.lower()
            if p_format == "email" or "email" in prop_lower:
                return f"qa.recon.{uuid.uuid4().hex[:6]}@example.com"
            if (
                p_format == "uuid"
                or "uuid" in prop_lower
                or prop_lower.endswith("_id")
                or prop_lower == "id"
                or prop_lower.endswith("id")
            ):
                return str(uuid.uuid4())
            if p_format == "date":
                return "2026-08-28"
            if p_format == "date-time":
                return "2026-08-28T12:00:00Z"
            if p_format == "uri" or "url" in prop_lower:
                return "https://example.com/webhook"
            if p_format == "binary" or "file" in prop_lower:
                return "synthetic_qa_test_document.pdf"
            if "password" in prop_lower:
                return "Password123!"
            if "currency" in prop_lower:
                return "USD"
            if "company" in prop_lower or "tenant" in prop_lower:
                return f"Recon Enterprise {uuid.uuid4().hex[:4]}"
            if "name" in prop_lower or "fullname" in prop_lower or "display_name" in prop_lower:
                return "Recon QA Tester"
            if "sku" in prop_lower:
                return "ITEM-100"
            if "role" in prop_lower:
                return "TenantAdmin"
            if "type" in prop_lower or "accounttype" in prop_lower:
                return "Customer"
            if "reason" in prop_lower:
                return "Commercial reconciliation adjustment"
            if "notes" in prop_lower or "description" in prop_lower:
                return "Automated enterprise audit verification"

            # Check minLength
            min_len = prop_schema.get("minLength", 1)
            val = f"test_{prop_name or 'val'}"
            if len(val) < min_len:
                val = val + "_" * (min_len - len(val))
            return val

        # 3. Numeric Types with Min/Max
        elif p_type in ("integer", "number"):
            minimum = prop_schema.get("minimum")
            maximum = prop_schema.get("maximum")
            if minimum is not None:
                val = minimum
            elif maximum is not None:
                val = maximum
            else:
                val = 100
            return int(val) if p_type == "integer" else float(val)

        # 4. Boolean
        elif p_type == "boolean":
            return True

        # 5. Array
        elif p_type == "array":
            items_schema = prop_schema.get("items", {})
            return [SchemaFuzzer.generate_valid_value(items_schema, prop_name)]

        # 6. Object
        elif p_type == "object":
            return SchemaFuzzer.generate_valid_payload(prop_schema)

        return "test_val"

    @classmethod
    def generate_valid_payload(cls, schema: dict[str, Any] | None) -> dict[str, Any]:
        """Generates a valid object dictionary satisfying all schema constraints."""
        if not schema or not isinstance(schema, dict):
            return {}

        properties = schema.get("properties", {})
        payload = {}

        for prop_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict):
                continue
            payload[prop_name] = cls.generate_valid_value(prop_schema, prop_name)

        return payload

    @classmethod
    def generate_boundary_payloads(
        cls, schema: dict[str, Any] | None
    ) -> list[tuple[str, dict[str, Any]]]:
        """
        Generates boundary cases: empty strings, zero, oversized numbers, min/max edges.
        Returns list of (case_description, mutated_payload).
        """
        if not schema or not isinstance(schema, dict):
            return []

        base = cls.generate_valid_payload(schema)
        properties = schema.get("properties", {})
        cases = []

        for prop_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict):
                continue
            p_type = prop_schema.get("type", "string")

            if p_type == "string":
                # Boundary 1: Empty string
                p_copy = dict(base)
                p_copy[prop_name] = ""
                cases.append((f"empty string for '{prop_name}'", p_copy))

                # Boundary 2: 1000 char long string
                p_copy2 = dict(base)
                p_copy2[prop_name] = "A" * 1000
                cases.append((f"oversized 1000-char string for '{prop_name}'", p_copy2))

            elif p_type in ("integer", "number"):
                # Boundary: Zero
                p_copy = dict(base)
                p_copy[prop_name] = 0
                cases.append((f"zero value for '{prop_name}'", p_copy))

                # Boundary: Negative integer
                p_copy2 = dict(base)
                p_copy2[prop_name] = -1
                cases.append((f"negative value for '{prop_name}'", p_copy2))

                # Boundary: Large integer
                p_copy3 = dict(base)
                p_copy3[prop_name] = 99999999
                cases.append((f"large integer for '{prop_name}'", p_copy3))

        return cases

    @classmethod
    def generate_validation_cases(
        cls, schema: dict[str, Any] | None
    ) -> list[tuple[str, dict[str, Any]]]:
        """Generates payload variants where each required field is omitted."""
        if not schema or not isinstance(schema, dict):
            return []

        base = cls.generate_valid_payload(schema)
        required = schema.get("required", [])
        cases = []

        for req_field in required:
            p_copy = dict(base)
            if req_field in p_copy:
                del p_copy[req_field]
                cases.append((f"omitted required field '{req_field}'", p_copy))

        return cases

    @classmethod
    def generate_negative_cases(
        cls, schema: dict[str, Any] | None
    ) -> list[tuple[str, dict[str, Any]]]:
        """Generates payload variants with incorrect data types and enum violations."""
        if not schema or not isinstance(schema, dict):
            return []

        base = cls.generate_valid_payload(schema)
        properties = schema.get("properties", {})
        cases = []

        for prop_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict):
                continue
            p_type = prop_schema.get("type", "string")
            p_enum = prop_schema.get("enum")

            # 1. Enum Violation
            if p_enum and isinstance(p_enum, list) and len(p_enum) > 0:
                p_copy = dict(base)
                p_copy[prop_name] = "INVALID_ENUM_OPTION_XYZ"
                cases.append((f"invalid enum value for '{prop_name}'", p_copy))

            # 2. Type Violations
            if p_type in ("integer", "number"):
                p_copy = dict(base)
                p_copy[prop_name] = "invalid_string_not_number"
                cases.append((f"string instead of numeric type for '{prop_name}'", p_copy))

            elif p_type == "string":
                p_copy = dict(base)
                p_copy[prop_name] = {"nested_obj": True}
                cases.append((f"object instead of string for '{prop_name}'", p_copy))

            elif p_type == "boolean":
                p_copy = dict(base)
                p_copy[prop_name] = "not_a_boolean"
                cases.append((f"string instead of boolean for '{prop_name}'", p_copy))

        return cases
