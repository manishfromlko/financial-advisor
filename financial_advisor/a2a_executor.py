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

"""A2A executor bridging the A2A protocol to the ADK financial advisor."""

from __future__ import annotations

from typing import NoReturn

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState, TextPart, UnsupportedOperationError
from a2a.utils import new_agent_text_message
from a2a.utils.errors import ServerError
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from financial_advisor.agent import root_agent as financial_advisor_agent


class FinancialAdvisorAgentExecutor(AgentExecutor):
    """Bridge between A2A requests and the ADK financial coordinator.

    Uses InMemorySessionService (same pattern as the Agent Engine A2A docs).
    Agent Engine playground context_ids are Vertex sessions owned by the
    console user; looking them up via VertexAiSessionService with a default
    a2a-user id raises ownership errors, so we keep ADK sessions in-memory.
    """

    def __init__(self) -> None:
        self.agent = None
        self.runner = None

    def _init_agent(self) -> None:
        if self.agent is not None:
            return

        self.agent = financial_advisor_agent
        self.runner = Runner(
            app_name=self.agent.name,
            agent=self.agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )

    @staticmethod
    def _resolve_user_id(context: RequestContext) -> str:
        metadata = {}
        if context.message and context.message.metadata:
            metadata.update(context.message.metadata)
        if context.metadata:
            metadata.update(context.metadata)
        for key in ("user_id", "userId", "USER_ID"):
            value = metadata.get(key)
            if value:
                return str(value)
        # Fall back to a stable per-context id so playground turns stay isolated.
        if context.context_id:
            return f"a2a-{context.context_id}"
        return "a2a-user"

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if self.agent is None:
            self._init_agent()

        query = context.get_user_input()
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        user_id = self._resolve_user_id(context)

        if not context.current_task:
            await updater.submit()
        await updater.start_work()

        try:
            session = await self._get_or_create_session(context.context_id, user_id)
            content = types.Content(role="user", parts=[types.Part(text=query)])

            async for event in self.runner.run_async(
                session_id=session.id,
                user_id=user_id,
                new_message=content,
            ):
                if event.is_final_response():
                    parts = event.content.parts if event.content else []
                    answer = " ".join(p.text for p in parts if p.text) or "No response."
                    await updater.add_artifact([TextPart(text=answer)], name="answer")
                    await updater.complete()
                    return

            await updater.update_status(
                TaskState.failed,
                message=new_agent_text_message(
                    "Failed to generate a final response with text content."
                ),
            )
        except Exception as e:
            await updater.update_status(
                TaskState.failed,
                message=new_agent_text_message(f"Error: {e!s}"),
            )
            raise

    async def _get_or_create_session(self, context_id: str | None, user_id: str):
        app_name = self.runner.app_name
        if context_id:
            session = await self.runner.session_service.get_session(
                app_name=app_name,
                session_id=context_id,
                user_id=user_id,
            )
            if session:
                return session
        return await self.runner.session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=context_id,
        )

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> NoReturn:
        raise ServerError(error=UnsupportedOperationError())
