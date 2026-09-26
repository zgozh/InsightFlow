"""Tests for deerflow.runtime.serialization."""

from __future__ import annotations


class _FakePydanticV2:
    """Object with model_dump (Pydantic v2)."""

    def model_dump(self):
        return {"key": "v2"}


class _FakePydanticV1:
    """Object with dict (Pydantic v1)."""

    def dict(self):
        return {"key": "v1"}


class _Unprintable:
    """Object whose str() raises."""

    def __str__(self):
        raise RuntimeError("no str")

    def __repr__(self):
        return "<Unprintable>"


def test_serialize_none():
    from deerflow.runtime.serialization import serialize_lc_object

    assert serialize_lc_object(None) is None


def test_serialize_primitives():
    from deerflow.runtime.serialization import serialize_lc_object

    assert serialize_lc_object("hello") == "hello"
    assert serialize_lc_object(42) == 42
    assert serialize_lc_object(3.14) == 3.14
    assert serialize_lc_object(True) is True


def test_serialize_dict():
    from deerflow.runtime.serialization import serialize_lc_object

    obj = {"a": _FakePydanticV2(), "b": [1, "two"]}
    result = serialize_lc_object(obj)
    assert result == {"a": {"key": "v2"}, "b": [1, "two"]}


def test_serialize_list():
    from deerflow.runtime.serialization import serialize_lc_object

    result = serialize_lc_object([_FakePydanticV1(), 1])
    assert result == [{"key": "v1"}, 1]


def test_serialize_tuple():
    from deerflow.runtime.serialization import serialize_lc_object

    result = serialize_lc_object((_FakePydanticV2(),))
    assert result == [{"key": "v2"}]


def test_serialize_pydantic_v2():
    from deerflow.runtime.serialization import serialize_lc_object

    assert serialize_lc_object(_FakePydanticV2()) == {"key": "v2"}


def test_serialize_pydantic_v1():
    from deerflow.runtime.serialization import serialize_lc_object

    assert serialize_lc_object(_FakePydanticV1()) == {"key": "v1"}


def test_serialize_fallback_str():
    from deerflow.runtime.serialization import serialize_lc_object

    result = serialize_lc_object(object())
    assert isinstance(result, str)


def test_serialize_fallback_repr():
    from deerflow.runtime.serialization import serialize_lc_object

    assert serialize_lc_object(_Unprintable()) == "<Unprintable>"


def test_serialize_channel_values_strips_pregel_keys():
    from deerflow.runtime.serialization import serialize_channel_values

    raw = {
        "messages": ["hello"],
        "__pregel_tasks": "internal",
        "__pregel_resuming": True,
        "__interrupt__": [{"value": "ask_human", "resumable": True}],
        "title": "Test",
    }
    result = serialize_channel_values(raw)
    assert "messages" in result
    assert "title" in result
    assert "__pregel_tasks" not in result
    assert "__pregel_resuming" not in result
    assert "__interrupt__" in result
    assert isinstance(result["__interrupt__"], list)
    assert len(result["__interrupt__"]) == 1
    assert result["__interrupt__"][0]["value"] == "ask_human"


def test_serialize_channel_values_serializes_objects():
    from deerflow.runtime.serialization import serialize_channel_values

    result = serialize_channel_values({"obj": _FakePydanticV2()})
    assert result == {"obj": {"key": "v2"}}


def test_serialize_messages_tuple():
    from deerflow.runtime.serialization import serialize_messages_tuple

    chunk = _FakePydanticV2()
    metadata = {"langgraph_node": "agent"}
    result = serialize_messages_tuple((chunk, metadata))
    assert result == [{"key": "v2"}, {"langgraph_node": "agent"}]


def test_serialize_messages_tuple_non_dict_metadata():
    from deerflow.runtime.serialization import serialize_messages_tuple

    result = serialize_messages_tuple((_FakePydanticV2(), "not-a-dict"))
    assert result == [{"key": "v2"}, {}]


