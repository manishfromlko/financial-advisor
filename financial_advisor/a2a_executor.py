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

import logging
import os
from typing import NoReturn

import vertexai
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState, TextPart, UnsupportedOperationError
from a2a.utils import new_agent_text_message
from a2a.utils.errors import ServerError
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService, VertexAiSessionService
from google.adk.utils.context_utils import Aclosing
from google.genai import types
from google.genai.errors import ClientError

from financial_advisor.agent import root_agent as financial_advisor_agent

logger = logging.getLogger(__name__)

EMPTY_FINAL_RESPONSE_MESSAGE = (
    "The model returned no text for this turn. "
    "This often means Gemini safety filters or "
    "Model Armor blocked the prompt/response. "
    "Check Model Armor / Security findings, or "
    "retry with a normal request such as: Analyze AAPL"
)


class FinancialAdvisorAgentExecutor(AgentExecutor):
    """Bridge between A2A requests and the ADK financial coordinator.

    On Agent Engine, uses VertexAiSessionService keyed by the playground
    session (context_id) and the session's real owner user_id. Locally uses
    InMemorySessionService.
    """

    def __init__(self) -> None:
        self.agent = None
        self.runner = None
        self._use_vertex_sessions = False

    def _init_agent(self) -> None:
        if self.agent is not None:
            return

        self.agent = financial_advisor_agent
        engine_id = os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID")

        if engine_id:
            project = os.environ.get("GOOGLE_CLOUD_PROJECT")
            location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
            if location == "global":
                location = "us-central1"
            vertexai.init(project=project, location=location)
            session_service = VertexAiSessionService(
                project=project,
                location=location,
                agent_engine_id=engine_id,
            )
            # Playground sessions belong to this Reasoning Engine id.
            app_name = engine_id
            self._use_vertex_sessions = True
        else:
            session_service = InMemorySessionService()
            app_name = self.agent.name
            self._use_vertex_sessions = False

        self.runner = Runner(
            app_name=app_name,
            agent=self.agent,
            artifact_service=InMemoryArtifactService(),
            session_service=session_service,
            memory_service=InMemoryMemoryService(),
        )

    @staticmethod
    def _metadata_user_id(context: RequestContext) -> str | None:
        metadata = {}
        if context.message and context.message.metadata:
            metadata.update(context.message.metadata)
        if context.metadata:
            metadata.update(context.metadata)
        for key in ("user_id", "userId", "USER_ID"):
            value = metadata.get(key)
            if value:
                return str(value)
        return None

    async def _lookup_vertex_session_owner(self, session_id: str) -> str | None:
        """Read the playground session owner so get_session ownership checks pass."""
        if not isinstance(self.runner.session_service, VertexAiSessionService):
            return None
        reasoning_engine_id = self.runner.session_service._get_reasoning_engine_id(
            self.runner.app_name
        )
        session_resource_name = (
            f"reasoningEngines/{reasoning_engine_id}/sessions/{session_id}"
        )
        try:
            async with self.runner.session_service._get_api_client() as api_client:
                response = await api_client.agent_engines.sessions.get(
                    name=session_resource_name
                )
            return getattr(response, "user_id", None)
        except ClientError as e:
            if getattr(e, "code", None) == 404:
                return None
            raise

    async def _resolve_user_id(self, context: RequestContext) -> str:
        # Agent Engine playground context_id is a Vertex session. Prefer that
        # session's real owner over generic metadata like user_id="user", which
        # fails VertexAiSessionService ownership checks.
        if self._use_vertex_sessions and context.context_id:
            owner = await self._lookup_vertex_session_owner(context.context_id)
            if owner:
                return owner

        metadata_user = self._metadata_user_id(context)
        if metadata_user and metadata_user not in {"user", "a2a-user", "a2a_user"}:
            return metadata_user

        if context.context_id:
            return f"a2a-{context.context_id}"
        return "a2a-user"

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

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if self.agent is None:
            self._init_agent()

        query = context.get_user_input()
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        user_id = await self._resolve_user_id(context)

        if not context.current_task:
            await updater.submit()
        await updater.start_work()

        try:
            session = await self._get_or_create_session(context.context_id, user_id)
            content = types.Content(role="user", parts=[types.Part(text=query)])

            # Do not return inside the async-for: that cancels the ADK runner
            # (GeneratorExit / "Root node was cancelled") and can make the
            # playground wipe the conversation even after a good reply.
            # Collect the last non-empty model text as a fallback: for blocked
            # / jailbreak prompts Gemini often marks a "final" event with no
            # text parts, which previously became a blank "No response." in
            # the playground.
            final_answer: str | None = None
            last_model_text: str | None = None
            async with Aclosing(
                self.runner.run_async(
                    session_id=session.id,
                    user_id=user_id,
                    new_message=content,
                )
            ) as agen:
                async for event in agen:
                    if event.content and event.content.parts:
                        texts = [
                            p.text
                            for p in event.content.parts
                            if getattr(p, "text", None)
                        ]
                        if texts:
                            last_model_text = "\n".join(texts)
                    if event.is_final_response():
                        parts = event.content.parts if event.content else []
                        text = " ".join(
                            p.text for p in parts if getattr(p, "text", None)
                        )
                        final_answer = text or last_model_text
                        if not final_answer:
                            final_answer = EMPTY_FINAL_RESPONSE_MESSAGE
                            logger.warning(
                                "Empty final ADK response for query=%r "
                                "event=%r",
                                query[:200],
                                event,
                            )
                        break

            if final_answer is not None:
                await updater.add_artifact(
                    [TextPart(text=final_answer)], name="answer"
                )
                await updater.complete()
                return

            await updater.update_status(
                TaskState.failed,
                message=new_agent_text_message(
                    "Failed to generate a final response with text content."
                ),
            )
        except Exception as e:
            logger.exception("A2A agent execution failed")
            await updater.update_status(
                TaskState.failed,
                message=new_agent_text_message(f"Error: {e!s}"),
            )
            raise

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> NoReturn:
        raise ServerError(error=UnsupportedOperationError())
