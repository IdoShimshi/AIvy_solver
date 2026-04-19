IVY_KNOWLEDGE = """\
# Ivy Language Reference (for invariant synthesis)

## What Ivy Is
Ivy is a language for specifying and verifying protocols. Programs model \
transition systems: types define the state space, relations/functions hold \
state, actions are transitions, and `invariant` lines state properties that \
must hold at all times. Verification is done by `ivy_check`, which proves \
invariants are inductive using the Z3 SMT solver.

## File Structure
```
#lang ivy1.7
type node                           # uninterpreted type
relation link(X:node, Y:node)      # mutable boolean function (state)
individual root : node              # single state variable
function f(X:node) : node          # function (state)
after init { link(X,Y) := false }  # initialization
action step(x:node) = { ... }     # transition
export step                         # environment can call this
invariant FORMULA                   # must hold after init and after every exported action
```

## Key Syntax
- `type t` — uninterpreted sort (could be any nonempty set)
- `type color = {red, green, blue}` — enumerated type
- `relation r(X:t, Y:t)` — boolean function on tuples (mutable state)
- `function f(X:t) : u` — function (mutable state)
- `individual x : t` — single value (mutable state)
- Capital letters (X, Y, N) are universally quantified logical variables
- Lowercase letters (x, y, n) are program variables / parameters

## Initialization
```
after init {
    relation_name(X, Y) := false;    # simultaneous: all tuples set to false
    some_var := 0
}
```

## Actions
```
action send(src: node, dst: node) = {
    require has_lock(src);          # precondition (caller responsible)
    assume has_lock(src);           # like require but no blame
    message(src, dst) := true;      # assignment
    has_lock(src) := false
}
```
- `require P` / `assume P` — guard/precondition
- `:=` — assignment; `x := *` — nondeterministic
- `f(x, Y) := false` — simultaneous: sets f(x,y) to false for ALL y
- Semicolon `;` is sequential composition, not a terminator

## Logic & Expressions
- `&` (and), `|` (or), `~` (not), `->` (implies), `<->` (iff)
- `=`, `~=` (not equal), `<`, `<=`, `>`, `>=`
- `forall X:t. P(X)`, `exists X:t. P(X)`
- In invariants, free capital-letter variables are implicitly universally quantified

## Invariants
```
invariant holds_lock(N1) & holds_lock(N2) -> N1 = N2
```
An invariant must be **inductive**:
1. **Initiation**: true in all initial states
2. **Consecution**: if true before any exported action, still true after

A property that is true but not inductive must be **strengthened** with \
supporting invariants. Example:
- Safety: `invariant holds_lock(X) & holds_lock(Y) -> X = Y`
- Supporting: `invariant ~(holds_lock(X) & message(Y,Z))`
- Supporting: `invariant ~message(X,Y) | ~message(Z,W) | X = Z`

Together they form an inductive set: each is preserved by every action \
given the conjunction of all invariants.

## ivy_check Output
ivy_check tests each invariant against initialization and each exported action.
```
Initialization must establish the invariant
    file.ivy: line 30: invar1 ... PASS
The following set of external actions must preserve the invariant:
    ext:send
        file.ivy: line 30: invar1 ... PASS
    ext:recv
        file.ivy: line 30: invar1 ... FAIL
```
FAIL means the invariant is not preserved by that action.

When a check fails, ivy_check prints a **counterexample trace** — a concrete \
execution that starts in a state satisfying all current invariants and reaches \
a state where one is violated. Example:
```
    ext:recv
        file.ivy: line 42: invar3 ... FAIL
file.ivy: line 18: message(n0,n1) = true
file.ivy: line 18: message(n0,n0) = false
file.ivy: line 19: has_lock(n0) = true
file.ivy: line 19: has_lock(n1) = false
...
[after recv] has_lock(n1) = true, has_lock(n0) = true  <-- violates invar3
```
This trace tells you:
1. **Which action** caused the failure (recv)
2. **Which invariant** failed (invar3, at line 42)
3. **The pre-state** values of relations/functions that led to the violation
4. **The post-state** showing the violation

Use the trace to understand WHY the invariant broke:
- Look at what the action did in that specific state
- Identify what additional fact about the pre-state would have prevented \
  this scenario
- Add that fact as a new supporting invariant

## Decidable Fragment (EPR/FAU)
ivy_check works reliably when verification conditions are in the decidable \
fragment. Key rules:
- **Prefer relations over functions** (relations are EPR-friendly)
- **Avoid arithmetic on universally quantified variables** (X+1, X-Y are \
  outside the fragment)
- **Avoid function cycles** (f:t→u and g:u→t create undecidable cycles)
- Quantifier alternations (forall-exists over same type) can be problematic
- Keep invariants as **quantifier-free** or **universally quantified** \
  formulas when possible

## Strategies for Finding Invariants
1. **Think inductively**: what must be true so that each action preserves \
   the safety property?
2. **Mutual exclusion**: if only one thing can be true at a time, state it \
   (`~(A & B)`)
3. **Message invariants**: if messages exist, relate message contents to \
   sender state at send time
4. **Monotonicity**: once a fact becomes true/false, it stays that way
5. **Quorum intersection**: for consensus protocols, preserve the link \
   between decisions and quorum votes
6. **Strengthening**: if ivy_check shows action A breaks invariant I, think \
   about what additional fact would prevent that specific scenario

## Complete Example: Lock Server
```
#lang ivy1.7
type node
relation lock_msg(N:node)
relation grant_msg(N:node)
relation unlock_msg(N:node)
relation holds_lock(N:node)
individual server_holds_lock: bool

after init {
    lock_msg(N) := false;
    grant_msg(N) := false;
    unlock_msg(N) := false;
    holds_lock(N) := false;
    server_holds_lock := true;
}

action send_lock(n: node) = { lock_msg(n) := true }
action recv_lock(n: node) = {
    require server_holds_lock;
    require lock_msg(n);
    server_holds_lock := false;
    lock_msg(N) := lock_msg(N) & N ~= n;
    grant_msg(n) := true;
}
action recv_grant(n: node) = {
    require grant_msg(n);
    grant_msg(N) := grant_msg(N) & N ~= n;
    holds_lock(n) := true;
}
action unlock(n: node) = {
    require holds_lock(n);
    holds_lock(N) := holds_lock(N) & N ~= n;
    unlock_msg(n) := true;
}
action recv_unlock(n: node) = {
    require unlock_msg(n);
    unlock_msg(N) := unlock_msg(N) & N ~= n;
    server_holds_lock := true;
}
export send_lock
export recv_lock
export recv_grant
export unlock
export recv_unlock

# safety property
invariant [safety] holds_lock(N1) & holds_lock(N2) -> N1 = N2

# supporting invariants (these make the safety property inductive)
invariant grant_msg(N1) & grant_msg(N2) -> N1 = N2
invariant unlock_msg(N1) & unlock_msg(N2) -> N1 = N2
invariant ~(holds_lock(N1) & grant_msg(N2))
invariant ~(holds_lock(N1) & unlock_msg(N2))
invariant ~(grant_msg(N1) & unlock_msg(N2))
invariant ~(grant_msg(N) & server_holds_lock)
invariant ~(holds_lock(N) & server_holds_lock)
invariant ~(unlock_msg(N) & server_holds_lock)
```
The key insight: the lock token exists in exactly one form at a time \
(server_holds_lock, grant_msg, holds_lock, or unlock_msg), and each form \
is unique. The supporting invariants encode all pairwise mutual exclusions."""

