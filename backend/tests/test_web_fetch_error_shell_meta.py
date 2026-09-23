"""web_fetch error-page classification (issue #4273).

Fetching a missing URL succeeds at the transport layer, so the server's error page
reached the model stamped ``deerflow_tool_meta.status="success"``: none of the existing
error branches (tool ``status="error"``, an ``Error:`` prefix, a JSON ``error`` field)
apply to a 200-with-an-error-body, and it fell through to success. ToolProgress then
counted the shell as evidence.

The classifier keys on the *extracted title* being nothing but an HTTP status line.
The cases below feed the real ``normalize_tool_message`` / middleware entry points, so
the payload shapes under test are the ones production consumes rather than
hand-written approximations.

Every assertion checks the whole metadata tuple, not just ``status``.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import ToolMessage

from deerflow.agents.middlewares.tool_result_meta import (
    _ATTRS_BY_ERROR_TYPE,
    _ERROR_SHELL_PHRASES,
    TOOL_META_KEY,
    _classify_error_shell,
    _classify_error_text,
    normalize_tool_message,
)

_SUBSTANTIVE_BODY = "Rice is a staple for most of the planet, and the difference between good rice and great rice is almost always technique rather than equipment."


def _msg(content: str, *, name: str = "web_fetch", status: str = "success") -> ToolMessage:
    return ToolMessage(content=content, tool_call_id="tc-1", name=name, status=status, additional_kwargs={})


def _meta(msg: ToolMessage) -> dict[str, object]:
    return msg.additional_kwargs[TOOL_META_KEY]


def _tuple(status: str, error_type: str | None, recoverable: bool, next_action: str) -> dict[str, object]:
    return {
        "status": status,
        "error_type": error_type,
        "recoverable_by_model": recoverable,
        "recommended_next_action": next_action,
        "source": "content_analysis",
    }


_SUCCESS = _tuple("success", None, True, "continue")


# ---------------------------------------------------------------------------
# Titles that are nothing but a status line


@pytest.mark.parametrize(
    "title,error_type,recoverable,next_action",
    [
        ("# 404 Not Found", "not_found", True, "rewrite_query"),
        ("# Page not found", "not_found", True, "rewrite_query"),
        ("# Not Found", "not_found", True, "rewrite_query"),
        ("# 404 - File or directory not found.", "not_found", True, "rewrite_query"),
        ("# HTTP Error 404 - Not Found", "not_found", True, "rewrite_query"),
        ("# 403 Forbidden", "permission", True, "try_alternative"),
        ("# Access Denied", "permission", True, "try_alternative"),
        ("# Permission denied", "permission", True, "try_alternative"),
        ("# 401 Unauthorized", "auth", False, "stop"),
        ("# 407 Proxy Authentication Required", "auth", False, "stop"),
        ("# 429 Too Many Requests", "rate_limited", False, "summarize"),
        # The 5xx split (review on #4314): 500/501 stay `internal` (stop), 502/503/504
        # are `transient` (try_alternative) — a gateway error page warns and escalates
        # instead of hard-blocking web_fetch on first sight.
        ("# 500 Internal Server Error", "internal", False, "stop"),
        ("# 501 Not Implemented", "internal", False, "stop"),
        ("# 502 Bad Gateway", "transient", False, "try_alternative"),
        ("# 503 Service Unavailable", "transient", False, "try_alternative"),
        ("# 503 Service Temporarily Unavailable", "transient", False, "try_alternative"),
        ("# 504 Gateway Timeout", "transient", False, "try_alternative"),
    ],
)
def test_status_line_title_is_classified_as_error(title: str, error_type: str, recoverable: bool, next_action: str):
    content = f"{title}\n\n---\n\nnginx/1.24.0"

    assert _meta(normalize_tool_message(_msg(content))) == _tuple("error", error_type, recoverable, next_action)


def test_body_prose_does_not_rescue_an_error_title():
    """Apache ships a sentence of body; it is still an error page."""
    content = "# 404 Not Found\n\nThe requested URL was not found on this server.\n\n---\n\nApache/2.4.58"

    assert _meta(normalize_tool_message(_msg(content)))["error_type"] == "not_found"


# ---------------------------------------------------------------------------
# Negative controls: documents that merely mention a status stay successful.


@pytest.mark.parametrize(
    "content",
    [
        # Legitimate titles that begin with a bare status number. This is why a bare
        # numeric code is stripped but never matched on its own.
        f"# 404 Ways to Cook Rice\n\n{_SUBSTANTIVE_BODY}",
        "# 404 Ways to Cook Rice",
        f"# 404 ways to improve API reliability\n\n{_SUBSTANTIVE_BODY}",
        "# 500 Startup Ideas Worth Stealing",
        "# 403",
        "404",
        # A document *about* a status: the phrase is there, but so are other words, and
        # matching is by equality. This is the case a substring scan would break.
        f"# Not Found: a short history of the 404\n\n{_SUBSTANTIVE_BODY}",
        "# Not Found: a short history of the 404",
        "# The Page Not Found Problem",
        "# Forbidden Planet",
        # Single-word document titles that collide with a reason phrase. "Gone" was dropped
        # from the phrase table for exactly this reason (410 is rare; the title is not), so
        # this is the control that records the decision.
        "# Gone",
        "# Gone\n\nA novel about a disappearance.",
        # API documentation listing status codes. Every reason phrase appears verbatim
        # as its own line, so this is what keeps the rule anchored to the *title* rather
        # than scanning the body. Dropping it makes a whole-document scan look safe.
        "# HTTP Status Codes\n\nThe most common client errors are:\n\nNot Found\n\nForbidden\n\nToo Many Requests\n\nAll are defined in RFC 9110.",
        f"# Debugging 404s\n\nWhen a page is not found, check the router first.\n\n{_SUBSTANTIVE_BODY}",
        # Explicitly *not* failure evidence per the issue triage: an untitled page, an
        # untitled-but-substantive page, and short valid content.
        "# Untitled",
        f"# Untitled\n\n{_SUBSTANTIVE_BODY}",
        "# Untitled\n\nNo content could be extracted from this page",
        "# Status\n\nAll systems operational.",
        "OK",
        # Empty / whitespace-only content must not be classified as an error.
        "",
        "   \n\n  ",
    ],
)
def test_document_content_stays_successful(content: str):
    assert _meta(normalize_tool_message(_msg(content))) == _SUCCESS


# ---------------------------------------------------------------------------
# Cross-path consistency: a phrase must not classify differently through the shell
# table than the same words would through _classify_error_text. (Review on #4314:
# "service temporarily unavailable" was `internal` here while _ERROR_RULES'
# "temporarily unavailable" keyword → `transient`; "gateway timeout" had the same
# split via the "timeout" keyword.) Phrases the keyword rules are silent on pass
# vacuously — the table deliberately knows phrases the rules don't.


@pytest.mark.parametrize("phrase,shell_type", sorted(_ERROR_SHELL_PHRASES.items()))
def test_shell_phrase_category_agrees_with_the_keyword_rules(phrase: str, shell_type: str):
    rules_type = _classify_error_text(phrase)["error_type"]

    assert rules_type in ("unknown", shell_type)


def test_shell_attrs_are_a_fresh_copy_per_call():
    """Match _classify_error_text's copy pattern: never hand out the rules-table dict."""
    msg = _msg("# 404 Not Found")
    first = _classify_error_shell(msg, "# 404 Not Found")
    second = _classify_error_shell(msg, "# 404 Not Found")

    assert first == _ATTRS_BY_ERROR_TYPE["not_found"]
    assert first is not _ATTRS_BY_ERROR_TYPE["not_found"]
    assert first is not second


