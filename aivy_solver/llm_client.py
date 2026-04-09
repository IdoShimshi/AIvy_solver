import re

from litellm import acompletion

from aivy_solver.config import Config


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
) -> str:
    response = await acompletion(
        model=config.model,
        messages=messages,
        temperature=config.temperature,
    )
    return response.choices[0].message.content or ""
