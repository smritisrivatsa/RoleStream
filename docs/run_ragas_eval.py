import json
from langchain_anthropic import ChatAnthropic
from ragas.llms import LangchainLLMWrapper
from ragas.dataset_schema import SingleTurnSample, EvaluationDataset
from ragas.metrics import Faithfulness, LLMContextPrecisionWithoutReference, ResponseRelevancy
from ragas import evaluate
from langchain_huggingface import HuggingFaceEmbeddings
from ragas.embeddings import LangchainEmbeddingsWrapper

INPUT_FILE = "golden_results.json"
OUTPUT_FILE = "ragas_scores.json"

claude_llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)
evaluator_llm = LangchainLLMWrapper(claude_llm)
local_embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
evaluator_embeddings = LangchainEmbeddingsWrapper(local_embeddings)


def load_samples():
    with open(INPUT_FILE) as f:
        raw_results = json.load(f)

    samples = []
    for entry in raw_results:
        result = entry.get("result", {})
        answer = result.get("answer")
        sources = result.get("sources", [])

        # Skip entries that errored out (e.g. services weren't running)
        if not answer or "error" in result:
            continue

        # RAGAS needs the actual retrieved text, not just metadata —
        # your /query response only returns metadata in "sources", so we
        # reconstruct a reasonable context string from what's available.
        contexts = [s.get("text") for s in sources if s.get("text")]

        samples.append(
            SingleTurnSample(
                user_input=entry["question"],
                response=answer,
                retrieved_contexts=contexts if contexts else ["No context retrieved"],
            )
        )
    return samples


def run():
    samples = load_samples()
    print(f"Loaded {len(samples)} valid samples for evaluation")

    dataset = EvaluationDataset(samples=samples)

    result = evaluate(
        dataset=dataset,
        metrics=[Faithfulness(), LLMContextPrecisionWithoutReference(), ResponseRelevancy()],
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
    )

    print(result)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(result.to_pandas().to_dict(orient="records"), f, indent=2)

    print(f"\nDetailed scores saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    run()