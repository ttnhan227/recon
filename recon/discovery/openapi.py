from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import yaml

from recon.common.exceptions import DiscoveryError
from recon.common.logging import logger
from recon.common.security import validate_target_url
from recon.discovery.models import (
    DiscoveredApplication,
    DiscoveredEndpoint,
    DiscoveredParameter,
)


class OpenAPIParser:
    """Parses OpenAPI 3.x and Swagger 2.0 specifications from URLs, local files, or raw dicts."""

    def __init__(self, raw_spec: dict[str, Any], source_url: str = ""):
        self.spec = raw_spec
        self.source_url = source_url
        self.components = self.spec.get("components", {})
        self.definitions = self.spec.get("definitions", {})  # Swagger 2.0

    @classmethod
    async def from_url(cls, spec_url: str) -> OpenAPIParser:
        """Fetches and parses spec from a remote HTTP URL."""
        validate_target_url(spec_url)
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(spec_url)
                resp.raise_for_status()
                content = resp.text

            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                data = yaml.safe_load(content)

            if not isinstance(data, dict):
                raise DiscoveryError(
                    f"OpenAPI spec from {spec_url} is not a valid JSON/YAML object."
                )

            return cls(data, source_url=spec_url)
        except Exception as e:
            logger.error(f"Failed to fetch OpenAPI spec from {spec_url}: {e}")
            raise DiscoveryError(
                f"Could not load OpenAPI specification from '{spec_url}': {e}"
            ) from e

    @classmethod
    def from_file(cls, file_path: str | Path) -> OpenAPIParser:
        """Loads and parses spec from a local file."""
        p = Path(file_path)
        if not p.exists():
            raise DiscoveryError(f"OpenAPI spec file not found: {file_path}")

        try:
            content = p.read_text(encoding="utf-8")
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                data = yaml.safe_load(content)

            if not isinstance(data, dict):
                raise DiscoveryError(
                    f"OpenAPI spec in {file_path} is not a valid JSON/YAML dictionary."
                )

            return cls(data, source_url=str(p))
        except Exception as e:
            raise DiscoveryError(f"Error reading OpenAPI file {file_path}: {e}") from e

    def resolve_ref(self, ref: str) -> dict[str, Any]:
        """Resolves a local JSON schema reference like #/components/schemas/User or #/definitions/User."""
        if not ref.startswith("#/"):
            return {}

        parts = ref.lstrip("#/").split("/")
        curr: Any = self.spec
        for part in parts:
            if isinstance(curr, dict) and part in curr:
                curr = curr[part]
            else:
                return {}

        if isinstance(curr, dict):
            # Recursively resolve nested refs if any
            if "$ref" in curr:
                return self.resolve_ref(curr["$ref"])
            # Resolve properties
            resolved = dict(curr)
            if "properties" in resolved and isinstance(resolved["properties"], dict):
                resolved_props = {}
                for p_name, p_val in resolved["properties"].items():
                    if isinstance(p_val, dict) and "$ref" in p_val:
                        resolved_props[p_name] = self.resolve_ref(p_val["$ref"])
                    else:
                        resolved_props[p_name] = p_val
                resolved["properties"] = resolved_props
            return resolved
        return {}

    def _resolve_schema(self, schema: dict[str, Any] | None) -> dict[str, Any] | None:
        """Deeply resolves $ref schemas inside a schema dictionary."""
        if not schema or not isinstance(schema, dict):
            return schema

        if "$ref" in schema:
            return self.resolve_ref(schema["$ref"])

        resolved = dict(schema)
        if "properties" in resolved and isinstance(resolved["properties"], dict):
            resolved["properties"] = {
                k: self._resolve_schema(v) for k, v in resolved["properties"].items()
            }

        if "items" in resolved and isinstance(resolved["items"], dict):
            resolved["items"] = self._resolve_schema(resolved["items"])

        if "allOf" in resolved and isinstance(resolved["allOf"], list):
            merged_props = {}
            required_fields = list(resolved.get("required", []))
            for sub in resolved["allOf"]:
                sub_res = self._resolve_schema(sub)
                if isinstance(sub_res, dict):
                    merged_props.update(sub_res.get("properties", {}))
                    required_fields.extend(sub_res.get("required", []))
            resolved["type"] = "object"
            resolved["properties"] = merged_props
            if required_fields:
                resolved["required"] = list(set(required_fields))

        return resolved

    def parse(self, base_url: str = "") -> DiscoveredApplication:
        """Extracts endpoints, parameters, schemas, and metadata from the specification."""
        info = self.spec.get("info", {})
        title = info.get("title", "Target API")
        version = info.get("version", "1.0.0")

        # Determine target base URL if not explicitly provided
        target_url = base_url
        if not target_url:
            servers = self.spec.get("servers", [])
            if servers and isinstance(servers, list) and len(servers) > 0:
                target_url = servers[0].get("url", "")
            elif "host" in self.spec:  # Swagger 2.0
                schemes = self.spec.get("schemes", ["http"])
                scheme = schemes[0] if schemes else "http"
                base_path = self.spec.get("basePath", "")
                target_url = f"{scheme}://{self.spec['host']}{base_path}"
            elif self.source_url.startswith("http"):
                target_url = self.source_url.rsplit("/", 1)[0]
            else:
                target_url = "http://localhost:8000"

        endpoints: list[DiscoveredEndpoint] = []
        paths = self.spec.get("paths", {})

        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            # Shared path parameters
            common_params = path_item.get("parameters", [])

            for method in ["get", "post", "put", "delete", "patch", "options", "head"]:
                if method not in path_item:
                    continue

                operation = path_item[method]
                if not isinstance(operation, dict):
                    continue

                summary = operation.get("summary")
                description = operation.get("description")
                tags = operation.get("tags", [])

                # Merge parameters
                all_params_raw = list(common_params) + operation.get("parameters", [])
                discovered_params: list[DiscoveredParameter] = []

                for param in all_params_raw:
                    if not isinstance(param, dict):
                        continue

                    if "$ref" in param:
                        param = self.resolve_ref(param["$ref"])

                    p_name = param.get("name", "")
                    p_in = param.get("in", "query")
                    p_req = param.get("required", False) or (p_in == "path")
                    p_schema = self._resolve_schema(param.get("schema", {})) or {}
                    p_type = p_schema.get("type", param.get("type", "string"))

                    discovered_params.append(
                        DiscoveredParameter(
                            name=p_name,
                            in_type=p_in,
                            required=p_req,
                            data_type=p_type,
                            schema_definition=p_schema,
                            default=param.get("default", p_schema.get("default")),
                            description=param.get("description"),
                        )
                    )

                # Extract request body (OpenAPI 3 vs Swagger 2)
                request_body_schema: dict[str, Any] | None = None
                if "requestBody" in operation:
                    req_body = operation["requestBody"]
                    if isinstance(req_body, dict):
                        content_dict = req_body.get("content", {})
                        # Prefer application/json
                        if "application/json" in content_dict:
                            raw_schema = content_dict["application/json"].get("schema")
                            request_body_schema = self._resolve_schema(raw_schema)
                        elif content_dict:
                            first_ct = next(iter(content_dict.values()))
                            request_body_schema = self._resolve_schema(first_ct.get("schema"))
                else:
                    # Swagger 2 body parameter
                    for param in all_params_raw:
                        if isinstance(param, dict) and param.get("in") == "body":
                            request_body_schema = self._resolve_schema(param.get("schema"))
                            break

                # Extract response schemas
                response_schemas: dict[str, dict[str, Any]] = {}
                responses = operation.get("responses", {})
                if isinstance(responses, dict):
                    for status_code, resp_def in responses.items():
                        if not isinstance(resp_def, dict):
                            continue
                        if "$ref" in resp_def:
                            resp_def = self.resolve_ref(resp_def["$ref"])

                        content = resp_def.get("content", {})
                        if "application/json" in content:
                            r_schema = content["application/json"].get("schema")
                            if r_schema:
                                response_schemas[str(status_code)] = (
                                    self._resolve_schema(r_schema) or {}
                                )
                        elif "schema" in resp_def:  # Swagger 2
                            response_schemas[str(status_code)] = (
                                self._resolve_schema(resp_def["schema"]) or {}
                            )

                # Security requirements
                security_schemes = operation.get("security", self.spec.get("security", []))

                endpoints.append(
                    DiscoveredEndpoint(
                        path=path,
                        method=method.upper(),
                        summary=summary,
                        description=description,
                        parameters=discovered_params,
                        request_body_schema=request_body_schema,
                        response_schemas=response_schemas,
                        security_schemes=security_schemes
                        if isinstance(security_schemes, list)
                        else [],
                        tags=tags if isinstance(tags, list) else [],
                    )
                )

        return DiscoveredApplication(
            target_url=target_url.rstrip("/"),
            title=title,
            version=version,
            spec_source=self.source_url or "openapi_dict",
            endpoints=endpoints,
            metadata={
                "total_endpoints": len(endpoints),
                "openapi_version": self.spec.get("openapi", self.spec.get("swagger", "3.0")),
            },
        )
