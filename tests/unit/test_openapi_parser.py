import pytest
from recon.discovery.openapi import OpenAPIParser

SAMPLE_OPENAPI_SPEC = {
    "openapi": "3.0.1",
    "info": {"title": "Test Store API", "version": "1.0.0"},
    "paths": {
        "/api/users": {
            "post": {
                "summary": "Create user",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/UserCreate"}
                        }
                    }
                },
                "responses": {
                    "201": {
                        "description": "User created",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/UserResponse"}
                            }
                        },
                    },
                    "422": {"description": "Validation Error"},
                },
            }
        },
        "/api/users/{user_id}": {
            "get": {
                "summary": "Get user by ID",
                "parameters": [
                    {
                        "name": "user_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"},
                    }
                ],
                "responses": {
                    "200": {"description": "User profile"},
                    "404": {"description": "Not found"},
                },
            }
        },
    },
    "components": {
        "schemas": {
            "UserCreate": {
                "type": "object",
                "required": ["email", "password"],
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string", "format": "email"},
                    "password": {"type": "string"},
                },
            },
            "UserResponse": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "email": {"type": "string"},
                },
            },
        }
    },
}


def test_openapi_parser_ref_resolution_and_extraction():
    parser = OpenAPIParser(SAMPLE_OPENAPI_SPEC, source_url="http://localhost:8000/openapi.json")
    app = parser.parse(base_url="http://localhost:8000")

    assert app.title == "Test Store API"
    assert len(app.endpoints) == 2

    post_ep = next(e for e in app.endpoints if e.method == "POST")
    assert post_ep.path == "/api/users"
    assert post_ep.request_body_schema is not None
    assert "email" in post_ep.request_body_schema["properties"]
    assert post_ep.request_body_schema["required"] == ["email", "password"]
    assert "201" in post_ep.response_schemas

    get_ep = next(e for e in app.endpoints if e.method == "GET")
    assert get_ep.path == "/api/users/{user_id}"
    assert len(get_ep.parameters) == 1
    assert get_ep.parameters[0].name == "user_id"
    assert get_ep.parameters[0].in_type == "path"
