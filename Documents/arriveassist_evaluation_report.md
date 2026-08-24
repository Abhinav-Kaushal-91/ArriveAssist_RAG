# ArriveAssist â€” Evaluation Report

## 1. Project Summary

**One-liner:** ArriveAssist helps newcomers and new Canadian citizens
answer settlement and citizenship-process questions from official IRCC,
Service Canada, and OHIP guides, with a target of high faithfulness and
correctness.

**Scope:** Canadian citizenship, OHIP (Ontario health coverage), and SIN
(Social Insurance Number). Explicitly out of scope: driver's licence
exchange, banking, student visas, taxes, employment, work visa travel,
and permanent residency applications.

**Stack:** n8n (orchestration) Â· Nebius/Qwen (embeddings + generation) Â·
Pinecone (vector store) Â· Cohere (reranking) Â· Streamlit (frontend).

---

## 2. Evaluation Methodology

### Golden set
40 hand-written questions across five categories:
- Straightforward single-topic lookups (citizenship, OHIP, SIN)
- Ambiguous or unusually phrased questions
- Cross-topic questions spanning two or more of the three subjects
- Out-of-scope questions that should trigger a refusal
- Questions deliberately targeting gaps in the source corpus ("known gap"
  and "likely gap" questions), where a correct answer is an honest
  refusal, not a guess

Each question has a written expected answer. Gap questions are marked
explicitly, so a refusal on those scores as a correct outcome rather than
a failure.

### Scoring approach
Rather than a full RAGAS/DeepEval installation (a separate Python
environment with no clear time-to-value gain for this project size), an
LLM-as-judge approach was implemented directly inside n8n, reusing the
existing Nebius credential:

1. A Code node holds the 40 records: question, expected answer, actual
   answer, and cited source
2. Each record is sent to a Nebius chat model with a dedicated judge
   system prompt, scoring **correctness** (does the answer match the
   expected content) and **faithfulness** (is the answer grounded, with
   no fabricated details, including in refusals)
3. Judge responses are parsed and averaged across all 40 questions

This mirrors RAGAS's methodology (faithfulness + correctness scoring
against ground truth) without the overhead of a separate evaluation
framework and environment.

---

## 3. Results Summary

| Metric | Score |
|---|---|
| Average correctness | 95% |
| Average faithfulness | 95% |
| Questions evaluated | 40 |

By category, qualitatively:
- **Straightforward lookups**: strong performance across citizenship,
  OHIP, and SIN
