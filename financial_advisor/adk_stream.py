# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Helpers for ADK Agent Engine streamQuery (Playground-equivalent) clients."""

from __future__ import annotations

import json
from typing import Any

# Surfaced when Gateway Model Armor blocks ADK streamQuery ingress.
MODEL_ARMOR_BLOCK_MARKERS = (
    "MODEL_ARMOR",
    "model armor",
    "Model Armor",
    "blocked by the safety filters",
    "Prompt blocked",
    "FILTERED",
    "SafetyAttributes",
)


def extract_event_texts(event: dict[str, Any]) -> list[str]:
    """Collect text parts from a single ADK streamQuery event JSON object."""
    texts: list[str] = []
    content = event.get("content") or {}
    parts = content.get("parts") or []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if text:
            texts.append(text)
    # Some payloads nest under "actions" / top-level text.
    if not texts and isinstance(event.get("text"), str) and event["text"]:
        texts.append(event["text"])
    return texts


def parse_sse_payload(raw: str) -> list[dict[str, Any]]:
    """Parse SSE or NDJSON body from streamQuery into event dicts."""
    events: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        if not line or line == "[DONE]":
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def collect_response_text(events: list[dict[str, Any]]) -> str:
    """Join all text parts from stream events (final answer last wins for assert)."""
    chunks: list[str] = []
    for event in events:
        chunks.extend(extract_event_texts(event))
    return "\n".join(chunks).strip()


def looks_like_model_armor_block(status_code: int, body: str) -> bool:
    """True if HTTP status/body indicates Model Armor or safety block on ingress."""
    lowered = body.lower()
    if status_code in {400, 403, 429} and any(
        m.lower() in lowered for m in MODEL_ARMOR_BLOCK_MARKERS
    ):
        return True
    if status_code >= 400 and "modelarmor" in lowered.replace("_", ""):
        return True
    if "MODEL_ARMOR" in body:
        return True
    return False


def stream_has_runtime_error(raw: str) -> bool:
    """True when streamQuery SSE/NDJSON carries an agent TypeError / code 498."""
    if '"error_code"' in raw and '"error_message"' in raw:
        return True
    if '"code": 498' in raw or '"code":498' in raw:
        return True
    return False


def is_usable_agent_reply(text: str) -> bool:
    """Normal Playground answer should be non-empty and not a blank placeholder."""
    if not text or not text.strip():
        return False
    if text.strip() in {"No response.", "None"}:
        return False
    return True
