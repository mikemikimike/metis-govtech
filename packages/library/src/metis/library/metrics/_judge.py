import os


def _get_judge_model():
    from deepeval.models import GPTModel

    return GPTModel(
        model="gpt-4.1-mini",
        api_key=os.environ.get("OPENAI_API_KEY"),
    )