def test_partial_marker_on_web_fetch_still_wins():
    """Direction two: the new branch must not swallow the existing partial path."""
    meta = _meta(normalize_tool_message(_msg("No results found")))

    assert meta["status"] == "partial_success"
    assert meta["recommended_next_action"] == "rewrite_query"


def test_existing_structured_stamp_is_not_overwritten():
    """Composition, not reclassification: a producer that already stamped wins."""
    existing = {"status": "partial_success", "source": "tool_return", "error_type": None}
    msg = ToolMessage(content="# 404 Not Found", tool_call_id="tc-1", name="web_fetch", additional_kwargs={TOOL_META_KEY: existing})

    assert _meta(normalize_tool_message(msg)) is existing


# ---------------------------------------------------------------------------
# Scoping: normalize_tool_message() normalizes EVERY tool, so the rule is gated on
# web_fetch identity. Other tools legitimately return these exact words.


@pytest.mark.parametrize("tool_name", ["read_file", "bash", "grep", "web_search", "memory_search", "test_tool"])
@pytest.mark.parametrize("content", ["# 404 Not Found", "Access denied", "Not Found", "Too Many Requests"])
def test_unrelated_tools_returning_the_same_wording_are_unchanged(tool_name: str, content: str):
    assert _meta(normalize_tool_message(_msg(content, name=tool_name))) == _SUCCESS


def test_unnamed_tool_message_is_unchanged():
    msg = ToolMessage(content="# 404 Not Found", tool_call_id="tc-1", additional_kwargs={})

    assert _meta(normalize_tool_message(msg)) == _SUCCESS
