from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Literal

try:
    from pydantic import BaseModel, Field
except ModuleNotFoundError:  # Keep model-only usage working in the minimal test environment.
    class _Field:
        def __init__(self, *, min_length: int | None = None) -> None:
            self.min_length = min_length

    def Field(*, min_length: int | None = None) -> _Field:
        return _Field(min_length=min_length)

    class BaseModel:
        def __init__(self, **values: Any) -> None:
            annotations = getattr(type(self), "__annotations__", {})
            for name, annotation in annotations.items():
                value = values.get(name)
                default = getattr(type(self), name, None)
                if isinstance(default, _Field):
                    if value is None or (default.min_length and len(value) < default.min_length):
                        raise ValueError(f"{name} is too short")
                elif value is None and default is not None:
                    raise ValueError(f"{name} is required")
                setattr(self, name, value)

if TYPE_CHECKING:
    from .infrai_client import InfraiClient


OrderStage = Literal["checkout", "fulfillment", "receipt", "customer_update"]


class QuestionRequest(BaseModel):
    order_id: str = Field(min_length=1)
    question: str = Field(min_length=3)
    stage: OrderStage | None = None


class Evidence(BaseModel):
    document_id: str
    stage: OrderStage
    text: str


class QuestionResponse(BaseModel):
    order_id: str
    stage: OrderStage
    answer: str
    evidence: list[Evidence]


def answer_order_question(request: QuestionRequest, client: InfraiClient) -> QuestionResponse:
    query_vector = client.embed([request.question])[0]
    document_filter: dict[str, Any] = {"order_id": request.order_id}
    if request.stage:
        document_filter["stage"] = request.stage

    result = client.query(
        collection=os.environ.get("INFRAI_COLLECTION", "commerce-order-documents"),
        embedding=query_vector,
        top_k=8,
        document_filter=document_filter,
    )
    matches = result.get("matches", [])
    candidates = [str(match["metadata"]["text"]) for match in matches]
    if not candidates:
        stage: OrderStage = request.stage or "customer_update"
        return QuestionResponse(
            order_id=request.order_id,
            stage=stage,
            answer="No matching order document was found.",
            evidence=[],
        )

    reranked = client.rerank(request.question, candidates, top_k=min(3, len(candidates)))
    ranked_items = reranked.get("results", reranked.get("data", []))
    ranked_indexes = [int(item["index"]) for item in ranked_items]
    selected = [matches[index] for index in ranked_indexes]
    evidence = [
        Evidence(
            document_id=str(match["id"]),
            stage=match["metadata"]["stage"],
            text=str(match["metadata"]["text"]),
        )
        for match in selected
    ]
    return QuestionResponse(
        order_id=request.order_id,
        stage=evidence[0].stage,
        answer=evidence[0].text,
        evidence=evidence,
    )
