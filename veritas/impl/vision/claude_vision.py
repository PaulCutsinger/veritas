"""
veritas.impl.vision.claude_vision
----------------------------------
Concrete VisionBackend that uses the Anthropic Claude API to describe
rendered factory scene images. Intended for cross-checking render outputs
against USD stage intent.
"""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path

import anthropic

from ...core.models import VisionResult
from ...interface.vision_backend import VisionBackend

_MODEL = "claude-opus-4-6"

_SYSTEM_PROMPT = """\
You are a factory simulation scene analyst. You are given a rendered image of a USD
factory scene used in NVIDIA Isaac Sim or Isaac Lab. Your job is to:

1. Describe what you see in the scene in 2-4 concise sentences focused on factory
   elements: robots, conveyor belts, workstations, shelving, floor markings, lighting,
   and any obvious simulation artefacts (clipping, z-fighting, missing geometry).

2. List all distinct entity types you can identify as a JSON array of strings under the
   key "entities". Use short canonical labels: "robot_arm", "conveyor", "pallet",
   "forklift", "shelf", "workstation", "human_worker", "sensor", "camera", "floor",
   "ceiling", "wall", etc.

Respond in this exact JSON format (no markdown fences, no extra keys):
{
  "description": "<2-4 sentence scene description>",
  "entities": ["label1", "label2", ...]
}
"""


class ClaudeVisionBackend(VisionBackend):
    """Sends a rendered image to Claude for scene analysis.

    Args:
        api_key: Anthropic API key. Defaults to ``ANTHROPIC_API_KEY`` env var.
        model: Claude model ID to use. Defaults to ``claude-opus-4-6``.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = _MODEL,
    ) -> None:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise OSError(
                "ANTHROPIC_API_KEY environment variable is not set and no api_key "
                "was provided to ClaudeVisionBackend."
            )
        self._client = anthropic.Anthropic(api_key=key)
        self._model = model

    def describe(self, image_path: str, context: str = "") -> VisionResult:
        """Send *image_path* to Claude and return a structured VisionResult.

        Args:
            image_path: Absolute or relative path to the rendered image (PNG/JPEG).
            context: Optional free-text context about what the scene should contain
                     (e.g. the USD stage path or a short description). This is
                     appended to the user message to help Claude focus.
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        suffix = path.suffix.lower()
        media_type_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }
        media_type = media_type_map.get(suffix, "image/png")

        image_data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")

        user_content: list[dict] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_data,
                },
            },
            {
                "type": "text",
                "text": (
                    "Analyse this factory scene render."
                    + (f" Context: {context}" if context else "")
                    + " Respond with the JSON format specified in your instructions."
                ),
            },
        ]

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )

        raw = response.content[0].text.strip()
        return _parse_vision_response(raw)


def _parse_vision_response(raw: str) -> VisionResult:
    """Parse JSON response from Claude into a VisionResult.

    Falls back gracefully if Claude returns malformed JSON.
    """
    import json

    # Strip accidental markdown fences
    cleaned = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.MULTILINE)
    cleaned = re.sub(r"\n?```$", "", cleaned, flags=re.MULTILINE).strip()

    try:
        data = json.loads(cleaned)
        description = str(data.get("description", raw))
        entities = [str(e) for e in data.get("entities", [])]
    except json.JSONDecodeError:
        # Degrade gracefully: treat the whole response as the description.
        description = raw
        entities = []

    return VisionResult(description=description, entities=entities)
