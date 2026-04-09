import logging
import re

from aivy_solver.config import Config
from aivy_solver.ivy_checker import check_ivy
from aivy_solver.llm_client import llm_complete, extract_ivy_code
from aivy_solver.problem import Problem
from aivy_solver.prompts import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    RETRY_PROMPT_TEMPLATE,
    EMPTY_RESPONSE_FEEDBACK,
    MODIFIED_LINES_FEEDBACK,
)
from aivy_solver.results import AttemptRecord, ProblemResult, RunResult

log = logging.getLogger(__name__)


def _normalize(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())


def _check_no_cheating(original: str, candidate: str) -> bool:
    orig_lines = [
        _normalize(l) for l in original.splitlines()
        if l.strip() and not l.strip().startswith("invariant")
    ]
    cand_lines = [
        _normalize(l) for l in candidate.splitlines()
        if l.strip() and not l.strip().startswith("invariant")
    ]

    if orig_lines == cand_lines:
        return False

    orig_idx = 0
    for cand_line in cand_lines:
        if orig_idx < len(orig_lines) and cand_line == orig_lines[orig_idx]:
            orig_idx += 1
    if orig_idx == len(orig_lines):
        return False

    for i, (o, c) in enumerate(zip(orig_lines, cand_lines)):
        if o != c:
            log.debug("  first diff at non-invariant line %d:\n    orig: %s\n    cand: %s", i, o, c)
            break

    return True


async def solve_problem(problem: Problem, config: Config) -> ProblemResult:
    log.info("Solving %s with %s (max %d attempts)", problem.name, config.model, config.max_attempts)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(stripped_program=problem.stripped)},
    ]

    attempts: list[AttemptRecord] = []

    for attempt_num in range(1, config.max_attempts + 1):
        log.info("  [%s] attempt %d/%d", problem.name, attempt_num, config.max_attempts)

        raw_reply = await llm_complete(messages, config)
        candidate = extract_ivy_code(raw_reply)

        if not candidate or not candidate.strip():
            messages.append({"role": "assistant", "content": raw_reply})
            messages.append({"role": "user", "content": EMPTY_RESPONSE_FEEDBACK})
            attempts.append(AttemptRecord(attempt=attempt_num, passed=False, ivy_output="empty response", llm_solution=""))
            continue

        if _check_no_cheating(problem.stripped, candidate):
            messages.append({"role": "assistant", "content": raw_reply})
            messages.append({"role": "user", "content": MODIFIED_LINES_FEEDBACK})
            attempts.append(AttemptRecord(attempt=attempt_num, passed=False, ivy_output=MODIFIED_LINES_FEEDBACK, llm_solution=candidate))
            log.info("  [%s] attempt %d: modified existing lines", problem.name, attempt_num)
            continue

        result = await check_ivy(candidate, ivy_check_cmd=config.ivy_check_command, timeout=config.ivy_check_timeout)

        if result.passed:
            messages.append({"role": "assistant", "content": raw_reply})
            attempts.append(AttemptRecord(attempt=attempt_num, passed=True, ivy_output=result.raw_output, llm_solution=candidate))
            log.info("  [%s] PASSED on attempt %d", problem.name, attempt_num)
            return ProblemResult(
                problem_name=problem.name,
                model=config.model,
                success=True,
                success_on_attempt=attempt_num,
                total_attempts=attempt_num,
                attempts=attempts,
            )

        reason = "timed out" if result.timed_out else "ivy_check failed"
        log.info("  [%s] attempt %d: %s", problem.name, attempt_num, reason)
        messages.append({"role": "assistant", "content": raw_reply})
        messages.append({"role": "user", "content": RETRY_PROMPT_TEMPLATE.format(error_output=result.feedback)})
        attempts.append(AttemptRecord(attempt=attempt_num, passed=False, ivy_output=result.raw_output, llm_solution=candidate))

    log.info("  [%s] FAILED after %d attempts", problem.name, config.max_attempts)
    return ProblemResult(
        problem_name=problem.name,
        model=config.model,
        success=False,
        success_on_attempt=None,
        total_attempts=config.max_attempts,
        attempts=attempts,
    )


async def run_benchmark(problems: list[Problem], config: Config) -> RunResult:
    log.info("Loaded %d problem(s), model=%s, max_attempts=%d", len(problems), config.model, config.max_attempts)

    run = RunResult(model=config.model)
    for problem in problems:
        result = await solve_problem(problem, config)
        run.problems.append(result)

    log.info(
        "Run complete: %d/%d passed (%.0f%%)",
        sum(1 for p in run.problems if p.success),
        len(run.problems),
        run.success_rate * 100,
    )
    return run