def test_serialize_messages_tuple_fallback():
    from deerflow.runtime.serialization import serialize_messages_tuple

    result = serialize_messages_tuple("not-a-tuple")
    assert result == "not-a-tuple"


def test_serialize_dispatcher_messages_mode():
    from deerflow.runtime.serialization import serialize

    chunk = _FakePydanticV2()
    result = serialize((chunk, {"node": "x"}), mode="messages")
    assert result == [{"key": "v2"}, {"node": "x"}]


def test_serialize_dispatcher_values_mode():
    from deerflow.runtime.serialization import serialize

    result = serialize({"msg": "hi", "__pregel_tasks": "x"}, mode="values")
    assert result == {"msg": "hi"}


def test_serialize_dispatcher_default_mode():
    from deerflow.runtime.serialization import serialize

    result = serialize(_FakePydanticV1())
    assert result == {"key": "v1"}


# ── strip_data_url_image_blocks ──────────────────────────────────────────────


def _make_msg(
    content,
    *,
    hide_from_ui=False,
    msg_type="human",
):
    """Build a serialised-style message dict."""
    msg = {"type": msg_type, "content": content}
    if hide_from_ui:
        msg["additional_kwargs"] = {"hide_from_ui": True}
    return msg


def test_strip_data_url_removes_base64_from_hidden_messages():
    from deerflow.runtime.serialization import strip_data_url_image_blocks

    messages = [
        _make_msg(
            [
                {"type": "text", "text": "Here are the images:"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,iVBOR..."},
                },
                {"type": "text", "text": "- file.jpg (image/jpeg)"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/jpeg;base64,/9j/..."},
                },
            ],
            hide_from_ui=True,
        ),
    ]
    result = strip_data_url_image_blocks(messages)
    assert len(result) == 1
    content = result[0]["content"]
    # Only text blocks remain
    assert content == [
        {"type": "text", "text": "Here are the images:"},
        {"type": "text", "text": "- file.jpg (image/jpeg)"},
    ]


def test_strip_data_url_preserves_non_hidden_messages():
    from deerflow.runtime.serialization import strip_data_url_image_blocks

    messages = [
        _make_msg(
            [
                {"type": "text", "text": "Check this out"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,iVBOR..."},
                },
            ],
            hide_from_ui=False,
        ),
    ]
    result = strip_data_url_image_blocks(messages)
    assert result == messages


def test_strip_data_url_preserves_https_image_urls():
    from deerflow.runtime.serialization import strip_data_url_image_blocks

    messages = [
        _make_msg(
            [
                {"type": "text", "text": "See image"},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://example.com/img.png"},
                },
            ],
            hide_from_ui=True,
        ),
    ]
    result = strip_data_url_image_blocks(messages)
    assert result == messages


def test_strip_data_url_handles_string_content():
    from deerflow.runtime.serialization import strip_data_url_image_blocks

    messages = [
        _make_msg("plain text content", hide_from_ui=True),
    ]
    result = strip_data_url_image_blocks(messages)
    assert result == messages


def test_strip_data_url_handles_non_dict_messages():
    from deerflow.runtime.serialization import strip_data_url_image_blocks

    result = strip_data_url_image_blocks(["a_string", None, 42])
    assert result == ["a_string", None, 42]


def test_strip_data_url_mixed_messages():
    """A realistic mix: normal user message + hidden image injection + AI reply."""
    from deerflow.runtime.serialization import strip_data_url_image_blocks

    messages = [
        _make_msg("Please analyze this image", hide_from_ui=False),
        _make_msg(
            [
                {"type": "text", "text": "Here are the images:"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,AABBCCDD"},
                },
            ],
            hide_from_ui=True,
        ),
        _make_msg("I can see a landscape", msg_type="ai"),
    ]
    result = strip_data_url_image_blocks(messages)
    assert len(result) == 3
    # First message untouched
    assert result[0]["content"] == "Please analyze this image"
    # Hidden message: image_url stripped, text kept
    assert result[1]["content"] == [{"type": "text", "text": "Here are the images:"}]
    # AI message untouched
    assert result[2]["content"] == "I can see a landscape"


