import asyncio
import json
import re
from typing import Dict, Any, List, Optional
import httpx
import yaml

from ...logs.logger import logger
from ..v2.schemas import ToolV2, ToolImplementation, ImplementationType


def _to_json_schema_type(openapi_type: str, fmt: Optional[str] = None) -> str:
    mapping = {
        "string": "string",
        "integer": "integer",
        "number": "number",
        "boolean": "boolean",
        "array": "array",
        "object": "object",
    }
    return mapping.get(openapi_type, "string")


def _param_to_json_schema(param: Dict[str, Any]) -> Dict[str, Any]:
    schema: Dict[str, Any] = {"type": _to_json_schema_type(param.get("type", "string"))}
    if "description" in param:
        schema["description"] = param["description"]
    if "enum" in param:
        schema["enum"] = param["enum"]
    if "default" in param:
        schema["default"] = param["default"]
    if param.get("type") == "array" and "items" in param:
        schema["items"] = param["items"]
    if param.get("type") == "object" and "properties" in param:
        schema["properties"] = param["properties"]
    return schema


def _build_input_schema(
    parameters: List[Dict[str, Any]],
    request_body: Optional[Dict[str, Any]],
    components: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    schema: Dict[str, Any] = {"type": "object", "properties": {}, "required": []}

    for param in parameters:
        name = param.get("name")
        if not name:
            continue
        schema["properties"][name] = _param_to_json_schema(param)
        if param.get("required", False):
            schema["required"].append(name)

    if request_body:
        content = request_body.get("content", {})
        json_content = content.get("application/json") or content.get("application/json; charset=utf-8")
        if json_content and "schema" in json_content:
            body_schema = json_content["schema"]
            # Resolve $ref if needed
            if "$ref" in body_schema and components:
                ref_name = body_schema["$ref"].split("/")[-1]
                body_schema = components.get("schemas", {}).get(ref_name, body_schema)
            if "properties" in body_schema:
                for name, prop in body_schema["properties"].items():
                    schema["properties"][name] = prop
                if "required" in body_schema:
                    for req in body_schema["required"]:
                        if req not in schema["required"]:
                            schema["required"].append(req)
            elif "type" in body_schema:
                # Inline body object
                schema["properties"]["body"] = body_schema

    if not schema["required"]:
        del schema["required"]

    return schema


def _extract_auth_schemes(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    schemes = []
    security = spec.get("security", [])
    security_defs = spec.get("securityDefinitions", {})
    components_security = spec.get("components", {}).get("securitySchemes", {})
    all_schemes = {**security_defs, **components_security}

    for sec in security:
        for name, scopes in sec.items():
            definition = all_schemes.get(name, {})
            schemes.append({
                "name": name,
                "type": definition.get("type", definition.get("scheme", "unknown")),
                "in": definition.get("in"),
                "key_name": definition.get("name"),
                "scopes": scopes if isinstance(scopes, list) else [],
            })

    return schemes


def _sanitize_tool_id(raw: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "_", raw)
    return sanitized.lower()


async def ingest_openapi_spec(url: str, category: str = "api") -> List[ToolV2]:
    """
    Fetch an OpenAPI spec from a URL and convert each operation into a ToolV2.
    """
    logger.info(f"Ingesting OpenAPI spec from {url}")

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content = resp.text

    # Parse YAML or JSON
    try:
        if content.strip().startswith("{"):
            spec = json.loads(content)
        else:
            spec = yaml.safe_load(content)
    except Exception as e:
        raise ValueError(f"Failed to parse OpenAPI spec: {e}")

    if not isinstance(spec, dict):
        raise ValueError("Invalid OpenAPI spec: root must be an object")

    base_url = spec.get("servers", [{}])[0].get("url", "")
    if not base_url:
        base_url = spec.get("host", "")
        scheme = spec.get("schemes", ["https"])[0]
        if base_url:
            base_url = f"{scheme}://{base_url}"

    auth_schemes = _extract_auth_schemes(spec)
    components = spec.get("components") or spec.get("definitions")
    if components is None:
        components = {}

    tools: List[ToolV2] = []
    paths = spec.get("paths", {})

    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, operation in methods.items():
            if method in ("parameters", "summary", "description"):
                continue
            if not isinstance(operation, dict):
                continue

            operation_id = operation.get("operationId")
            if not operation_id:
                # Auto-generate from path + method
                clean_path = path.replace("/", "_").replace("{", "").replace("}", "").strip("_")
                operation_id = f"{method}_{clean_path}"

            tool_id = f"{category}__{_sanitize_tool_id(operation_id)}"
            name = operation.get("summary") or operation_id
            description = operation.get("description") or operation.get("summary") or name

            # Parameters
            path_params = methods.get("parameters", [])
            op_params = operation.get("parameters", [])
            all_params = path_params + op_params

            request_body = operation.get("requestBody")

            input_schema = _build_input_schema(all_params, request_body, components)

            # Output schema (simplified: take 200 response)
            responses = operation.get("responses", {})
            output_schema: Optional[Dict[str, Any]] = None
            for code in ("200", "201", "default"):
                if code in responses:
                    resp_content = responses[code].get("content", {})
                    json_resp = resp_content.get("application/json") or resp_content.get("application/json; charset=utf-8")
                    if json_resp and "schema" in json_resp:
                        output_schema = json_resp["schema"]
                    break

            config: Dict[str, Any] = {
                "spec_url": url,
                "base_url": base_url,
                "path": path,
                "method": method.upper(),
                "auth_schemes": auth_schemes,
            }

            tool = ToolV2(
                tool_id=tool_id,
                name=name,
                description=description,
                version="1.0.0",
                input_schema=input_schema,
                output_schema=output_schema,
                implementation=ToolImplementation(
                    type=ImplementationType.OPENAPI,
                    config=config,
                ),
                category=category,
                tags=["openapi", method.upper()],
                author="system",
                dependencies=[],
                sandboxed=False,
                timeout=30,
                max_retries=2,
            )
            tools.append(tool)

    logger.info(f"Ingested {len(tools)} tools from OpenAPI spec")
    return tools
