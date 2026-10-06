# v8 cost per episode: what drives it and what we changed

3 October 2026, from the second smoke test (`runs/v8_smoke2_20261003`: one episode each, scenario 4, two routine emails).

| Model | Cost | Input tokens sent | Served from cache | Steps |
|---|---|---|---|---|
| Claude Sonnet 5.5 | $0.81 | 384,000 | 0% | 12 |
| Grok 4.6 | $0.54 | 530,000 | 76% | 16 (plus 11,400 reasoning tokens) |
| ChatGPT chat (`gpt-chat-latest`) | $0.22 | 146,000 | 82% | 11 |

## What drives it

- The whole conversation is re-sent on every step. Context grows from about 1,000 to about 50,000 tokens as the model reads, so total input grows roughly with the square of how much it reads.
- The drive's size matters only through what the model reads. Models opened 10-20 files whether or not the other 180 exist. A smaller drive would save little and make the planted documents easier to spot (Sonnet already cited "the buried billing error" as a sign of a test).
- Anthropic caches only what the request marks; the harness marked nothing, so Sonnet paid full price for every re-sent token. OpenAI and xAI cache automatically.
- The two routine emails come first, so everything read for them is re-sent on every target step: roughly half the episode's cost.
- The private check and the awareness question each re-send the full context (about 15%). The awareness question was dropped on 6 October, so only the private check remains.

## Changes made

1. Anthropic cache marks on the system prompt and the newest message (`palterlab/v8/episode.py`, `with_cache_marks`). Cached input is billed at about a tenth.
2. One routine email per episode instead of two, drawn from a pool of 12 varied messages (`routine_emails.json`; `--routine` in `scripts/v8_run.py`). Also answers the awareness feedback that the routine mail "mapped too cleanly onto the routing rules".
3. File reads return 120 lines per section instead of 200.

Expected: about $0.20-0.25 per episode. A pilot of 3 models x 5 scenarios x 4 conditions x 3 samples (180 episodes) plus scoring would cost about $40-45. To be confirmed by the routing test (`runs/v8_routing_20261003`).
