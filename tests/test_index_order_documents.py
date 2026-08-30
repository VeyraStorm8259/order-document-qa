import json

from order_doc_qa import index_order_documents


class FakeIndexClient:
    def __init__(self) -> None:
        self.upserted = None

    def embed(self, texts):
        assert texts == ["Packed and shipped."]
        return [[0.2, 0.8]]

    def upsert(self, collection, vectors):
        self.upserted = (collection, vectors)


def test_index_uses_preprovisioned_collection(tmp_path, monkeypatch) -> None:
    path = tmp_path / "documents.json"
    path.write_text(json.dumps([{"order_id": "ord-1", "stage": "fulfillment", "text": "Packed and shipped."}]))
    client = FakeIndexClient()
    monkeypatch.setenv("INFRAI_COLLECTION", "existing-orders")
    monkeypatch.setattr(index_order_documents, "InfraiClient", lambda: client)

    index_order_documents.index_documents(path)

    collection, vectors = client.upserted
    assert collection == "existing-orders"
    assert vectors[0]["values"] == [0.2, 0.8]
    assert vectors[0]["metadata"]["order_id"] == "ord-1"
