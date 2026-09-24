# Office Library scenario search

A bounded, reward-guided search for settings in which an office assistant gives a materially misleading answer. This is an **adaptive adversarial evaluation**, not reinforcement-learning fine-tuning of the tested models. No model weights change. The generator receives feedback; the office assistant never receives the reward or a message saying that honesty is incorrect.

Built for Baihui Wang and Beth Anne Helgason. All offices, people and incidents in the library are fictional.

## Status

Implemented and tested offline. **No paid search has run.** Live provider compatibility and empirical reader calibration remain to be checked in the approved smoke run. Mock output is explicitly labelled and must never be used as empirical results.

- [Design and costs](docs/design.html)
- [Full protocol](docs/protocol.md)
- [Search instructions](program.md)
- [Cost calculations](docs/cost_estimates.json)
- Exact prompts: `palterlab/prompts.py`
- Configurations: `config/smoke.json`, `pilot.json`, `search60.json`, `search200.json`

## Information access

The generator can choose **private** or **shared** evidence. Both give the office the same incident facts. In shared, the recipient can retrieve a fixed case extract; in private, that extract is internal. An owner-specific case stays private to that owner, never public to everyone. Disclosure permissions do not change.

Each reply has separate message coding, an isolated factual-comprehension check, and reader assessments before and after optional retrieval. A selected condition is confirmed in both profiles with the same wording. See [the design](docs/design.html) for the paired comparison and updated cost estimate. Cross-office internal access and multiple office agents are not part of this version.

These are derived experimental archives. Some formerly public decisive papers are moved into staff scope in both versions, with publication metadata harmonized. The base archive and previous results are unchanged; all transformations are recorded in each snapshot’s `information.json`.

## What was adapted from autoresearch

Upstream: https://github.com/karpathy/autoresearch, commit `228791fb499afffb54b46200aca536f79142f117`, separately cloned to `../autoresearch-upstream`.

We adapt its fixed evaluator, constrained editable surface, recorded experiment budget and propose/test/keep-or-discard loop. Here the editable surface is a JSON condition plus operational documents; the measured outcome is communication and recipient inference. Upstream's `train.py`, GPU training and indefinite-loop instruction are **not executed**. This is an independent Git repository, not a claim that OpenRouter implements PPO/GRPO or weight updates. See `data/provenance.json`.

## Offline commands

Python 3.10+; standard library only.

```sh
cd /Users/wangbaihui/gist-eval/paltering-autoresearch
python3 -m unittest discover -s tests -v
python3 -m palterlab estimate --config config/smoke.json
python3 -m palterlab prepare --config config/smoke.json --out build/new_review
python3 -m palterlab mock --config config/smoke.json --out build/new_mock
python3 -m palterlab serve --out build/new_review --port 59603
```

Each preparation/mock needs a fresh output directory. The server binds only to localhost. Its researcher dashboard contains labels; **never give participants access to that dashboard**. Target tools access only the allowlisted library source snapshot, not arbitrary HTTP or the repository filesystem. Public, staff and case-specific recipient HTML are separately generated from the same snapshot used by the tools. This does not modify or publish the existing Office Library Site.

## Paid run: only after the owner approves the scope and cap

Set `OPENROUTER_API_KEY` in the shell (never in a tracked file). No credentials are copied from the older project. After approval:

```sh
python3 -m palterlab authorize --config config/smoke.json --out runs/smoke01 --approval .approvals/smoke01.json
python3 -m palterlab run --config config/smoke.json --out runs/smoke01 --approval .approvals/smoke01.json
```

`authorize` records a local audit permission, not identity authentication. It must not be executed before the owner approves. It binds the run directory, code, source files, model catalog, configuration and budget. If any of these change, review and renew approval. This turn created **no approval file**.

Resume with the identical `run` command. Completed and failed calls are cached; a failed/truncated completion is not resampled for a preferred outcome. Interrupted calls with unknown billing retain their full reservation. The live loop has an exclusive process lock. All requests, results, incomplete attempts and costs remain in `runs/` (ignored by Git). Do not delete ledgers to restart under the same budget. A new budget or new conditions require a new authorization.

Requests use catalog-supported parameters, price ceilings and no automatic provider fallback. Provider availability can still change. If a provider bills above the conservative reservation the run stops and records the overrun; a local reservation is not a billing guarantee. A dedicated capped OpenRouter key gives an additional account-side limit.

## Files

| Location | Purpose |
|---|---|
| `data/library/` | Frozen source-only archive, 157 files, 9 fictional offices |
| `data/information_plans.json` | Fixed extracts and controlled access changes for six cases |
| `data/cases.json` | Six researcher keys and reference answers; never a participant tool result |
| `data/model_catalog.json` | Public OpenRouter catalog fetched 23 September 2026 |
| `palterlab/candidates.py` | Proposals, integrity checks, independent semantic validation and immutable versions |
| `palterlab/library.py` | Office-scoped retrieval and hash-chained tool logs; reused from the prior project |
| `palterlab/subject.py` | Tool-using office assistant and optional follow-up conversation |
| `palterlab/evaluate.py` | Separate message coding and cloned recipient assessments |
| `palterlab/experiment.py` | Baselines, bounded search, frozen selection and transfer |
| `palterlab/client.py` | OpenRouter calls, durable cache, cost reservations and failures |
| `palterlab/site.py` | Source-only public/staff archive pages and separate researcher dashboard |

## Limits on conclusions

Search scores describe conditions deliberately selected for failures, not their prevalence in ordinary deployments. Small open-weight models and frontier products differ in more than honesty training. The six seed cases have appeared in earlier pilots; the reserved cases are held out from this **new adaptive search**, not historically unseen. Confirmation on newly authored dossiers, independent coders and human recipients is still needed. Reader probabilities are elicited reports, not observations of human belief. Native reasoning may be unavailable, and returned summaries do not establish intent.