def test_serialize_channel_values_for_api_strips_base64():
    from deerflow.runtime.serialization import serialize_channel_values_for_api

    channel_values = {
        "messages": [
            {
                "type": "human",
                "content": "hello",
            },
            {
                "type": "human",
                "content": [
                    {"type": "text", "text": "images:"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,BIGDATA"},
                    },
                ],
                "additional_kwargs": {"hide_from_ui": True},
            },
        ],
        "title": "My thread",
    }
    result = serialize_channel_values_for_api(channel_values)
    assert result["title"] == "My thread"
    assert len(result["messages"]) == 2
    assert result["messages"][0]["content"] == "hello"
    # base64 block stripped, text block kept
    assert result["messages"][1]["content"] == [{"type": "text", "text": "images:"}]


def test_serialize_channel_values_for_api_no_messages():
    """When channel_values has no messages key, returns without error."""
    from deerflow.runtime.serialization import serialize_channel_values_for_api

    result = serialize_channel_values_for_api({"title": "empty"})
    assert result == {"title": "empty"}


def test_serialize_values_mode_strips_base64_from_hidden_messages():
    """The SSE stream emits ``values`` snapshots of the full state, so it must
    strip base64 image data from hide_from_ui messages just like the REST
    endpoints do — otherwise the same payload leaks over the stream."""
    import json

    from deerflow.runtime.serialization import serialize

    state = {
        "messages": [
            _make_msg(
                [
                    {"type": "text", "text": "context"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,iVBOR..."},
                    },
                ],
                hide_from_ui=True,
            ),
        ],
    }
    result = serialize(state, mode="values")
    # the hidden message survives (count/order preserved) but the data: block is gone
    assert len(result["messages"]) == 1
    assert "data:image/png;base64" not in json.dumps(result)
    assert result["messages"][0]["content"] == [{"type": "text", "text": "context"}]


