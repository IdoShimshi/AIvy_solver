IVY_KNOWLEDGE = """# Ivy Language Reference (for invariant synthesis)

## What Ivy Is
Ivy is a language for specifying and verifying protocols. Programs model transition systems: types define the state space, relations/functions hold state, actions are transitions, and `invariant` lines state properties that must hold at all times. Verification is done by `ivy_check`, which proves invariants are inductive using the Z3 SMT solver.

Ivy actions are atomic. Each exported action runs as one isolated transition. Concurrent behavior is modeled by the environment choosing exported actions in some order.

## File Structure

```ivy
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

```ivy
after init {
    relation_name(X, Y) := false;    # simultaneous: all tuples set to false
    some_var := 0
}
```

## Actions

```ivy
action send(src: node, dst: node) = {
    require has_lock(src);          # Caller may only call send when src holds the lock.
    message(src, dst) := true;      # State update: record that a message from src to dst has been sent.
    has_lock(src) := false          # State update: src gives up the lock after sending.
}
```

- `require P` — precondition; the caller must establish it
- `ensure P` — postcondition; the action must establish it
- `assert P` — proof obligation; Ivy must prove it
- `:=` — assignment; `x := *` — nondeterministic
- `f(x, Y) := false` — simultaneous: sets f(x,y) to false for ALL y
- Semicolon `;` is sequential composition, not a terminator

Actions are checked as isolated transitions. Ivy checks what can happen before and after each exported action. It does not reason about another action interrupting the middle of the current action.

## Modules

A module is a reusable template. It can contain types, relations, functions, actions, invariants, and other declarations.

```ivy
module counter(t) = {
    individual value : t

    after init {
        value := 0
    }

    action inc = {
        value := value + 1
    }

    action get returns (v:t) = {
        v := value
    }
}
```

A module is used with `instance`.

```ivy
type num
interpret num -> int

instance c : counter(num)

export c.inc
export c.get
```

This creates one counter named `c`. Its state is `c.value`. Its actions are `c.inc` and `c.get`.

Modules are useful when the same pattern appears more than once. They also make examples easier to split into small parts.

Parameterized instances create one object per value.

```ivy
type node
instance local_counter(N:node) : counter(num)
```

Now each node has its own counter:

```ivy
local_counter(n).inc
local_counter(n).get
```

## Trusted Isolates
A `trusted isolate` is a component Ivy assumes is correct. Ivy uses its `ensure` facts, but does not prove them.

```ivy
trusted isolate ns = {
    action add(n:node, s:nodeset) returns (res:nodeset) = {
        ensure member(n,res)
    }
}
```

When proving invariants, treat it as a black box. Use only the facts it promises.

## Logic & Expressions

- `&` (and), `|` (or), `~` (not), `->` (implies), `<->` (iff)
- `=`, `~=` (not equal), `<`, `<=`, `>`, `>=`
- `forall X:t. P(X)`, `exists X:t. P(X)`
- In invariants, free capital-letter variables are implicitly universally quantified. For example:

    ```ivy
    invariant message(X, Y) -> has_lock(X)
    ```

    is equivalent to:

    ```ivy
    invariant forall X:node, Y:node. message(X, Y) -> has_lock(X)
    ```

## Axioms

An `axiom` is a fact Ivy accepts without proof.

```ivy
axiom forall S1:nodeset, S2:nodeset.
    majority(S1) & majority(S2) -> exists N. member(N,S1) & member(N,S2)
```

Axioms are useful for abstract facts, like quorum intersection.

They are also dangerous. If axioms are inconsistent, Ivy may prove incorrect things. Never use axioms yourself.

## Invariants

```ivy
invariant holds_lock(N1) & holds_lock(N2) -> N1 = N2
```

An invariant must be **inductive**:

1. **Initiation**: true in all initial states
2. **Consecution**: if true before any exported action, still true after

A property that is true but not inductive must be **strengthened** with supporting invariants. Example:

- Safety: `invariant holds_lock(X) & holds_lock(Y) -> X = Y`
- Supporting: `invariant ~(holds_lock(X) & message(Y,Z))`
- Supporting: `invariant ~message(X,Y) | ~message(Z,W) | X = Z`

Together they form an inductive set: each is preserved by every action given the conjunction of all invariants.

## ivy_check Output

ivy_check tests each invariant against initialization and each exported action.

```text
Initialization must establish the invariant
    file.ivy: line 30: invar1 ... PASS
The following set of external actions must preserve the invariant:
    ext:send
        file.ivy: line 30: invar1 ... PASS
    ext:recv
        file.ivy: line 30: invar1 ... FAIL
```

FAIL means the invariant is not preserved by that action.

When a check fails, ivy_check prints a **counterexample trace** — a concrete execution that starts in a state satisfying all current invariants and reaches a state where one is violated. Example:

```text
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
- Identify what additional fact about the pre-state would have prevented this scenario
- Add that fact as a new supporting invariant

## Decidable Fragment (EPR/FAU)

ivy_check works reliably when verification conditions are in the decidable fragment. Key rules:

- **Prefer relations over functions** (relations are EPR-friendly)
- **Avoid arithmetic on universally quantified variables** (X+1, X-Y are outside the fragment)
- **Avoid function cycles** (f:t->u and g:u->t create undecidable cycles)
- Quantifier alternations (forall-exists over same type) can be problematic
- Keep invariants as **quantifier-free** or **universally quantified** formulas when possible

## Strategies for Finding Invariants

1. **Think inductively**: what must be true so that each action preserves the safety property?
2. **Mutual exclusion**: if only one thing can be true at a time, state it (`~(A & B)`)
3. **Message invariants**: if messages exist, relate message contents to sender state at send time
4. **Monotonicity**: once a fact becomes true/false, it stays that way
5. **Quorum intersection**: for consensus protocols, preserve the link between decisions and quorum votes
6. **Strengthening**: if ivy_check shows action A breaks invariant I, think about what additional fact would prevent that specific scenario

## Complete Example: Lock Server

```ivy
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

The key insight: the lock token exists in exactly one form at a time (server_holds_lock, grant_msg, holds_lock, or unlock_msg), and each form is unique. The supporting invariants encode all pairwise mutual exclusions.
"""

