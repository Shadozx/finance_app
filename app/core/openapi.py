from typing import Any

from fastapi import FastAPI

from app.schemas.error import ErrorResponse


def problem_response(description: str) -> dict[str, Any]:
    return {
        # The model registers ErrorResponse in components/schemas, so the $ref resolves
        "model": ErrorResponse,
        "description": description,
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}
        },
    }


def configure_openapi(app: FastAPI) -> None:
    def problem_openapi() -> dict[str, Any]:
        schema = FastAPI.openapi(app)
        for path_item in schema["paths"].values():
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue
                responses = operation.get("responses", {})
                # FastAPI adds its default 422 only for parameters or a request body.
                if not (operation.get("parameters") or operation.get("requestBody")):
                    responses.pop("422", None)
                # Any operation can fail, so "default" stays everywhere, /health included.
                for status_key in ("422", "default"):
                    content = responses.get(status_key, {}).get("content", {})
                    if "application/problem+json" in content:
                        # FastAPI also adds the route's media type for additional response models.
                        content.pop("application/json", None)
        return schema

    app.openapi = problem_openapi  # type: ignore[method-assign]
