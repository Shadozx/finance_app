from typing import Any

from fastapi import FastAPI


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
                    continue
                content = responses.get("422", {}).get("content", {})
                if "application/problem+json" in content:
                    # FastAPI also adds the route's media type for additional response models.
                    content.pop("application/json", None)
        return schema

    app.openapi = problem_openapi  # type: ignore[method-assign]
