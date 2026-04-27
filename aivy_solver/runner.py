import asyncio
import logging
import re

from tqdm import tqdm

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

    attempts: list[AttemptRecord] = []

    log.info("  [%s] running ivy_check on stripped program", problem.name)
    baseline = await check_ivy(problem.stripped, ivy_check_cmd=config.ivy_check_command, timeout=config.ivy_check_timeout)

    if baseline.passed:
        log.info("  [%s] stripped program already verifies — PASSED on attempt 0", problem.name)
        attempts.append(AttemptRecord(
            attempt=0, passed=True,
            ivy_output=baseline.raw_output, llm_solution=problem.stripped,
        ))
        return ProblemResult(
            problem_name=problem.name,
            model=config.model,
            success=True,
            success_on_attempt=0,
            total_attempts=0,
            attempts=attempts,
        )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(
            stripped_program=problem.stripped,
            ivy_output=baseline.raw_output,
        )},
    ]

    for attempt_num in range(1, config.max_attempts + 1):
        log.info("  [%s] attempt %d/%d", problem.name, attempt_num, config.max_attempts)

        reply = await llm_complete(messages, config)
        raw_reply = reply.content
        candidate = extract_ivy_code(raw_reply)

        if not candidate or not candidate.strip():
            messages.append({"role": "assistant", "content": raw_reply})
            messages.append({"role": "user", "content": EMPTY_RESPONSE_FEEDBACK})
            attempts.append(AttemptRecord(
                attempt=attempt_num, passed=False,
                ivy_output="empty response", llm_solution="",
                reasoning=reply.reasoning, usage=reply.usage,
            ))
            continue

        if _check_no_cheating(problem.stripped, candidate):
            messages.append({"role": "assistant", "content": raw_reply})
            messages.append({"role": "user", "content": MODIFIED_LINES_FEEDBACK})
            attempts.append(AttemptRecord(
                attempt=attempt_num, passed=False,
                ivy_output=MODIFIED_LINES_FEEDBACK, llm_solution=candidate,
                reasoning=reply.reasoning, usage=reply.usage,
            ))
            log.info("  [%s] attempt %d: modified existing lines", problem.name, attempt_num)
            continue

        result = await check_ivy(candidate, ivy_check_cmd=config.ivy_check_command, timeout=config.ivy_check_timeout)

        if result.passed:
            messages.append({"role": "assistant", "content": raw_reply})
            attempts.append(AttemptRecord(
                attempt=attempt_num, passed=True,
                ivy_output=result.raw_output, llm_solution=candidate,
                reasoning=reply.reasoning, usage=reply.usage,
            ))
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
        attempts.append(AttemptRecord(
            attempt=attempt_num, passed=False,
            ivy_output=result.raw_output, llm_solution=candidate,
            reasoning=reply.reasoning, usage=reply.usage,
        ))

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
    concurrency = max(1, min(config.concurrency, len(problems))) if problems else 1
    log.info(
        "Loaded %d problem(s), model=%s, max_attempts=%d, concurrency=%d",
        len(problems), config.model, config.max_attempts, concurrency,
    )

    run = RunResult(model=config.model, reasoning_effort=config.reasoning_effort)

    aivy_logger = logging.getLogger("aivy_solver")
    use_progress_bar = (
        len(problems) > 1
        and concurrency > 1
        and aivy_logger.getEffectiveLevel() > logging.DEBUG
    )

    if concurrency == 1:
        for problem in problems:
            result = await solve_problem(problem, config)
            run.problems.append(result)
    else:
        semaphore = asyncio.Semaphore(concurrency)

        async def _bounded_solve(problem: Problem) -> ProblemResult:
            async with semaphore:
                return await solve_problem(problem, config)

        if use_progress_bar:
            run.problems.extend(await _gather_with_progress(problems, _bounded_solve, aivy_logger))
        else:
            results = await asyncio.gather(*(_bounded_solve(p) for p in problems))
            run.problems.extend(results)

    log.info(
        "Run complete: %d/%d passed (%.0f%%)",
        sum(1 for p in run.problems if p.success),
        len(run.problems),
        run.success_rate * 100,
    )
    return run


async def _gather_with_progress(
    problems: list[Problem],
    bounded_solve,
    aivy_logger: logging.Logger,
) -> list[ProblemResult]:
    bar = tqdm(total=len(problems), desc="solving", unit="prob")
    passed = 0
    failed = 0

    def _on_done(task: asyncio.Task) -> None:
        nonlocal passed, failed
        if task.cancelled() or task.exception() is not None:
            failed += 1
        else:
            result = task.result()
            if result.success:
                passed += 1
            else:
                failed += 1
        bar.update(1)
        bar.set_postfix(passed=passed, failed=failed)

    tasks = [asyncio.create_task(bounded_solve(p)) for p in problems]
    for t in tasks:
        t.add_done_callback(_on_done)

    prev_level = aivy_logger.level
    aivy_logger.setLevel(logging.WARNING)
    try:
        return await asyncio.gather(*tasks)
    finally:
        aivy_logger.setLevel(prev_level)
        bar.close()
