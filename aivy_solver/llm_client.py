import logging
import re
from dataclasses import dataclass, field
from typing import Any

import litellm
from litellm import acompletion

from aivy_solver.config import Config

log = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    content: str
    reasoning: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


def extract_ivy_code(reply: str) -> str:
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

    if reply.strip().startswith("#lang ivy"):
        return reply.strip()

    return reply.strip()


async def llm_complete(
    messages: list[dict[str, str]],
    config: Config,
) -> LLMResponse:
    response = await acompletion(
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