- **Numeric reasoning** (e.g. "I've been in Canada for 1,000/1,500 days â€”
  can I apply?"): correct in both directions, including precise arithmetic
  on the shortfall
- **Jurisdiction awareness** (e.g. Alberta health card, Nova Scotia
  reciprocity): correctly recognized as out of the corpus's coverage
  rather than answering as if OHIP applied everywhere
- **Out-of-scope refusals**: consistently correct across all tested cases
  (driver's licence, banking, taxes, employment, work visa travel,
  PR-on-student-visa)
- **Cross-topic questions**: correctly synthesized information from
  multiple source topics in a single answer

---

## 4. Failure Analysis

### 4.1 Source extraction: accordion-collapsed content
The IRCC "who can apply" citizenship page uses collapsible accordion
sections. Early PDF exports (browser print-to-PDF without expanding those
sections first) silently omitted content inside them â€” the page heading
and top-level structure printed fine, but detail hiding inside collapsed
panels (physical presence requirement, PR status guidance) did not. This
caused early "I don't have that information" failures on two questions
despite the source page genuinely covering both facts. **Fix**: re-print
with all sections expanded before re-ingesting. This resolved the
physical-presence question; see 4.2 for the related question that
persisted.

### 4.2 Retrieval-ranking gap
After the accordion fix, "How many days do I need to be physically
present" answered correctly, but "Can I lose my PR status while my
application is processed?" â€” a fact from the *same* re-ingested
document â€” continued to return "I don't have that information," even
with reranking enabled and top-k widened from 4 to 20. This narrows the
finding precisely: it is not an ingestion problem (the sibling fact in
the same document retrieves correctly), but a retrieval-ranking
limitation specific to this chunk. On closer reading, the underlying
question's exact framing ("lose status *during* processing") isn't
directly addressed by the source content either â€” the documents describe
confirming status *before* applying and note that review-related cases
may be suspended, which is adjacent but not identical. The system's
refusal here is faithful (no fabrication) but not optimal (it didn't
surface the closely related content that does exist).

### 4.3 Retrieval non-determinism
"Do I need to file taxes before applying for citizenship?" returned a
correct, sourced answer in an earlier run and "I don't have that
information" in a later run of the identical question, with no changes
made to the ingested content in between. This indicates the retrieval
pipeline (vector search plus reranking) is not fully deterministic run to
run â€” a materially different finding from a static content gap, and one
worth flagging for anyone building on top of this pattern.

### 4.4 Citation fabrication
On the out-of-scope "find a job in Ontario" refusal, the system correctly
declined to help but appended a specific-looking redirect URL
(`ontario.ca/page/find-job`) that does not exist (confirmed 404). The
correct page is `ontario.ca/page/employment-ontario`. This shows the
refusal-path system message did not originally constrain link generation
during refusals â€” only during in-scope answers. **Fix applied**: added an
explicit rule prohibiting invented URLs in refusal responses.

### 4.5 Citation mis-attribution (distinct from fabrication)
Several answers cited real, topically correct, official government pages
that were not among the specific pages ingested â€” for example, a SIN
"hub" landing page that itself links to the actual ingested sub-pages, and
an older, parallel IRCC URL covering the same citizenship eligibility
content as the page that was actually ingested. Unlike 4.4, these are not
inventions â€” they are real, relevant pages, most plausibly picked up from
cross-reference links embedded in the ingested PDFs' visible text. This is
a meaningfully less severe failure mode than fabrication: a user clicking
the link still lands on correct, official information, just not the exact
source page the fact was drawn from.

### 4.6 Correctly identified gaps
Several questions were deliberately chosen to test corpus gaps: losing an
OHIP card, SIN rejection affecting citizenship, and reciprocal coverage
for a Nova Scotia health card in Ontario. All three correctly returned an
honest refusal rather than a fabricated answer, matching the expected
"known gap" behavior defined in the golden set.

### 4.7 Observed strengths
- Correct, precise arithmetic on physical-presence day counts in both
  directions (above and below the 1,095-day threshold)
- Jurisdiction-aware refusal on the Alberta health card question, rather
  than incorrectly applying Ontario-specific OHIP rules
- Coherent multi-topic synthesis on the "new permanent resident" question,
  correctly sequencing SIN, OHIP, and citizenship guidance in one answer

---

## 5. Mitigations Applied During This Build

- Re-ingested citizenship source pages with accordion sections expanded
- Added Cohere reranking on top of initial dense retrieval, widening
  top-k from 4 to 20 candidates pre-rerank
- Refined the AI Agent's system message to prohibit fabricated URLs in
  refusal responses specifically, not just in-scope answers
- Restricted source citations to genuine, well-formed URLs only,
  omitting the citation line entirely otherwise

---

## 6. Remaining Limitations and Future Work

- **Hybrid (dense + sparse) retrieval** is the most direct next step for
  the ranking gap in 4.2 â€” exact keyword overlap via a sparse/BM25
  component would likely surface chunks that dense similarity alone
  missed. Scoped out of this build due to the setup cost (new index
  metric, no native n8n sparse-encoding node, full re-ingestion).
- **Retrieval determinism** was not investigated further within this
  build; documenting its existence (4.3) is the primary output for now.
- **Citation mis-attribution** (4.5) could be reduced by stripping
  embedded cross-reference links from source PDFs before chunking, or by
  attaching stronger per-chunk metadata than a single filename/URL.
- Coverage is Ontario-only; other provinces and additional topics
  (driver's licence, banking) are natural v2 extensions, each requiring
  their own sourcing and scoping work.

---

## 7. Related Deliverables

- `golden_set.md` â€” the 40-question golden set with expected answers
- `judge_prompt.md` â€” the LLM-judge scoring prompt
- `golden_set_scoring_array.js` â€” the compiled input data for the eval run
- `arriveassist_solution_kit.md` â€” architecture, node roster, and prompt
  library
- `arriveassist_prd.md` â€” product requirements
- n8n workflow exports (ingestion, query, eval)

