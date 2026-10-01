import os
from langchain_anthropic import ChatAnthropic
from ragas.llms import LangchainLLMWrapper
from ragas.dataset_schema import SingleTurnSample
from ragas.metrics import Faithfulness
import asyncio

claude_llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)
evaluator_llm = LangchainLLMWrapper(claude_llm)

# A single test case, using one of your real golden results
sample = SingleTurnSample(
    user_input="Is Hightouch currently hiring?",
    response="Yes, Hightouch is currently hiring for the position of Backend Engineer, Platform.",
    retrieved_contexts=[
        "Hightouch | Backend Engineer, Platform | The Role: ..."
    ],
)

async def main():
    scorer = Faithfulness(llm=evaluator_llm)
    score = await scorer.single_turn_ascore(sample)
    print(f"Faithfulness score: {score}")

if __name__ == "__main__":
    asyncio.run(main())