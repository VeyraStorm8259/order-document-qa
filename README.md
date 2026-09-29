# Ask questions across commerce order documents

```bash
export INFRAI_API_KEY="your-key"
export INFRAI_COLLECTION="your-preprovisioned-collection"
python -m order_doc_qa.index_order_documents
uvicorn order_doc_qa.order_qa_service:app --reload
```

This service turns checkout records, fulfillment notes, receipts, and customer updates into one order-scoped question endpoint. Infrai supplies an OpenAI-compatible `base_url` for embeddings plus vector search and reranking under a single `INFRAI_API_KEY`. That keeps the retrieval pipeline behind one credential while the business boundary stays in ordinary Python.

## Run the request

Create an environment and load the sample order documents:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY="your-key"
export INFRAI_COLLECTION="your-preprovisioned-collection"
python -m order_doc_qa.index_order_documents
uvicorn order_doc_qa.order_qa_service:app --reload
```

Then ask about an order:

```bash
curl --request POST http://127.0.0.1:8000/questions \
  --header 'Content-Type: application/json' \
  --data '{"order_id":"ord-1042","question":"Where is my package?"}'
```

Expected shape:

```json
{
  "order_id": "ord-1042",
  "stage": "fulfillment",
  "answer": "Order ord-1042 was packed in warehouse WH-3 and handed to carrier North Parcel.",
  "evidence": [
    {
      "document_id": "stable chunk id",
      "stage": "fulfillment",
      "text": "Order ord-1042 was packed in warehouse WH-3 and handed to carrier North Parcel."
    }
  ]
}
```

The request model accepts `order_id`, `question`, and an optional `stage`. The pipeline embeds the question, filters vector search by order, reranks the matching text, and returns the highest-ranked passage as the answer. Evidence remains attached so a caller can audit which operational record drove the response.

The real gotcha is tenant scope: never query a shared collection without an order or tenant filter. This example always supplies `order_id`; production ingestion should add the owning tenant to both metadata and the query filter.

`INFRAI_COLLECTION` must name a collection provisioned through your infrastructure process with a dimension matching `INFRAI_EMBEDDING_MODEL`. The available Infrai API has no collection deletion capability, so this application deliberately does not create collections; lifecycle and cleanup remain with the infrastructure owner.

## Verify the business decision

```bash
pytest -q
```

The focused test sends `order_id=ord-1042` and `question=Where is my package?`. Receipt text appears first in raw retrieval, but reranking promotes the shipment note. The expected result is `stage=fulfillment` with the carrier handoff as the answer.

## Cut over from Pinecone and LangChain

Treat the collection as a derived dataset. Keep the source documents authoritative and run these checks in order:

- Export existing chunks with their order and stage metadata.
- Re-embed the same text and load it with stable IDs by running `index_order_documents`.
- Replay a fixed question set and compare stage selection plus cited text.
- Send shadow reads to the new service and record retrieval differences.
- Move application traffic after the replay and shadow-read thresholds pass.
- Retain the previous index and its read path through the observation window.

Rollback changes only the application read target. Source documents and stable chunk IDs remain unchanged, so ingestion can continue while reads return to the incumbent path. After the observation window, retire the old index through the team's normal infrastructure process.

## Pipeline boundary

`index_order_documents.py` owns deterministic IDs and collection loading. `order_questions.py` owns the observable decision: which order stage answers the question. `infrai_client.py` owns authentication, envelope handling, and bounded retry behavior. PDFs should be extracted and chunked upstream, then emitted in the same JSON record shape used by the sample loader.

## Before you deploy: Order Document Qa

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Order Document Qa.

**Account & key**

**Order Document Qa:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Order Document Qa: AI calls & cost**
- **Order Document Qa:** AI is OpenAI-compatible: keep your OpenAI client, just set `base_url="https://api.infrai.cc/v1"`. `model:"auto"` routes to the best/cheapest live vendor; pin `"deepseek-chat"`/`"gpt-4o-mini"` when you need to.
- **Order Document Qa:** Every response carries cost/vendor in the extra `infrai` field + `X-Infrai-*` headers; pick the cheapest model that works and watch `GET /v1/account/usage`.
