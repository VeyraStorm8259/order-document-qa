from order_doc_qa.order_questions import QuestionRequest, answer_order_question


class FakeRetrievalClient:
    def embed(self, texts: list[str]) -> list[list[float]]:
        assert texts == ["Where is my package?"]
        return [[0.2, 0.8]]

    def query(self, collection, embedding, top_k, document_filter=None):
        assert document_filter == {"order_id": "ord-1042"}
        return {
            "matches": [
                {"id": "receipt-1", "metadata": {"stage": "receipt", "text": "Receipt rcpt-8817 was emailed."}},
                {"id": "ship-1", "metadata": {"stage": "fulfillment", "text": "The package was handed to North Parcel."}},
            ]
        }

    def rerank(self, query, candidates, top_k):
        assert query == "Where is my package?"
        return {"results": [{"index": 1}, {"index": 0}]}


def test_shipping_question_selects_fulfillment_evidence() -> None:
    result = answer_order_question(
        QuestionRequest(order_id="ord-1042", question="Where is my package?"),
        FakeRetrievalClient(),
    )

    assert result.stage == "fulfillment"
    assert result.answer == "The package was handed to North Parcel."
    assert [item.document_id for item in result.evidence] == ["ship-1", "receipt-1"]