SYSTEM_PROMPT = f"""\
You are an expert in the Ivy verification language. Your task is to add \
inductive invariants to Ivy programs so that ivy_check verifies them.

CRITICAL OUTPUT FORMAT RULES — you MUST follow ALL of these:
1. Your response must contain ONLY a complete Ivy program. \
No English text, no explanations, no reasoning, no markdown — ONLY Ivy code.
2. The program you return must start with `#lang ivy1.7` and include \
EVERY line from the original program, unchanged, plus your new invariants.
3. Do NOT output just the invariants — output the ENTIRE program.
4. Do NOT explain your thinking — just output code.
5. Do NOT modify any existing lines (types, relations, actions, axioms, \
init blocks, exports, or the safety invariant).
6. You may only ADD new `invariant` lines that strengthen the inductive \
hypothesis so ivy_check can prove the safety property.
7. Place new invariants at the end of the program, after the existing invariant.

---

Below is a reference on the Ivy language. Consult it as needed.

{IVY_KNOWLEDGE}"""

USER_PROMPT_TEMPLATE = """\
The following Ivy program has a safety property (marked as `invariant`) \
that ivy_check cannot prove on its own because supporting invariants are missing.

Add the necessary `invariant` lines so that ivy_check verifies the program.

Respond with ONLY the complete Ivy program — all original lines unchanged, \
plus your new invariants at the end. No explanations.

Program:
{stripped_program}

Below is the current ivy_check output for this program. Use it to understand \
which action breaks the safety property and what counterexample state leads \
to the violation:

{ivy_output}"""

RETRY_PROMPT_TEMPLATE = """\
Your previous solution did not pass ivy_check. Here is the full output:

{error_output}

Fix your invariants and respond with ONLY the complete Ivy program. \
No explanations — just the full program starting with #lang ivy1.7."""

TIMEOUT_FEEDBACK = """\
ivy_check timed out. Your invariants may be too complex or outside the \
decidable fragment. Try simpler, quantifier-free invariants. \
Respond with ONLY the complete Ivy program starting with #lang ivy1.7."""

EMPTY_RESPONSE_FEEDBACK = """\
Your response was empty or contained no Ivy code. \
Respond with ONLY the complete Ivy program starting with #lang ivy1.7, \
including all original lines plus your new invariants."""

MODIFIED_LINES_FEEDBACK = """\
You modified existing lines of the program. \
Only new `invariant` lines may be added — all original lines must stay untouched. \
Respond with ONLY the complete Ivy program starting with #lang ivy1.7, \
with the original lines exactly preserved and only new invariants appended."""
