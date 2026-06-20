# Explainability

How TrustShield provides transparent, grounded explanations for fraud decisions.

## Grounding Contract

The RAG (Retrieval-Augmented Generation) explainability system enforces a strict grounding contract:

1. **Context-only answers**: The LLM may only cite information present in the retrieved context. It must never invent risk factors, entities, or scores not in the context.
2. **Source citation**: Answers include `[S-session_id]` notation linking claims to specific sessions.
3. **Insufficient context**: When context is inadequate, the LLM explicitly says so rather than guessing.
4. **PII redaction**: All context and questions are redacted before LLM submission via `app.utils.pii.redact()`. The LLM never sees raw PII.

The system prompt (`app/services/explain/llm_service.py:SYSTEM_PROMPT`) encodes these rules and is non-overridable by user input.

## Provider Configuration

TrustShield supports two LLM backends, configured via `LLM_PROVIDER` env var:

### OpenRouter (default)
```env
LLM_PROVIDER=openrouter
LLM_API_KEY=sk-or-...
LLM_MODEL=meta-llama/llama-3.1-8b-instruct
LLM_TIMEOUT_SECONDS=10
```

Uses the OpenRouter API (`https://openrouter.ai/api/v1/chat/completions`). Suitable for production with managed infrastructure.

### Local (vLLM / Ollama)
```env
LLM_PROVIDER=local
LLM_BASE_URL=http://localhost:11434
LLM_MODEL=llama3.1:8b
LLM_TIMEOUT_SECONDS=30
```

Uses an OpenAI-compatible local endpoint. Suitable for development and air-gapped deployments.

### No LLM (template fallback)
When `LLM_API_KEY` is empty, the system falls back to template-based answers that summarize risk scores, attributions, and similar sessions without LLM generation.

## Evaluation Harness

RAG grounding quality is evaluated via `tests/evaluation/test_rag_grounding.py`:

```bash
# Run evaluation (requires OPENROUTER_API_KEY or local LLM)
RUN_RAG_EVAL=1 pytest tests/evaluation/ -v
```

The harness tests:
- **Groundedness**: LLM answers cite only retrieved context
- **Faithfulness**: No fabricated entities or scores
- **Relevance**: Answers address the actual question
- **Citation accuracy**: `[S-id]` references match real session IDs

Evaluation runs in CI only when secrets are available (gated by `RUN_RAG_EVAL=1`).

## PII Redaction Boundary

PII redaction happens at the `rag_chat.py` layer, before context reaches the LLM:

```
User query → redact() → LLM (sees redacted text) → answer → user
                    ↑
Context retrieval → redact() ↗
```

The `redact()` function masks:
- Phone numbers → `XXX...XX`
- Email addresses → `X...@domain`
- UPI VPA addresses → `X...@bank`
- Aadhaar numbers → `XXXX XXXX XXXX`

Redaction is applied to both the question and the context. The LLM never receives raw PII. Post-LLM, the answer is returned as-is (already safe since input was redacted).
