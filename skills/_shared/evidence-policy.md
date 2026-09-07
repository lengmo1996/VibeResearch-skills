# Evidence Policy

Maintain an internal ledger whenever retrieval or source verification affects claims:

```json
{"claim_id":"C01","claim":"...","evidence_type":"direct|partial|contradictory|background","source_origin":"user_file|project_file|rag|inference","title":"...","document_id":"...","chunk_id":"...","page_numbers":[],"text":"...","support_strength":"high|medium|low","caveat":null}
```

- Relevance is not support. Distinguish direct, partial, contradictory, and background evidence.
- Do not infer a full-paper conclusion from an abstract. Inspect complete chunks for numbers and formulas.
- Never invent authors, DOI, citation keys, pages, IDs, formulas, tables, or values.
- Report contradictory evidence. Label all inference.
- Zero hits means only: `未在当前 KnowledgeHub 中检索到足够证据`.
- Use compact visible markers where useful: `[Title | document_id | chunk_id | pp. 3–4]`.
- If no RAG is used, cite user/project locations when available and omit empty fake ledgers.
