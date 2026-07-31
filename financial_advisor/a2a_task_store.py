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

"""Shared GCS-backed A2A TaskStore for multi-worker Agent Engine."""

from __future__ import annotations

import asyncio
import logging
import os

from a2a.server.context import ServerCallContext
from a2a.server.tasks.task_store import TaskStore
from a2a.types import Task

logger = logging.getLogger(__name__)


class GcsTaskStore(TaskStore):
    """Persist A2A tasks in GCS so get_task works across uvicorn workers.

    Agent Engine runs multiple processes; InMemoryTaskStore is per-process, which
    causes playground polling to return "Task not found" when it lands on another
    worker than the one that handled message:send.
    """

    def __init__(
        self,
        bucket_name: str | None = None,
        prefix: str = "a2a_tasks",
    ) -> None:
        from google.cloud import storage

        bucket_name = (
            bucket_name
            or os.environ.get("A2A_TASK_STORE_BUCKET")
            or os.environ.get("GOOGLE_CLOUD_STORAGE_BUCKET")
        )
        if not bucket_name:
            raise ValueError(
                "GcsTaskStore requires bucket_name or A2A_TASK_STORE_BUCKET / "
                "GOOGLE_CLOUD_STORAGE_BUCKET."
            )
        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket_name)
        self._prefix = prefix.strip("/")
        logger.info(
            "Initialized GcsTaskStore bucket=%s prefix=%s",
            bucket_name,
            self._prefix,
        )

    def _blob(self, task_id: str):
        return self._bucket.blob(f"{self._prefix}/{task_id}.json")

    async def save(
        self, task: Task, context: ServerCallContext | None = None
    ) -> None:
        payload = task.model_dump_json(by_alias=True, exclude_none=True)
        await asyncio.to_thread(
            self._blob(task.id).upload_from_string,
            payload,
            "application/json",
        )
        logger.debug("Saved A2A task %s to GCS", task.id)

    async def get(
        self, task_id: str, context: ServerCallContext | None = None
    ) -> Task | None:
        blob = self._blob(task_id)
        exists = await asyncio.to_thread(blob.exists)
        if not exists:
            logger.debug("A2A task %s not found in GCS", task_id)
            return None
        payload = await asyncio.to_thread(blob.download_as_text)
        return Task.model_validate_json(payload)

    async def delete(
        self, task_id: str, context: ServerCallContext | None = None
    ) -> None:
        blob = self._blob(task_id)
        exists = await asyncio.to_thread(blob.exists)
        if not exists:
            logger.warning("Attempted to delete missing A2A task %s", task_id)
            return
        await asyncio.to_thread(blob.delete)
        logger.debug("Deleted A2A task %s from GCS", task_id)


def build_gcs_task_store() -> GcsTaskStore:
    """Builder used by A2aAgent(task_store_builder=...)."""
    return GcsTaskStore()
