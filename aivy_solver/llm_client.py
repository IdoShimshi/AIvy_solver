import asyncio
import logging
import random
import re
from dataclasses import dataclass, field
from typing import Any

import litellm
from litellm import acompletion

from aivy_solver.config import Config

log = logging.getLogger(__name__)


_TRANSIENT_ERRORS: tuple[type[BaseException], ...] = tuple(
    cls for cls in (
        getattr(litellm, "APIError", None),
        getattr(litellm, "APIConnectionError", None),
        getattr(litellm, "Timeout", None),
        getattr(litellm, "RateLimitError", None),
        getattr(litellm, "ServiceUnavailableError", None),
        getattr(litellm, "InternalServerError", None),
    ) if cls is not None
)


@dataclass
class LLMResponse:
    content: str
    reasoning: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


def extract_invariants(reply: str) -> str:
    for tag in ("```ivy", "```"):
        start = reply.find(tag)
        if start != -1:
            code_start = start + len(tag)
            end = reply.find("```", code_start)
            if end != -1:
                return reply[code_start:end].strip()

    answer_match = re.search(r"<answer>(.*?)</answer>", reply, re.DOTALL)
    if answer_match:
        return answer_match.group(1).strip()

    return reply.strip()


async def _acompletion_with_retries(
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    rate_limit_base_delay: float = 8.0,
    **kwargs: Any,
) -> Any:
    """Call litellm.acompletion, retrying transient API errors with backoff.

    Handles the well-known OpenRouter empty-response / JSONDecodeError pattern,
    network blips, 5xx errors, and rate limits. Non-transient errors (auth,
    bad request, context-window) propagate immediately.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return await acompletion(**kwargs)
        except _TRANSIENT_ERRORS as exc:
            last_exc = exc
            if attempt >= max_retries:
                log.error(
                    "LLM call exhausted %d retries; last error %s: %s",
                    max_retries, type(exc).__name__, str(exc)[:300],
                )
                raise
            is_rate_limit = isinstance(
                exc, getattr(litellm, "RateLimitError", ())
            )
            base = rate_limit_base_delay if is_rate_limit else base_delay
            wait = base * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            log.warning(
                "LLM call attempt %d/%d failed with %s: %s — retrying in %.1fs",
                attempt, max_retries, type(exc).__name__, str(exc)[:200], wait,
            )
            await asyncio.sleep(wait)
    assert last_exc is not None
    raise last_exc


async def llm_complete(
    messages: list[dict[str, str]],
    config: Config,
) -> LLMResponse:
    response = await _acompletion_with_retries(
        model=config.model,
        messages=messages,
        temperature=config.temperature,
        reasoning_effort=config.reasoning_effort,
        allowed_openai_params=["reasoning_effort"],
    )

    message = response.choices[0].message
    content = message.content or ""
    reasoning = getattr(message, "reasoning_content", None)

    return LLMResponse(
        content=content,
        reasoning=reasoning,
        usage=response.usage.model_dump(),
    )
