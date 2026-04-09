import logging

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


def _check_no_cheating(original: str, candidate: str) -> bool:
    return _non_invariant_lines(original) != _non_invariant_lines(candidate)


def _non_invariant_lines(program: str) -> list[str]:
    lines = []
    for line in program.splitlines():
        stripped = line.strip()
        if stripped.startswith("invariant") and not stripped.startswith("invariant [safety]"):
            continue
        if stripped:
            lines.append(stripped)
    return lines


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

        attempts.append(AttemptRecord(
            attempt=attempt_num,
            passed=result.passed,
            ivy_output=result.raw_output,
            llm_solution=candidate,
        ))

        if result.passed:
            log.info("  [%s] PASSED on attempt %d", problem.name, attempt_num)
            return ProblemResult(
                problem_name=problem.name,
                model=config.model,
                success=True,
                success_on_attempt=attempt_num,
                total_attempts=attempt_num,
                attempts=attempts,
            )

        log.info("  [%s] attempt %d FAILED: %s", problem.name, attempt_num, result.feedback[:120])
        messages.append({"role": "assistant", "content": raw_reply})
        messages.append({"role": "user", "content": RETRY_PROMPT_TEMPLATE.format(error_output=result.feedback)})

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
