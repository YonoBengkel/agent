---
name: grilling
description: Grill the user relentlessly about a plan, decision, or idea. Use when the user wants to stress-test their thinking, or uses any 'grill' or 'drill' trigger phrases, such as "drill", "putaran drill", or "grill me".
---

Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it. If no plan, decision, or idea has been named, ask for it first and don't invent one.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Numbers continue across rounds: if round 1 ends at Q5, round 2 starts at Q6. Then wait for the user's answers before the next round.

Format a round like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>

---

❓ **Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Word each question so "yes" accepts your recommended answer.

Each round the user answers reshapes the tree: settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this one.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a sub-agent to find it (look it up yourself when the platform has none); don't ask the user for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report; ask the rest of the frontier now. The _decisions_ are the user's: put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Then list every settled decision, ask the user to confirm this is the shared understanding, and stop.

"Yes to all" settles only that round's questions, and "continue" asks only for the next round or this summary. Neither is permission to act. Until the user confirms the summary, do not act on the plan and do not create, change, or overwrite any project file, the plan itself included. After the confirmation, write the plan file only if the user asked for it or says yes when you name the file.

For a large plan written to a file, before acting, give only that file to a fresh reviewer subagent. It restates the plan in its own words, then lists gaps and says whether the plan is ready. A wrong restatement means the plan is ambiguous. Skip this when the platform has no subagents.
