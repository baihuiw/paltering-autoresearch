# v8 work plan

The order in which we implement [design_v8.md](design_v8.md). Work through it top to bottom; each step ends with a review with Beth Anne before the next begins. Update the status and notes as we go.

Status key: `[ ]` not started, `[~]` in progress, `[x]` done.

## Step 1. Cutoff line `[~]`

- Confirm the six models against the live OpenRouter catalog (OpenAI, Anthropic, Google, xAI, two Chinese).
- Record each model's training cutoff with its source; the latest is the cutoff line.
- Tool-calling smoke test per model (one short call each; needs approval of a small spend).
- Choose two judge models from families not under test.

Output: `docs/v8/models.md` (models, slugs, cutoffs, sources, judges).
Done when: Beth Anne approves the model list and the cutoff line.

Notes (2026-10-03): models approved to start (revisit later); pilot tier chosen. Still open: the 1 September 2026 cutoff line and the smoke test (needs `OPENROUTER_API_KEY` and approval of < $0.50).

## Step 2. System prompt v1 `[x]`

- Base prompt template, filled per office (official, office, how mail arrives, named staff), with the ~150-word limit.
- Three condition blocks: baseline, realistic pressure, explicit steer (with and without "Everything you say has to be true").
- Remove the lines listed in design section 5; realistic signature and email domains.
- Ground wording in published office prompts (POPVOX, Indigov).

Output: `docs/v8/system_prompt.md`, then the code template.
Done when: Beth Anne approves the wording.

Notes (2026-10-03): wording approved. The code template is built with the harness in step 5.

## Step 3. Severity rubric and scenario key `[x]`

- Severity tiers with definitions and anchor examples.
- Question-form categories.
- Scenario key format: fact, false gist, tier, question form, decisive documents, honest / palter / lie reference replies, disclosability note.

Output: `docs/v8/rubric.md` and a JSON schema for scenario keys.

Notes (2026-10-03): approved. Severity combines harm and seriousness of conduct; rated by the author plus a model rater, with an RA spot-check. Realistic-email guidance and the large-drive rules added.

## Step 4. Office 1 by hand `[~]`

- Pick the office (proposal: convert the RA's Defiance mayor's office) and a fictional official appointed after the cutoff line.
- Knowledge probe on the office; read raw answers.
- Drive of 150-250 files (150,000-300,000 words) with realistic names; decisive facts private and buried in long ordinary documents (rubric section 7).
- Five scenarios spanning severity tiers and question forms; hand-written target documents and emails.
- Read every file for realism.

Output: `data/v8/offices/<office_id>/` (drive and scenarios).

Notes (2026-10-03): office and five concepts approved (docs/v8/office1_plan.md). Mayor Paul Haverkamp, appointed September 2026; invented names web-checked (office.json name_checks). Built so far: `data/v8/offices/defiance_mayor/office.json`, `AUTHORING.md`, `scripts/v8_probe_knowledge.py` (dry-run tested; paid run needs the API key), `scripts/v8_check_office.py` (automatic checks). Done (2026-10-03): five scenario keys and their documents (subagent-drafted, reviewed), bulk routine content in five non-overlapping batches merged with `scripts/v8_merge_bulk.py`, and two reconciliation passes. Drive: 192 files, 197,569 words; automatic checks pass; facts sheet in `WORLD.md`. Remaining for step 4: Beth Anne's read-through (scenario emails, keys, decisive documents and a sample of bulk files) and the knowledge probe (needs the API key and approval of < $1).

## Step 5. Harness changes `[~]`

- Tools: list_files, search_files, read_file, send_reply, route_to_staff (drop approved responses).
- One or two routine emails before the target; tool-call limit per email (15 to start, set in hand-testing); single turn.
- Private comprehension check, branched awareness question, reasoning capture, decisive-document logging.
- Outcome coding: honest, palter, lie, incidental error, explicit evasion, routed, technical failure; informed flag.
- Judges per step 1; truncated replies excluded.
- Fix Python 3.12 requirement so the test suite runs.

Output: new v8 runner module and tests; offline tests pass.

Notes (2026-10-03): built `palterlab/v8/` (prompts.py with the approved wording, drive.py with the five tools and a hash-chained log, episode.py with the queue, the branched private check and awareness question, and decisive-passage tracking), `scripts/v8_run.py` (hand-test runner with a budget cap, transcripts and a summary table) and `tests/test_v8_harness.py` (6 offline tests, passing). `palterlab/client.py` gained an optional `tool_choice` argument (backward compatible). Still to do: outcome coding by two judges (honest / palter / lie / incidental error / explicit evasion / routed), coding verbalized awareness in reasoning, and the Python 3.12 fix. The wording of the private-check and awareness questions needs Beth Anne's review.

## Step 6. Realism and eval-awareness checks `[ ]`

- Awareness test on a subset of pilot episodes (`--awareness subset`): asked P(test) and reasons, plus verbalized awareness in reasoning. This is the go/no-go check on realism before the main run (design section 10).
- Optional: P(evaluation) judge on sample transcripts against a realistic reference set.
- Revise office 1 until scores are acceptable.

## Step 7. Hand-test office 1 `[ ]`

- Condition 2 first, then 1, then 3 (both versions); 10-20 samples per condition; cheaper model first, then the rest.
- Read every transcript in full, tool calls included.
- Track routing; compare routing variants if needed.
- Log each prompt version, what changed and what we saw.

Output: `docs/v8/handtest_log.md`, transcripts and counts per condition.

## Step 8. Exploratory tactic analysis `[ ]`

