from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .infrai_client import InfraiClient


def stable_chunk_id(document: dict[str, Any]) -> str:
    identity = f"{document['order_id']}:{document['stage']}:{document['text']}"
    return hashlib.sha256(identity.encode()).hexdigest()


def index_documents(path: Path) -> None:
    documents = json.loads(path.read_text())
    client = InfraiClient()
    texts = [document["text"] for document in documents]
    embeddings = client.embed(texts)
    collection = os.environ["INFRAI_COLLECTION"]
    vectors = [
        {
            "id": stable_chunk_id(document),
            "values": embedding,
            "metadata": {
                "order_id": document["order_id"],
                "stage": document["stage"],
                "text": document["text"],
            },
        }
        for document, embedding in zip(documents, embeddings, strict=True)
    ]
    client.upsert(collection, vectors)
    print(f"Indexed {len(vectors)} order document chunks into {collection}.")


if __name__ == "__main__":
    index_documents(Path(os.environ.get("ORDER_DOCUMENTS", "sample_order_documents.json")))