def test_analytics_message_projection_keeps_model_state_and_non_analytics_messages_unchanged():
    import json

    from langchain_core.messages import AIMessage, ToolMessage

    from deerflow.runtime.serialization import project_analytics_structured_value, serialize_channel_values_for_api

    evidence = {
        "evidence_id": "a" * 64,
        "datasource_id": "ds-1",
        "query_hash": "b" * 64,
        "risk": "low",
        "schema_version": "schema-v1",
        "policy_version": "policy-v1",
        "plan_digest": "c" * 64,
        "estimated_rows": 1,
        "engine_cost": "0.25",
        "row_count": 1,
        "byte_count": 32,
        "truncated": False,
        "result_digest": "d" * 64,
        "decision_code": "executed",
    }
    analytics_call = AIMessage(
        content="",
        id="ai-analytics",
        tool_calls=[
            {
                "id": "call-analytics",
                "name": "query_business_data",
                "args": {
                    "datasource_id": "ds-1",
                    "sql": "SELECT SQL_SENTINEL",
                    "plan_id": "PLAN_SENTINEL",
                    "password": "CREDENTIAL_SENTINEL",
                },
            },
            {"id": "call-search", "name": "web_search", "args": {"query": "ordinary query"}},
        ],
    )
    analytics_result_content = json.dumps(
        {
            "code": "executed",
            "columns": ["COLUMN_SENTINEL"],
            "rows": [["ROW_SENTINEL"]],
            "row_count": 1,
            "truncated": False,
            "evidence": evidence,
            "plan_id": "PLAN_SENTINEL",
            "credential": "CREDENTIAL_SENTINEL",
        }
    )
    analytics_result = ToolMessage(
        content=analytics_result_content,
        tool_call_id="call-analytics",
        name="query_business_data",
    )
    ordinary_result = ToolMessage(content='{"query":"ordinary result"}', tool_call_id="call-search", name="web_search")

    result = serialize_channel_values_for_api({"messages": [analytics_call, analytics_result, ordinary_result]})

    projected_call, projected_result, projected_ordinary_result = result["messages"]
    assert projected_call["tool_calls"][0]["args"] == {"datasource_id": "ds-1"}
    assert projected_call["tool_calls"][1]["args"] == {"query": "ordinary query"}
    assert json.loads(projected_result["content"]) == {
        "code": "executed",
        "row_count": 1,
        "truncated": False,
        "evidence": evidence,
    }
    assert projected_ordinary_result["content"] == '{"query":"ordinary result"}'
    assert not any(sentinel in json.dumps(result) for sentinel in ("SQL_SENTINEL", "PLAN_SENTINEL", "CREDENTIAL_SENTINEL", "COLUMN_SENTINEL", "ROW_SENTINEL"))
    assert analytics_call.tool_calls[0]["args"]["sql"] == "SELECT SQL_SENTINEL"
    assert analytics_result.content == analytics_result_content

    provider_shape = project_analytics_structured_value(
        {
            "messages": [
                {
                    "type": "ai",
                    "additional_kwargs": {
                        "tool_calls": [
                            {
                                "id": "provider-analytics-call",
                                "function": {
                                    "name": "query_business_data",
                                    "arguments": '{"datasource_id":"ds-1","sql":"PROVIDER_SQL_SENTINEL"}',
                                },
                            }
                        ]
                    },
                },
                {
                    "type": "tool",
                    "tool_call_id": "provider-analytics-call",
                    "content": json.dumps({"code": "executed", "rows": [["PROVIDER_ROW_SENTINEL"]]}),
                },
            ]
        }
    )
    assert provider_shape["messages"][0]["additional_kwargs"]["tool_calls"][0]["function"]["arguments"] == '{"datasource_id":"ds-1"}'
    assert json.loads(provider_shape["messages"][1]["content"]) == {"code": "executed"}
    assert "PROVIDER_SQL_SENTINEL" not in json.dumps(provider_shape)
    assert "PROVIDER_ROW_SENTINEL" not in json.dumps(provider_shape)


def test_analysis_report_writer_projection_hides_markdown_and_projects_receipt_fields():
    import json

    from langchain_core.messages import AIMessage, ToolMessage

    from deerflow.runtime.serialization import project_analytics_event_rows, serialize_channel_values_for_api

    markdown = "REPORT_MARKDOWN_SQL_SENTINEL"
    evidence_id = "e" * 64
    writer_call = AIMessage(
        content="",
        id="ai-report-writer",
        tool_calls=[
            {
                "id": "call-report-writer",
                "name": "write_analysis_report",
                "args": {"title": "Synthetic report", "markdown": markdown, "evidence_ids": [evidence_id]},
            }
        ],
    )
    writer_result = ToolMessage(
        content=json.dumps(
            {
                "code": "published",
                "report_id": "report-1",
                "artifact_path": "/mnt/user-data/outputs/analysis-report-run_1.md",
                "evidence_ids": [evidence_id],
                "markdown": markdown,
                "principal_id": "PRINCIPAL_SENTINEL",
                "thread_id": "THREAD_SENTINEL",
                "run_id": "RUN_SENTINEL",
            }
        ),
        tool_call_id="call-report-writer",
        name="write_analysis_report",
    )

    projected = serialize_channel_values_for_api({"messages": [writer_call, writer_result]})
    projected_call, projected_result = projected["messages"]
    assert projected_call["tool_calls"][0]["args"] == {"title": "Synthetic report", "evidence_ids": [evidence_id]}
    assert json.loads(projected_result["content"]) == {
        "code": "published",
        "report_id": "report-1",
        "artifact_path": "/mnt/user-data/outputs/analysis-report-run_1.md",
        "evidence_ids": [evidence_id],
    }
    assert markdown not in json.dumps(projected)
    assert writer_call.tool_calls[0]["args"]["markdown"] == markdown
    assert markdown in writer_result.content

    event_rows = project_analytics_event_rows(
        [
            {
                "run_id": "run_1",
                "event_type": "subagent.step",
                "content": {
                    "kind": "ai",
                    "tool_calls": [
                        {
                            "id": "child-report-call",
                            "name": "write_analysis_report",
                            "args": {"title": "Synthetic report", "markdown": markdown, "evidence_ids": [evidence_id]},
                        }
                    ],
                },
            }
        ]
    )
    assert event_rows[0]["content"]["tool_calls"][0]["args"] == {"title": "Synthetic report", "evidence_ids": [evidence_id]}
    assert markdown not in json.dumps(event_rows)