SYSTEM_PROMPT = f"""\
You are an expert in the Ivy verification language. Your task is to add \
inductive invariants to Ivy programs so that ivy_check verifies them.

CRITICAL OUTPUT FORMAT RULES — you MUST follow ALL of these:
1. Output ONLY new `invariant` declarations that should be appended to the \
program. Nothing else. No prose, no explanations, no reasoning, no markdown \
fences, no comments, no `#lang` line, no `relation`, `function`, `type`, \
`definition`, `property`, `axiom`, `action`, `module`, or any other Ivy \
declaration — ONLY `invariant ...` declarations.
2. Each invariant declaration starts with the keyword `invariant`. \
A single invariant MAY span multiple lines (e.g. to break up long quantifier \
prefixes or large conjunctions); just make sure the next `invariant` keyword \
is what begins the next declaration. Whatever you output will be appended \
verbatim to the end of the program, so it must parse as valid Ivy.
3. On every turn, output the COMPLETE set of invariants you want appended \
to the program. The system replaces (not merges) your previous answer with \
your latest one, so anything you omit will be lost. If on a previous turn \
you had two invariants that you still want, repeat them in full alongside \
any new ones.
4. Do NOT attempt to modify, repeat, or reference any existing line of the \
program. The original program is fixed; you only contribute new invariants.

---

Below is a reference on the Ivy language. Consult it as needed.

{IVY_KNOWLEDGE}"""

USER_PROMPT_TEMPLATE = """\
The following Ivy program has a safety property (marked as `invariant`) \
that ivy_check cannot prove on its own because supporting invariants are missing.

Your job is to come up with a set of `invariant` declarations that, when \
appended to the end of the program, make ivy_check succeed.

Respond with ONLY the new `invariant` declarations — nothing else. A single \
invariant may span multiple lines if that helps readability.

Program:
{stripped_program}

Below is the current ivy_check output for this program. Use it to understand \
which action breaks the safety property and what counterexample state leads \
to the violation:

{ivy_output}"""

RETRY_PROMPT_TEMPLATE = """\
Your previous set of invariants did not pass ivy_check. Here is the full output:

{error_output}

Use the counterexample to understand which state and action lead to the \
failure and what additional fact about the pre-state would have prevented it.

Reply with the COMPLETE updated set of invariants you want appended to the \
program (not just changes — anything you omit will be dropped). Output ONLY \
`invariant` declarations. No prose, no comments, no fences."""

TIMEOUT_FEEDBACK = """\
ivy_check timed out. Your invariants may be too complex or outside the \
decidable fragment. Try simpler, quantifier-free invariants. \
Reply with the complete updated set of `invariant` declarations you want \
appended to the program. Output ONLY `invariant` declarations — no prose, \
no comments, no fences."""

EMPTY_RESPONSE_FEEDBACK = """\
Your response was empty or contained no Ivy code. \
Reply with the complete set of `invariant` declarations you want appended \
to the program — nothing else."""
