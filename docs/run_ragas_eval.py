import json
from langchain_anthropic import ChatAnthropic
from langchain_huggingface import HuggingFaceEmbeddings
from ragas import evaluate
from ragas.dataset_schema import SingleTurnSample, EvaluationDataset
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    Faithfulness,
    LLMContextPrecisionWithoutReference,
    ResponseRelevancy,
)
from ragas.run_config import RunConfig

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
        if not answer or "error" in result:
            continue
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
        run_config=RunConfig(timeout=300, max_workers=4, max_retries=5),
    )

    df = result.to_pandas()
    metric_cols = ["faithfulness", "llm_context_precision_without_reference", "answer_relevancy"]

    print("\n=== Scores (mean over non-NaN rows) ===")
    for col in metric_cols:
        valid = df[col].dropna()
        print(f"{col}: {valid.mean():.4f}  (n={len(valid)}, NaN/dropped={len(df) - len(valid)})")

    df.to_json(OUTPUT_FILE, orient="records", indent=2)
    print(f"\nDetailed scores saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    run()