def test_analysis_report_reviewer_receipts_survive_only_as_safe_sse_history_and_api_fields():
    import json

    from deerflow.runtime.serialization import project_analytics_event_rows, project_analytics_structured_value, serialize_channel_values_for_api

    sensitive = {
        "code": "analysis_review_rejected",
        "reason_code": "evidence_mismatch",
        "markdown": "REVIEW_MARKDOWN_SENTINEL",
        "sql": "REVIEW_SQL_SENTINEL",
        "rows": [["REVIEW_ROW_SENTINEL"]],
        "token": "REVIEW_TOKEN_SENTINEL",
        "exception": "REVIEW_EXCEPTION_SENTINEL",
        "report_id": "REPORT_ID_SENTINEL",
        "artifact_path": "/mnt/user-data/outputs/analysis-report-run_1.md",
        "evidence_ids": ["e" * 64],
    }
    tool_content = json.dumps(sensitive)
    raw_message = {
        "type": "tool",
        "name": "write_analysis_report",
        "tool_call_id": "call-review",
        "content": tool_content,
        "artifact": {"markdown": "ARTIFACT_SENTINEL"},
        "additional_kwargs": {"review": "RAW_REVIEW_SENTINEL"},
        "response_metadata": {"completion": "RAW_COMPLETION_SENTINEL"},
    }

    # SSE/stream values use the structured projector; state/history reads use
    # serialize_channel_values_for_api; persisted event reads use event rows.
    sse = project_analytics_structured_value(raw_message)
    history = serialize_channel_values_for_api({"messages": [raw_message]})["messages"][0]
    events = project_analytics_event_rows(
        [
            {
                "run_id": "run_1",
                "event_type": "subagent.step",
                "content": {
                    "kind": "tool",
                    "tool_name": "write_analysis_report",
                    "tool_call_id": "call-review",
                    "text": tool_content,
                },
            }
        ]
    )

    expected = {"code": "analysis_review_rejected", "reason_code": "evidence_mismatch"}
    assert json.loads(sse["content"]) == expected
    assert json.loads(history["content"]) == expected
    assert json.loads(events[0]["content"]["text"]) == expected
    encoded = json.dumps({"sse": sse, "history": history, "events": events}, ensure_ascii=False)
    assert not any(
        sentinel in encoded
        for sentinel in (
            "REVIEW_MARKDOWN_SENTINEL",
            "REVIEW_SQL_SENTINEL",
            "REVIEW_ROW_SENTINEL",
            "REVIEW_TOKEN_SENTINEL",
            "REVIEW_EXCEPTION_SENTINEL",
            "REPORT_ID_SENTINEL",
            "ARTIFACT_SENTINEL",
            "RAW_REVIEW_SENTINEL",
            "RAW_COMPLETION_SENTINEL",
        )
    )


