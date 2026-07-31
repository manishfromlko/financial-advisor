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

"""Deployment script for Financial Advisor"""

import os

import vertexai
from absl import app, flags
from dotenv import load_dotenv
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp

from financial_advisor.agent import root_agent

FLAGS = flags.FLAGS
flags.DEFINE_string("project_id", None, "GCP project ID.")
flags.DEFINE_string("location", None, "GCP location.")
flags.DEFINE_string("bucket", None, "GCP bucket.")
flags.DEFINE_string("resource_id", None, "ReasoningEngine resource ID.")

flags.DEFINE_bool("list", False, "List all agents.")
flags.DEFINE_bool("create", False, "Creates a new agent.")
flags.DEFINE_bool("update", False, "Updates an existing agent.")
flags.DEFINE_bool("delete", False, "Deletes an existing agent.")
flags.mark_bool_flags_as_mutual_exclusive(["create", "update", "delete"])

# Floors required for Agent Engine Observability settings in Cloud Console.
# See: google-cloud-aiplatform >= 1.126.1 and google-adk >= 1.18.0
AGENT_ENGINE_REQUIREMENTS = [
    "google-adk (>=1.18.0)",
    "google-cloud-aiplatform[agent_engines] (>=1.126.1)",
    "google-genai (>=1.9.0)",
    "pydantic (>=2.10.6,<3.0.0)",
    "absl-py (>=2.2.1,<3.0.0)",
]

# Enables traces/logs in Agent Engine + GenAI semantic conventions.
# EVENT_ONLY puts prompt/response content in Cloud Logging events (not spans).
AGENT_ENGINE_ENV_VARS = {
    "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
    "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "EVENT_ONLY",
    "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS": "false",
}


def _build_adk_app() -> AdkApp:
    """Build the AdkApp used for create/update.

    enable_tracing is left unset so the Cloud Console telemetry toggle and
    GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY control observability.
    """
    return AdkApp(agent=root_agent)


def create() -> None:
    """Creates an agent engine for Financial Advisors."""
    remote_agent = agent_engines.create(
        _build_adk_app(),
        display_name=root_agent.name,
        requirements=AGENT_ENGINE_REQUIREMENTS,
        env_vars=AGENT_ENGINE_ENV_VARS,
    )
    print(f"Created remote agent: {remote_agent.resource_name}")


def update(resource_id: str) -> None:
    """Updates an existing agent engine with current code and observability deps."""
    remote_agent = agent_engines.update(
        resource_id,
        agent_engine=_build_adk_app(),
        requirements=AGENT_ENGINE_REQUIREMENTS,
        env_vars=AGENT_ENGINE_ENV_VARS,
    )
    print(f"Updated remote agent: {remote_agent.resource_name}")


def delete(resource_id: str) -> None:
    remote_agent = agent_engines.get(resource_id)
    remote_agent.delete(force=True)
    print(f"Deleted remote agent: {resource_id}")


def list_agents() -> None:
    remote_agents = agent_engines.list()
    template = """
{agent.name} ("{agent.display_name}")
- Create time: {agent.create_time}
- Update time: {agent.update_time}
"""
    remote_agents_string = "\n".join(
        template.format(agent=agent) for agent in remote_agents
    )
    print(f"All remote agents:\n{remote_agents_string}")


def main(argv: list[str]) -> None:
    del argv  # unused
    load_dotenv()

    project_id = (
        FLAGS.project_id
        if FLAGS.project_id
        else os.getenv("GOOGLE_CLOUD_PROJECT")
    )
    location = (
        FLAGS.location if FLAGS.location else os.getenv("GOOGLE_CLOUD_LOCATION")
    )
    bucket = (
        FLAGS.bucket
        if FLAGS.bucket
        else os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET")
    )

    print(f"PROJECT: {project_id}")
    print(f"LOCATION: {location}")
    print(f"BUCKET: {bucket}")

    if not project_id:
        print("Missing required environment variable: GOOGLE_CLOUD_PROJECT")
        return
    elif not location:
        print("Missing required environment variable: GOOGLE_CLOUD_LOCATION")
        return
    elif not bucket:
        print(
            "Missing required environment variable: GOOGLE_CLOUD_STORAGE_BUCKET"
        )
        return

    vertexai.init(
        project=project_id,
        location=location,
        staging_bucket=f"gs://{bucket}",
    )

    if FLAGS.list:
        list_agents()
    elif FLAGS.create:
        create()
    elif FLAGS.update:
        if not FLAGS.resource_id:
            print("resource_id is required for update")
            return
        update(FLAGS.resource_id)
    elif FLAGS.delete:
        if not FLAGS.resource_id:
            print("resource_id is required for delete")
            return
        delete(FLAGS.resource_id)
    else:
        print("Unknown command")


if __name__ == "__main__":
    app.run(main)
