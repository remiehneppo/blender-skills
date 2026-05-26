from __future__ import annotations

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from blender_mcp.server import create_server


def _names(items):
    return {item.name for item in items}


def test_mcp_surface_exposes_tools_resources_and_prompts(settings) -> None:
    server = create_server(settings)
    tools = _names(asyncio.run(server.list_tools()))
    prompts = _names(asyncio.run(server.list_prompts()))
    resources = {str(item.uri) for item in asyncio.run(server.list_resources())}
    templates = {str(item.uriTemplate) for item in asyncio.run(server.list_resource_templates())}

    assert {"blender_healthcheck", "job_create", "render_object_mask", "image_segment", "image_edit_by_mask"} <= tools
    assert "blender_run_python" not in tools
    assert {
        "create_model_workflow",
        "product_render_workflow",
        "segment_edit_workflow",
        "cryptomatte_workflow",
    } <= prompts
    assert "blender://capabilities" in resources
    assert "blender://jobs/{job_id}/manifest" in templates


def test_unsafe_python_tool_requires_opt_in(settings) -> None:
    enabled = type(settings)(**{**settings.__dict__, "unsafe_python": True})
    tools = _names(asyncio.run(create_server(enabled).list_tools()))

    assert "blender_run_python" in tools


def test_capabilities_resource_states_mask_boundary(settings) -> None:
    contents = asyncio.run(create_server(settings).read_resource("blender://capabilities"))
    payload = json.loads(contents[0].content)
    assert payload["scene_identity_masks"] == "Cryptomatte Object/Material"
    assert payload["unsafe_python_enabled"] is False


def test_stdio_client_discovers_public_surface(settings) -> None:
    async def discover():
        env = os.environ | {
            "BLENDER_BIN": str(settings.blender_bin),
            "BLENDER_MCP_WORKSPACE_ROOT": str(settings.workspace_root),
            "BLENDER_MCP_OUTPUT_ROOT": str(settings.output_root),
            "BLENDER_MCP_YOLO_MODEL": str(settings.yolo_model),
        }
        params = StdioServerParameters(command=sys.executable, args=["-m", "blender_mcp.server"], env=env)
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = await session.list_tools()
                resources = await session.list_resources()
                prompts = await session.list_prompts()
                return tools, resources, prompts

    tools, resources, prompts = asyncio.run(discover())
    assert "blender_healthcheck" in {tool.name for tool in tools.tools}
    assert "blender://capabilities" in {str(resource.uri) for resource in resources.resources}
    assert "product_render_workflow" in {prompt.name for prompt in prompts.prompts}
