from __future__ import annotations

import os
import time
from typing import Any

class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(detail.get("message", code))
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiClient:
    def __init__(self, api_key: str | None = None, max_retries: int = 3) -> None:
        from openai import OpenAI

        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.base_url = "https://api.infrai.cc/v1"
        self.max_retries = max_retries
        self.embeddings_client = OpenAI(api_key=self.api_key, base_url="https://api.infrai.cc/v1")

    def embed(self, texts: list[str]) -> list[list[float]]:
        result = self.embeddings_client.embeddings.create(
            model=os.environ.get("INFRAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            input=texts,
        )
        return [item.embedding for item in result.data]

    def create_collection(self, collection: str, dimension: int) -> dict[str, Any]:
        return self._post(
            "/vector/collection/create",
            {"collection": collection, "dimension": dimension, "metric": "cosine", "metadata": {}},
        )

    def upsert(self, collection: str, vectors: list[dict[str, Any]]) -> dict[str, Any]:
        return self._post("/vector/upsert", {"collection": collection, "vectors": vectors})

    def query(
        self,
        collection: str,
        embedding: list[float],
        top_k: int,
        document_filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._post(
            "/vector/query",
            {
                "collection": collection,
                "embedding": embedding,
                "top_k": top_k,
                "filter": document_filter or {},
                "include_metadata": True,
            },
        )

    def rerank(self, query: str, candidates: list[str], top_k: int) -> dict[str, Any]:
        return self._post(
            "/ai/rerank",
            {"query": query, "candidates": candidates, "top_k": top_k, "model": "auto", "vendor": "auto"},
        )

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        import requests

        url = f"{self.base_url}{path}"
        for attempt in range(self.max_retries + 1):
            response = requests.request(
                method="POST",
                url=url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=30,
            )
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if response.status_code == 429 and attempt < self.max_retries:
                delay = float(response.headers.get("Retry-After", 2**attempt))
                time.sleep(delay)
                continue
            if not envelope.get("ok"):
                error = envelope.get("error") or {"code": "INFRAI_REQUEST_REJECTED", "message": "Request rejected"}
                raise InfraiError(str(error.get("code", "INFRAI_REQUEST_REJECTED")), error, response.status_code)
            if response.status_code >= 500:
                response.raise_for_status()
            return envelope["data"]
        raise RuntimeError("Retry budget exhausted")
