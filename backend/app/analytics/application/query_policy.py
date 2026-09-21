from typing import Protocol, runtime_checkable

from app.analytics.domain import QueryPolicyDecision, QueryPolicyRequest


@runtime_checkable
class QueryPolicy(Protocol):
    def evaluate(self, request: QueryPolicyRequest) -> QueryPolicyDecision: ...