def test_analysis_report_projection_limits_review_reason_and_failure_fields_to_their_codes():
    import json

    from deerflow.runtime.serialization import project_analytics_structured_value

    def project(code: str, reason_code: str | None = None) -> dict:
        payload = {"code": code, "markdown": "BODY_SENTINEL", "artifact_path": "/mnt/user-data/outputs/analysis-report-run_1.md", "evidence_ids": ["e" * 64]}
        if reason_code is not None:
            payload["reason_code"] = reason_code
        projected = project_analytics_structured_value({"type": "tool", "name": "write_analysis_report", "content": json.dumps(payload)})
        return json.loads(projected["content"])

    assert project("analysis_review_rejected", "missing_citation") == {
        "code": "analysis_review_rejected",
        "reason_code": "missing_citation",
    }
    assert project("analysis_review_rejected", "INTERNAL_SENTINEL") == {"code": "analysis_review_rejected"}
    for code in (
        "analysis_review_unavailable",
        "analysis_review_input_too_large",
        "analysis_review_attempt_limit",
        "analysis_evidence_unavailable",
    ):
        assert project(code, "unsupported_claim") == {"code": code}


def test_structured_projection_masks_partial_analytics_tool_names_in_all_raw_shapes():
    import copy
    import json

    from deerflow.runtime.serialization import project_analytics_structured_value, serialize_channel_values_for_api

    payload = {
        "messages": [
            {
                "type": "ai",
                "tool_calls": [{"id": "partial-writer", "name": "write_analysis_", "args": {"markdown": "BODY_SENTINEL"}}],
            },
            {
                "type": "tool",
                "tool_call_id": "partial-writer",
                "content": '{"markdown":"CORRELATED_BODY_SENTINEL"}',
            },
            {
                "type": "ai",
                "tool_calls": [{"id": "partial-query", "name": "query_business_", "args": {"sql": "SQL_SENTINEL"}}],
            },
            {
                "type": "ai",
                "invalid_tool_calls": [{"id": "invalid-writer", "name": "write_analysis_repor", "args": '{"markdown":"INVALID_BODY_SENTINEL"}'}],
            },
            {
                "type": "AIMessageChunk",
                "tool_call_chunks": [{"id": "chunk-query", "index": 0, "name": "query_business_dat", "args": '{"sql":"CHUNK_SQL_SENTINEL"}'}],
            },
            {
                "type": "ai",
                "additional_kwargs": {
                    "tool_calls": [
                        {
                            "id": "raw-writer",
                            "function": {"name": "write_analysis_repor", "arguments": '{"markdown":"RAW_BODY_SENTINEL"}'},
                        }
                    ],
                    "function_call": {
                        "name": "query_business_dat",
                        "arguments": '{"sql":"RAW_SQL_SENTINEL"}',
                    },
                },
            },
        ]
    }
    original = copy.deepcopy(payload)

    projected = project_analytics_structured_value(payload)
    encoded = json.dumps(projected, ensure_ascii=False)
    checkpoint_history = serialize_channel_values_for_api({"messages": payload["messages"]})
    checkpoint_history_encoded = json.dumps(checkpoint_history, ensure_ascii=False)

    assert not any(
        sentinel in encoded
        for sentinel in (
            "BODY_SENTINEL",
            "CORRELATED_BODY_SENTINEL",
            "SQL_SENTINEL",
            "INVALID_BODY_SENTINEL",
            "CHUNK_SQL_SENTINEL",
            "RAW_BODY_SENTINEL",
            "RAW_SQL_SENTINEL",
        )
    )
    assert not any(
        sentinel in checkpoint_history_encoded
        for sentinel in (
            "BODY_SENTINEL",
            "CORRELATED_BODY_SENTINEL",
            "SQL_SENTINEL",
            "INVALID_BODY_SENTINEL",
            "CHUNK_SQL_SENTINEL",
            "RAW_BODY_SENTINEL",
            "RAW_SQL_SENTINEL",
        )
    )
    assert payload == original


