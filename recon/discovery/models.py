from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class DiscoveredParameter(BaseModel):
    name: str
    in_type: str = "query"  # query, path, header, cookie
    required: bool = False
    data_type: str = "string"
    schema_definition: dict[str, Any] = Field(default_factory=dict)
    default: Any = None
    description: str | None = None


class DiscoveredEndpoint(BaseModel):
    path: str
    method: str  # GET, POST, PUT, DELETE, PATCH
    summary: str | None = None
    description: str | None = None
    parameters: list[DiscoveredParameter] = Field(default_factory=list)
    request_body_schema: dict[str, Any] | None = None
    response_schemas: dict[str, dict[str, Any]] = Field(default_factory=dict)  # "200" -> schema
    security_schemes: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class DiscoveredFormField(BaseModel):
    name: str
    field_type: str = "text"  # text, email, password, number, checkbox, select, hidden
    required: bool = False
    placeholder: str | None = None
    default_value: str | None = None
    options: list[str] = Field(default_factory=list)  # for select dropdowns
    selector: str | None = None


class DiscoveredForm(BaseModel):
    action: str | None = None
    method: str = "POST"
    selector: str | None = None
    fields: list[DiscoveredFormField] = Field(default_factory=list)
    submit_selector: str | None = None
    location_url: str
    is_visible: bool = True


class DiscoveredButton(BaseModel):
    text: str
    selector: str
    button_type: str = "button"
    is_clickable: bool = True
    is_visible: bool = True


class DiscoveredPage(BaseModel):
    url: str
    title: str | None = None
    status_code: int = 200
    forms: list[DiscoveredForm] = Field(default_factory=list)
    buttons: list[DiscoveredButton] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    inputs: list[DiscoveredFormField] = Field(default_factory=list)
    console_errors: list[str] = Field(default_factory=list)
    network_errors: list[str] = Field(default_factory=list)


class DiscoveredApplication(BaseModel):
    target_url: str
    title: str = "Discovered Application"
    version: str = "1.0.0"
    spec_source: str | None = None  # openapi_url, openapi_file, web_crawler
    endpoints: list[DiscoveredEndpoint] = Field(default_factory=list)
    pages: list[DiscoveredPage] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
