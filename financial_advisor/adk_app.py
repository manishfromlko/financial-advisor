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

"""AdkApp wrapper that rebuilds the agent graph at set_up time.

Cloudpickling LlmAgent can drop Pydantic private state (`__pydantic_private__`).
When the Agent Engine runtime google-adk version differs from the pickle host,
`canonical_model` then raises TypeError: 'NoneType' object is not subscriptable.
Re-importing `root_agent` from the deployed package after unpickle avoids that.
"""

from __future__ import annotations

from vertexai.preview.reasoning_engines import AdkApp

from financial_advisor.agent import root_agent


class FinancialAdvisorAdkApp(AdkApp):
    """AdkApp that rebinds a freshly constructed agent during set_up."""

    def set_up(self) -> None:
        from financial_advisor.agent import root_agent as fresh_root

        self._tmpl_attrs["agent"] = fresh_root
        super().set_up()


def build_adk_app() -> FinancialAdvisorAdkApp:
    return FinancialAdvisorAdkApp(agent=root_agent)