def test_structured_projection_masks_only_ambiguous_call_and_preserves_explicit_other_names():
    import json

    from deerflow.runtime.serialization import project_analytics_structured_value

    payload = {
        "type": "ai",
        "tool_calls": [
            {"args": {"markdown": "AMBIGUOUS_BODY_SENTINEL"}},
            {"id": "ordinary", "name": "web_search", "args": {"query": "ordinary query"}},
            {
                "id": "writer-preview",
                "name": "write_analysis_report_preview",
                "args": {"markdown": "visible writer-preview text"},
            },
            {
                "id": "query-export",
                "name": "query_business_data_export",
                "args": {"sql": "visible query-export text"},
            },
        ],
        "additional_kwargs": {
            "tool_calls": [
                {"function": {"arguments": '{"markdown":"AMBIGUOUS_RAW_BODY_SENTINEL"}'}},
                {"function": {"name": "web_search", "arguments": '{"query":"ordinary raw query"}'}},
            ]
        },
    }

    projected = project_analytics_structured_value(payload)
    calls = projected["tool_calls"]
    encoded = json.dumps(projected, ensure_ascii=False)

    assert "AMBIGUOUS_BODY_SENTINEL" not in encoded
    assert "AMBIGUOUS_RAW_BODY_SENTINEL" not in encoded
    assert calls[0]["args"] == {}
    assert calls[1]["args"] == {"query": "ordinary query"}
    assert calls[2]["args"] == {"markdown": "visible writer-preview text"}
    assert calls[3]["args"] == {"sql": "visible query-export text"}
    raw_calls = projected["additional_kwargs"]["tool_calls"]
    assert raw_calls[0]["function"]["arguments"] == "{}"
    assert raw_calls[1]["function"]["arguments"] == '{"query":"ordinary raw query"}'


def test_history_event_projection_masks_partial_invalid_and_raw_calls():
    import json

    from deerflow.runtime.serialization import project_analytics_event_rows

    events = [
        {
            "run_id": "synthetic-run",
            "event_type": "llm.ai.response",
            "content": {
                "type": "ai",
                "invalid_tool_calls": [{"id": "history-invalid", "name": "write_analysis_repor", "args": '{"markdown":"HISTORY_INVALID_SENTINEL"}'}],
                "additional_kwargs": {
                    "tool_calls": [
                        {
                            "id": "history-raw",
                            "function": {"name": "query_business_dat", "arguments": '{"sql":"HISTORY_RAW_SQL_SENTINEL"}'},
                        }
                    ]
                },
            },
        },
        {
            "run_id": "synthetic-run",
            "event_type": "llm.tool.result",
            "content": {
                "type": "tool",
                "tool_call_id": "history-raw",
                "content": '{"rows":[["HISTORY_RESULT_SENTINEL"]]}',
            },
        },
        {
            "run_id": "synthetic-run",
            "event_type": "subagent.step",
            "content": {
                "kind": "ai",
                "tool_calls": [{"id": "subagent-partial", "name": "write_analysis_", "args": {"markdown": "SUBAGENT_BODY_SENTINEL"}}],
            },
        },
        {
            "run_id": "synthetic-run",
            "event_type": "subagent.step",
            "content": {
                "kind": "tool",
                "tool_call_id": "subagent-partial",
                "text": '{"markdown":"SUBAGENT_RESULT_SENTINEL"}',
            },
        },
    ]

    projected = project_analytics_event_rows(events)
    encoded = json.dumps(projected, ensure_ascii=False)

    assert not any(
        sentinel in encoded
        for sentinel in (
            "HISTORY_INVALID_SENTINEL",
            "HISTORY_RAW_SQL_SENTINEL",
            "HISTORY_RESULT_SENTINEL",
            "SUBAGENT_BODY_SENTINEL",
            "SUBAGENT_RESULT_SENTINEL",
        )
    )
    assert projected[0]["content"]["invalid_tool_calls"][0]["args"] == ""
    assert json.loads(projected[1]["content"]["content"]) == {"code": "analytics_result_unavailable"}
