# RoleStream

RoleStream is a search and Q&A system over live job postings. It pulls openings from the public Greenhouse, Lever and Ashby APIs, streams every change through Kafka, and lets you ask questions like "which companies are hiring data engineers?" and get an answer with citations back to the actual postings.

I built it solo, mostly to learn how a streaming pipeline and a RAG system fit together, and to find out how bad retrieval gets when the data is messy real-world job text. The answer turned out to be "bad in specific, fixable ways", which is most of what the rest of this README is about.

## How it works

```
Greenhouse / Lever / Ashby APIs
        |
     pollers  -->  Postgres
                      |
                  Debezium (CDC)
                      |
              Kafka: rolestream.public.postings
                      |
              Go consumer (chunking)
                      |
              embedding service  -->  Qdrant (44,577 chunks)
                                          |
                          FastAPI /query (hybrid retrieval)
                                          |
                                Ollama, llama3.2:3b
```

- **Pollers** (Python) hit the three job board APIs and write postings to Postgres.
- **Debezium** watches Postgres and publishes row changes to Kafka, so nothing downstream has to poll the database.
- **The Go consumer** reads the topic, splits each posting into chunks, and sends them to the embedding service.
- **The embedding service** produces a dense vector (`all-MiniLM-L6-v2`) and a sparse BM25 vector (fastembed) for each chunk. Both go into Qdrant.
- **The API** embeds the question, runs a hybrid search in Qdrant (dense and sparse results merged with reciprocal rank fusion), and hands the top chunks to a local `llama3.2:3b` model through Ollama. The model is told to answer only from those chunks and cite them.

Everything runs locally. Postgres, Kafka, Debezium and Qdrant are in `docker-compose.yml`. The embedding service, Ollama and the API run directly on the machine.

## Running it

Start the containers:

```bash
docker compose up -d
```

Then three terminals:

```bash
# embedding service
cd embedding && uvicorn service:app --port 8001

# local model
ollama serve

# API
cd api && uvicorn main:app --port 8000
```

Ask a question:

```bash
curl -s -X POST localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Which roles mention Kubernetes?"}'
```

The first request after starting Ollama is slow because the model has to load. After that it's a few seconds per question.

## Evaluating it

I wrote 55 questions (`docs/run_golden_questions.py`) covering language and tool lookups, company-specific questions, comparisons between two companies, salary questions, and a group of questions that should be refused: a "Chief Vibes Officer" role, COBOL developers, a "Time Travel Consultant", and so on. `docs/run_ragas_eval.py` runs them through the API and scores the answers with RAGAS v0.4.3, using Claude Haiku as the judge. It's reference-free, so there are no hand-written gold answers, only the question, the retrieved chunks and the response.

| Version | Faithfulness | Answer relevancy |
|---|---|---|
| First baseline | 0.76 | 0.60 |
| After adding the "no dates in the data" rule | 0.789 | 0.578 |
| Cross-company retrieval + query rewriter | **0.805** | **0.668** |

All three rows after the first are n=55 with nothing dropped. Judge noise on a run like this is around 0.03, so the faithfulness gain from the last change is within noise. The relevancy gain (+0.09) is not.

I also track context precision, but I don't trust it with this judge and I'm not reporting it.

### What changed the numbers

**A prompt rule about dates.** The chunks have no posting dates, but the model kept answering "what was posted this week?" anyway. Telling it explicitly that dates aren't in the data and to say so took faithfulness from 0.653 to 0.789 on that run.

**Citing company and title, not just numbers.** Early answers were things like "[1], [3] and [5]", which is useless to read and hard to verify. The prompt now requires the company and job title next to each citation.

**Removing duplicate chunks.** The same role is often posted several times. I dedupe by posting ID and again by exact chunk text, otherwise one posting can fill the whole context window.

**Per-company retrieval for comparisons.** "Compare backend roles at Stripe and ClickHouse" used to return chunks from whichever company matched the query better. The API now pulls the company names out of the question and runs a separate filtered search for each one, so both show up.

**A query rewriter.** Hybrid search works better on "data engineer" than on "Which companies are hiring for data engineer roles?". The rewriter strips question words and generic filler like "roles", "hiring" and "postings" before embedding. It's a plain word list, not an LLM call, so it's fast and can't invent terms. If only one very short word is left, it falls back to the original question.

### What didn't work

I tried a prompt that told the model to restate the question, put one role per line, and only list a role if its chunk explicitly mentioned the topic. On paper it should have helped relevancy. Instead faithfulness dropped to about 0.76 and relevancy to about 0.64, and answers got long enough that more questions timed out during the golden run (8 failures on the first pass, versus 2 before). I reverted it. Two other runs of that experiment were thrown out because the judge hit timeouts and an empty credit balance and dropped rows, so the comparison above rests on one run with 1 to 3 dropped rows per metric. The gap was bigger than the dropped rows could explain, but it's not as clean as I'd like.

## Known limitations

- **Short ambiguous words break retrieval.** Searching for "Go" matches the word "Go-To-Market" in a pile of sales postings, and the 3B model then happily lists them as Go jobs. Neither the dense model nor BM25 can tell the language from the word. Searching "Golang" works better. I left this alone instead of special-casing one token.
- **The 3B model has a ceiling.** It sometimes blurs two companies into one sentence, and it pads answers with weak matches when the retrieved chunks are poor.
- **RAGAS penalizes correct refusals.** When the right answer is "there is no COBOL role in the data", faithfulness and relevancy both score it near zero. The refusal questions are in the 55, so they pull both averages down. I haven't split them out yet.
- **I tuned on the same 55 questions I score on.** Some of the improvement is probably fitting to that set. A held-out set is on the to-do list.
- **One Anthropic "evergreen role" chunk shows up for unrelated queries.** It's boilerplate that should be stripped at chunking time, which means re-embedding everything, so it's not done.
- **Aggregate questions don't work.** "Which companies have the most open roles?" needs a count, and RAG can't count. This should go to SQL against Postgres.

## What's next

- Split refusal questions out of the RAGAS averages and report refusal accuracy separately.
- Add recall@5 on a hand-labeled set of questions, so retrieval has a deterministic metric that doesn't depend on a judge model.
- A cross-encoder reranker over the top 20 hybrid results, to cut down on weak chunks in the context.
- Try a larger generator (8B local, or Haiku) and compare against the 3B model.
- Prometheus and Grafana for latency and error rates, plus a load test.
- A simple web frontend and a demo video.

Relevancy at 0.668 is the number I most want to move. My target is 0.80, and I expect the reranker and a better model to matter more than further prompt changes.

## Layout

```
pollers/      Greenhouse, Lever and Ashby pollers
consumer/     Go Kafka consumer and chunker
embedding/    dense + sparse embedding service
api/          FastAPI service (retrieval, query rewriting, generation)
debezium/     connector config
schema/       Postgres schema
docs/         golden questions, RAGAS scripts, saved results
```
