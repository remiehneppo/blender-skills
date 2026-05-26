---
name: blender-segmentation
description: >
  Instance-mask editing for external images through the Blender MCP server.
  Uses YOLO11-seg metadata and per-instance masks for extract,
  remove-background, blur-background, recolor and composite actions. Use when
  an input photograph or reference image contains multiple selectable objects.
  For known Blender scene objects or materials, use Cryptomatte via
  render_object_mask instead.
compatibility: "Requires blender-mcp-server with optional segmentation dependencies and locally prepared YOLO weights."
license: MIT
allowed-tools: mcp__blender__*
---

## Preferred MCP Workflow

1. Call `blender_healthcheck` and confirm segmentation model availability.
2. Create a job with `job_create`.
3. Call `image_segment` on an image inside the configured workspace, optionally
   filtering by class and confidence.
4. Choose exactly one returned `instance_id`, reviewing `bbox`,
   `confidence`, `mask_path` and `preview_path`.
5. Call `image_edit_by_mask` with that `instance_id` and one action:
   `extract`, `remove_background`, `blur_background`, `recolor` or
   `composite`.

## Identity Boundary

YOLO identifies visual instances in an external image. Do not infer that an
instance maps to a named Blender object. For a render produced from a known
scene, call `render_object_mask` with the exact object or material name; that
tool uses Cryptomatte identity passes.

## Model Setup

Weights must already exist at `BLENDER_MCP_YOLO_MODEL`; do not trigger an
implicit download during an agent workflow. The server's direct Ultralytics
integration is distributed separately under `AGPL-3.0-or-later`.
