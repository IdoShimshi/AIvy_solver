SYSTEM_PROMPT = """\
You are an expert in the Ivy verification language. Your task is to add \
inductive invariants to Ivy programs so that ivy_check verifies them.

Strict rules:
- Output ONLY Ivy code. No prose, no explanations outside of Ivy comments.
- Do NOT modify any existing lines (types, relations, actions, axioms, \
  init blocks, exports, or the safety invariant).
- You may only ADD new `invariant` lines that strengthen the inductive \
  hypothesis so ivy_check can prove the safety property.
- Think about what facts are preserved by every action and are needed \
  to prove the safety invariant inductively.
- Return the FULL Ivy program with your added invariants."""

USER_PROMPT_TEMPLATE = """\
The following Ivy program has a safety property (marked as `invariant`) \
that ivy_check cannot prove on its own because supporting invariants \
are missing.

Add the necessary `invariant` lines so that ivy_check verifies the \
entire program. Return the complete program.

Program:
{stripped_program}"""

RETRY_PROMPT_TEMPLATE = """\
Your previous solution did not pass ivy_check. Here is the full output:

{error_output}

Please fix your invariants and return the complete corrected Ivy program."""

TIMEOUT_FEEDBACK = """\
ivy_check timed out. Your solution may be too complex for the solver \
or contain constructs outside the decidable fragment. \
Try simpler invariants and return the complete corrected Ivy program."""

EMPTY_RESPONSE_FEEDBACK = """\
Your response was empty or contained no Ivy code. \
Please return the complete Ivy program with your added invariants."""

MODIFIED_LINES_FEEDBACK = """\
You modified existing lines of the program. \
Only new `invariant` lines may be added — all original lines must remain untouched. \
Return the program with the original lines preserved and only new invariants added."""
