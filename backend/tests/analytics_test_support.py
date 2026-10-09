"""离线 analysis roles 集成测试使用的 ChatOpenAI double。"""

from __future__ import annotations

import asyncio
import json
from typing import Any, ClassVar

import httpx
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI
from pydantic import Field, PrivateAttr

_MODELS: list[ChatOpenAI] = []


class AnalysisChatOpenAI(ChatOpenAI):
    """保留真实 ChatOpenAI SDK 形状，并在本地异步入口产生固定结果。"""

    max_tokens: int | None = None
    max_retries: int = 3
    sql_responses: list[Any] = Field(default_factory=list)
    data_responses: list[Any] = Field(default_factory=list)
    layout_responses: list[Any] = Field(default_factory=list)
    reviewer_responses: list[Any] = Field(default_factory=list)
    sql_delay_seconds: float = 0
    reviewer_delay_seconds: float = 0
    calls: ClassVar[list[dict[str, Any]]] = []
    _reviewer_started: asyncio.Event = PrivateAttr(default_factory=asyncio.Event)

    @property
    def prompts(self) -> list[list[BaseMessage]]:
        return [call["messages"] for call in type(self).calls if call["role"] == "reviewer"]

    @property
    def _started(self) -> asyncio.Event:
        return self._reviewer_started

    @property
    def _llm_type(self) -> str:
        return "synthetic-analysis-chat-openai"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise AssertionError("analysis roles use their async model entry point")

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        system_prompt = str(messages[0].content) if messages else ""
        if "SQL 分析角色" in system_prompt:
            role = "sql_analyst"
            responses = self.sql_responses
            if self.sql_delay_seconds:
                await asyncio.sleep(self.sql_delay_seconds)
        elif "数据分析角色" in system_prompt:
            role = "data_analyst"
            responses = self.data_responses
        elif "报告布局角色" in system_prompt:
            role = "report_writer"
            responses = self.layout_responses
        elif "复核器" in system_prompt:
            role = "reviewer"
            responses = self.reviewer_responses
            self._reviewer_started.set()
            if self.reviewer_delay_seconds:
                await asyncio.sleep(self.reviewer_delay_seconds)
        else:
            raise AssertionError("unknown analysis model role")
        type(self).calls.append({"role": role, "messages": messages, "kwargs": kwargs, "model": self})

        if responses:
            response = responses.pop(0)
        elif role == "data_analyst":
            payload = json.loads(str(messages[-1].content))
            snapshot = payload["snapshots"][0]
            column_name = snapshot["columns"][0]
            response = json.dumps(
                {
                    "claims": [
                        {
                            "id": "cell-claim",
                            "operation": "cell",
                            "operands": [
                                {
                                    "evidence_id": snapshot["evidence_id"],
                                    "row_index": 0,
                                    "column_name": column_name,
                                }
                            ],
                            "decimal_places": 0,
                            "unit_reference": None,
                            "period_reference": None,
                        }
                    ],
                    "labels": [{"claim_id": "cell-claim", "label": "已验证数据"}],
                },
                ensure_ascii=False,
            )
        elif role == "report_writer":
            response = '{"sections":[{"kind":"summary","claim_ids":["cell-claim"]}]}'
        elif role == "reviewer":
            response = '{"approved":true,"reason_code":"approved"}'
        else:
            response = '{"sql":"SELECT 1"}'

        if isinstance(response, BaseException):
            raise response
        message = response if isinstance(response, BaseMessage) else AIMessage(content=str(response))
        return ChatResult(generations=[ChatGeneration(message=message)])


def create_analysis_chat_model(**kwargs: Any) -> AnalysisChatOpenAI:
    async_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}, request=request)))
    sync_client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}, request=request)))
    model = AnalysisChatOpenAI(
        model="gpt-synthetic",
        api_key="sk-local-test-only",
        base_url="https://offline.example/v1",
        http_async_client=async_client,
        http_client=sync_client,
        **kwargs,
    )
    _MODELS.append(model)
    return model


def clear_analysis_model_calls() -> None:
    AnalysisChatOpenAI.calls.clear()


async def close_analysis_chat_models() -> None:
    while _MODELS:
        model = _MODELS.pop()
        if model.root_async_client is not None:
            await model.root_async_client.close()
        if model.root_client is not None:
            model.root_client.close()
