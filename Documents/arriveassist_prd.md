# Product Requirements Document: ArriveAssist

**Tagline:** New to Canada? I am here to help.
**Status:** MVP built and evaluated
**Owner:** Abhi

---

## 1. Summary

ArriveAssist is a retrieval-augmented generation (RAG) chatbot that helps
newcomers to Ontario navigate three specific settlement tasks: applying for
Canadian citizenship, enrolling in OHIP (Ontario's health coverage), and
applying for a SIN (Social Insurance Number). It answers questions grounded
in official Government of Canada and Government of Ontario sources, and
explicitly declines to answer outside its scope rather than guessing.

## 2. Problem Statement

Newcomers settling in Ontario need to complete several time-sensitive,
document-heavy government processes in their first weeks â€” citizenship
eligibility tracking, health coverage enrollment, and SIN registration.
This information is spread across multiple government websites, each with
its own structure, and it's easy to miss a requirement or misunderstand
eligibility (e.g. physical presence day counts, which documents are
accepted). A focused assistant that answers only from verified official
sources reduces the risk of acting on incorrect or outdated advice found
elsewhere online.

## 3. Target Users

- New permanent residents in Ontario in their first months after arrival
- Newcomers actively tracking citizenship eligibility timelines
- Anyone with a specific procedural question about OHIP or SIN enrollment

## 4. Goals

- Give accurate, source-grounded answers on citizenship, OHIP, and SIN
- Correctly decline questions outside these three topics rather than
  answering from general knowledge
- Handle questions that span more than one topic (e.g. "what do I need to
  do for citizenship, OHIP, and my SIN as a new PR?")
- Be honest when the underlying documents don't cover something, rather
  than fabricating an answer

## 5. Scope

### In scope
- Canadian citizenship: eligibility criteria, application process, minor
  application types (5(1) vs 5(2))
- OHIP: eligibility, required documents, application process, coverage
  details
- SIN: application process, required documents, protecting your SIN,
  eligibility by immigration status

### Explicitly out of scope
- Driver's licence exchanges
- Opening a bank account
- Student visas / study permits
- Filing income taxes
- Job search / employment services
- Work visa travel and re-entry rules
- Permanent residency applications
- Health coverage from provinces other than Ontario

## 6. Functional Requirements

| ID | Requirement |
|----|-------------|
| F1 | User can ask a free-text question and receive a grounded answer |
| F2 | System retrieves relevant content from an indexed knowledge base before answering |
| F3 | System declines to answer questions outside the three supported topics |
| F4 | System declines rather than guesses when a question is in-scope but not covered by the source documents |
| F5 | User can start a new chat, clearing prior context |
| F6 | User can view and return to previous chat threads within a session |
| F7 | Landing page clearly states what the assistant can and can't help with before the user starts chatting |

## 7. Non-Functional Requirements

- Answers should cite a source where one is genuinely available from the
  retrieved content
- Response time should feel conversational (not require the user to wait
  more than a few seconds under normal conditions)
- The knowledge base should be easy to extend with additional topics later
  without rebuilding the whole system

## 8. Technical Architecture

- **Orchestration:** n8n (ingestion workflow + query workflow)
- **Embedding model:** Qwen3-Embedding-8B via Nebius
- **Vector store:** Pinecone (dense retrieval, cosine similarity)
- **Reranking:** Cohere Reranker, applied on top of initial vector search
- **Generation model:** Qwen chat model via Nebius
- **Frontend:** Streamlit (Python)
- **Source documents:** official canada.ca and ontario.ca pages, ingested
  as PDFs with source metadata attached per chunk

## 9. User Flow

1. User opens the app and sees the landing page (name, tagline, Do's and
   Don'ts)
2. User clicks "Let's Chat" to enter the chat interface
3. User types a question
4. System embeds the question, retrieves and reranks relevant chunks,
   generates an answer grounded in that content
5. Answer is displayed, with a source reference when one is available
6. User can continue the conversation, start a new chat, or revisit an
   earlier thread from the sidebar

## 10. Success Metrics

- **Correctness**: whether answers match verified source content
- **Faithfulness**: whether answers are grounded in retrieved content
  rather than the model's own general knowledge, and whether the system
  refuses appropriately when it lacks information
- Evaluated against a 40-question golden set spanning straightforward
  lookups, ambiguous phrasing, cross-topic questions, and out-of-scope
  refusals

## 11. Known Limitations (v1)

- Retrieval can occasionally miss a relevant fact even when the source
  document is correctly ingested, particularly when a document covers many
  distinct sub-topics in one page
- Citations sometimes reference a closely related official page (e.g. a
  topic hub page) rather than the exact page a fact was drawn from
- Answers to an identical question are not guaranteed to be fully
  consistent between runs
- Currently covers Ontario only; other provinces and topics (e.g. driver's
  licences, banking) are out of scope for v1

## 12. Future Considerations

- Hybrid (dense + sparse) retrieval to improve recall on fact-dense pages
- Additional topics (driver's licence, banking, taxes) as separate,
  clearly scoped extensions
- Persisted chat history across sessions, not just within a single run
- Automated regression testing against the golden set whenever the
  knowledge base or prompt changes

