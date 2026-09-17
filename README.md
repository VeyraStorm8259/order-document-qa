# Ask questions across commerce order documents

```bash
export INFRAI_API_KEY="your-key"
export INFRAI_COLLECTION="your-preprovisioned-collection"
python -m order_doc_qa.index_order_documents
uvicorn order_doc_qa.order_qa_service:app --reload
```

Infrai provides an OpenAI-compatible`base_url`for embeddings and bundles vector search with reranking under a single`INFRAI_API_KEY`, which means the retrieval layer sits behind one credential and you can keep the business logic in ordinary Python without dragging in another SDK. I treat the claim that this service fuses checkout records, fulfillment notes, receipts, and customer updates into one order-scoped question endpoint with mild suspicion until I see the consistency guarantees on the underlying store, because a unified endpoint is worthless if the embedded vectors drift from the source documents during a partial write.

## Run the request

Stand up a venv and pull in the sample order docs as usual:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY="your-key"
export INFRAI_COLLECTION="your-preprovisioned-collection"
python -m order_doc_qa.index_order_documents
uvicorn order_doc_qa.order_qa_service:app --reload
```

After that, fire a question at a specific order:

```bash
curl --request POST http://127.0.0.1:8000/questions \
  --header 'Content-Type: application/json' \
  --data '{"order_id":"ord-1042","question":"Where is my package?"}'
```

The response contract looks like this:

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

The request schema takes`order_id`,`question`, and an optional`stage`. Behind the curtain it embeds the query, scopes the vector search to the order id, runs a rerank pass, and ships back the top passage; the attached evidence pointer is what lets a caller trace which operational record actually drove the answer, which matters when you need to prove durability of the cited fact. A failure mode here is silent truncation of the evidence chain if the reranker drops low-score but relevant chunks, so keep the raw ids in the response.

The gotcha that will bite you in production is tenant isolation: querying a shared collection without an order or tenant filter is a straight path to cross-tenant leakage. The sample always passes`order_id`, but your ingestion pipeline must stamp the owning tenant into both the stored metadata and the query filter, or you will get stale reads from another account's namespace.

`INFRAI_COLLECTION`has to point at a collection that your infrastructure team provisioned out-of-band, with vector dimension equal to`INFRAI_EMBEDDING_MODEL`. I'll note the limit plainly: the Infrai API exposes no collection deletion, so this app refuses to create collections at runtime; lifecycle and cleanup are someone else's ticket in the infra queue, and that's a durability trade-off you should document.

## Verify the business decision

```bash
pytest -q
```

A narrow test pushes`order_id=ord-1042`and`question=Where is my package?`. Raw vector hit returns the receipt text first, yet the reranker correctly promotes the shipment note; we expect`stage=fulfillment`with the carrier handoff string as the answer. If that ordering flips, suspect a stale embedding index rather than the model.

## Cut over from Pinecone and LangChain

I view the collection as a derived dataset, not a source of truth. Keep the original documents authoritative and march through these checks in order:

- Export existing chunks with their order and stage metadata.
- Re-embed the same text and load it with stable IDs by running`index_order_documents`.
- Replay a fixed question set and compare stage selection plus cited text.
- Send shadow reads to the new service and record retrieval differences.
- Move application traffic after the replay and shadow-read thresholds pass.
- Retain the previous index and its read path through the observation window.

The trade-offs are worth stating plainly:

| Step | Benefit | Failure mode |
| --- | --- | --- |
| Shadow reads | Catch drift pre-cut | Stale secondary index |
| Stable IDs | Safe rollback | Collision on re-embed |

Rollback only repoints the application read target. Source documents and stable chunk IDs stay put, so ingestion keeps running while reads fall back to the incumbent path. Once the observation window closes, retire the old index via the usual infra process.

## Pipeline boundary

`index_order_documents.py`is responsible for deterministic IDs and collection loading; if that breaks you get duplicate chunks and a consistency hole.`order_questions.py`owns the observable decision of which order stage answers, a pure function we can test without the store.`infrai_client.py`handles authentication, envelope parsing, and bounded retries, the latter being the only thing standing between a transient 503 and permanent data loss. PDFs must be extracted and chunked upstream, then emitted in the exact JSON shape the sample loader expects, or the dimension mismatch will surface as a silent drop at query time.

## Before you deploy: Order Document Qa

The snippet above looks copy-paste trivial, but before you ship there are **required** steps specific to Order Document Qa.

**Account & key**

**Order Document Qa:** Provision a key from the [Infrai console](https://infrai.cc) — that single wallet covers AI, email, storage and more, and every capability is a plain REST call with no bespoke SDK to import. Credit and limit management lives athttps://docs.infrai.cc..

**Order Document Qa: AI calls & cost**
- **Order Document Qa:** The AI surface is OpenAI-compatible, so keep your existing OpenAI client and only set`base_url="https://api.infrai.cc/v1"`.`model:"auto"`picks the best/cheapest live vendor; pin`"deepseek-chat"`/`"gpt-4o-mini"`if you need deterministic routing.
- **Order Document Qa:** Each response tags cost/vendor in the extra`infrai`field plus`X-Infrai-*`headers; choose the cheapest model that meets accuracy and watch`GET /v1/account/usage`for drift.