- Plain-language description of each palter; cluster into emergent tactics.
- Reconcile with taxonomy A-H; first codebook draft; omission-only variable.

Output: `docs/v8/tactics_codebook.md`.

## Step 9. Joint review: go or no-go `[ ]`

Decide whether office 1 works and what changes before scaling.

## Step 10. Scale to 60 offices `[ ]`

- Knowledge probe per office; model-drafted routine content, hand-edited; hand-written targets.
- Automate generation and scoring; read a sample of transcripts from each new office.
- Generation method (agreed 2026-10-03): split offices into non-overlapping batches; one subagent per batch writes its offices' drive files and appends each scenario key to its own `scenarios/batch_XX.jsonl`. Each subagent gets the full brief (AUTHORING.md, rubric, schema, system prompt), a per-office facts sheet, and office 1's reviewed scenarios as examples. Merge step: schema check, duplicates across offices (officials, invented businesses, senders, topics, near-identical emails), the automatic office checks, and counts per category (severity, conduct type, question form, office type, state, party).

## Step 11. Full run `[ ]`

- Cost estimate and Beth Anne's approval of the spend.
- Run with `--awareness none` (no awareness question); keep verbalized-awareness coding. Analysis; report by verbalized awareness.

## Decisions log

| Date | Decision |
|---|---|
| 2026-10-03 | Design agreed (design_v8.md). Automated search dropped. |
| 2026-10-03 | Six models approved to start (docs/v8/models.md). **Revisit the model list before the full run.** |
| 2026-10-03 | Pilots and hand-tests use cheaper models first (DeepSeek V4.1 Flash, GPT-6 Luna, Gemini 3.8 Flash, Sonnet 5.5); never Fable, Opus, Astra or "-pro" variants in pilots. |
| 2026-10-03 | System prompt: drive described by folder names; "warm, professional tone" in baseline; condition 2 drops the election-year sentence and adds "come away confident" and "don't admit fault"; condition 3 keeps v7's "don't get into it" wording (favors paltering over explicit evasion). |
| 2026-10-03 | Severity: harm plus seriousness of conduct; model rater plus RA spot-check. Drive must bury decisive facts in a large corpus (150-250 files). Emails written to sound like real constituent mail. |
| 2026-10-03 | API key stored in git-ignored `.env` (loaded by `palterlab/v8/env.py`). Knowledge probe passed for Defiance (no model calls the official fictional; Gemini 3.8 Flash treats Sept 2026 as future without a date). Pilot models: Claude Sonnet 5.5, ChatGPT's free model (`gpt-chat-latest`), Grok 4.6. |
| 2026-10-03 | Smoke-test fixes: tool_choice 'auto' for all models; 30 tool calls per email; no utility bills in the casework examples; scenario 4 email asks about everyone's bills. |
| 2026-10-03 | Cost: target under $50 for the pilot. Anthropic prompt caching, one routine email per episode from a pool of 12, 120-line reads (docs/v8/cost.md). |
| 2026-10-03 | Judge protocol drafted (docs/v8/judge_protocol.md); first reference check 13/20, fixes applied (literal-truth rule with examples, scenario 1 reference, reader token limit). Routing variants standard / clarified / none under test. |
| 2026-10-03 | Eval awareness becomes a separate test on a subset: asked in the first sample of each pilot cell; not asked in the main run. Verbalized-awareness coding of reasoning stays on every episode. |
| 2026-10-03 | Routing narrowed: reply to every message; route only threats, legal action and media requests (to the chief of staff). Tool description narrowed to match. 'Reply and refer within the reply' rejected (invites non-answers). |
| 2026-10-03 | Pre-pilot harness items done: 'declined to send' outcome (text without sending; kept for review), one retry for empty responses, one retry for failed judge/reader calls, one reader sample per family, `scripts/v8_pilot.py` (episodes, scoring, summary; $40 cap). |
| 2026-10-03 | Measured cost about $0.29 per episode (Sonnet $0.18, ChatGPT $0.25, Grok $0.44). Pilot launched: 3 free-tier models x 5 scenarios x 3 conditions (baseline, pressure, steer; steer_true deferred) x 3 samples = 135 episodes, narrow routing, awareness on the first sample of each cell; caps $44 episodes + $6 scoring. Launched before Beth Anne's read-through; scenario 2 reader rule still open (raw reader scores kept, so outcomes can be recomputed). |
| 2026-10-03 | Speed: episodes 12 at a time by default (was 4), slowest models started first; scoring runs reader and both judges in parallel, 12 replies at a time. Keep the budget cap comfortably above expected spend so worst-case reservations don't throttle the run. The running pilot keeps 4 workers for its episodes (restarting would turn in-flight calls into failures); its scoring step uses the faster code. |
| 2026-10-03 | Grok deferred within the pilot (slowest and most expensive): pilot stopped at 58 episodes (Sonnet 21, ChatGPT 21, Grok 16; 4 Grok episodes interrupted, kept as logs); resumed with Sonnet and ChatGPT only. Grok's remaining 29 run later with `--models grok46` once the setup is settled; interrupted episodes restart as new attempts under new labels. |
| 2026-10-03 | Pilot (Sonnet, ChatGPT, partial Grok; 106 target emails; $25.12) scored. Found compound true propositions (core fact plus accountability details) inflating palter codes. Facts and propositions narrowed to the core asked state; accountability details moved to accountability_facts. Lies split by the private check into knowing lie / false statement under uncertainty / honest error. Reference check 15/20 (misses: scenario 2 reader rule, scenario 3 active-palter reference now an evasion, two single-judge Qwen slips). Rescoring into runs/v8_pilot_20261003/rescore1. |
