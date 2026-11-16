"""
This extracts token counts without treating missing usage as zero.
"""

from typing import Any

from langchain_core.messages import AIMessage


def extract_usage(
    response: AIMessage,
    *,
    provider: str,
    requested_model: str,
) -> dict[str, Any]:
    usage = response.usage_metadata

    if usage is None:
        raise ValueError("Provider did not return token usage metadata")

    input_details = usage.get("input_token_details") or {}
    output_details = usage.get("output_token_details") or {}

    return {
        "provider": provider,
        "requested_model": requested_model,
        "reported_model": response.response_metadata.get("model_name"),
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "total_tokens": usage["total_tokens"],
        "cached_input_tokens": input_details.get("cache_read", 0),
        "reasoning_tokens": output_details.get("reasoning", 0),
    }