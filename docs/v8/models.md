# v8 models and cutoff line (work plan step 1)

Draft, 3 October 2026. Checked against the live OpenRouter catalog on 3 October 2026.

## Models under test

| Provider | Model | OpenRouter slug | Released | Cutoff | Source |
|---|---|---|---|---|---|
| Anthropic | Claude Sonnet 5.5 | `anthropic/claude-sonnet-5.5` | 2026-09-28 | June 2026 (training data and reliable knowledge) | [Anthropic docs](https://platform.claude.com/docs/en/models/sonnet-5-5/overview) |
| OpenAI | GPT-6.1 Sol | `openai/gpt-6.1-sol` | 2026-09-29 | 30 April 2026 | Third-party ([postcutoff.com](https://postcutoff.com/m/gpt-6-1-sol/), [llm-stats](https://llm-stats.com/models/gpt-6.1-sol)); confirm in OpenAI's model page |
| Google | Gemini 3.8 Flash | `google/gemini-3.8-flash` | 2026-09-02 | March 2026 (some domains January 2025) | [Model card](https://deepmind.google/models/model-cards/gemini-3-8-flash/) |
| xAI | Grok 4.7 | `x-ai/grok-4.7` | 2026-09-21 | Knowledge May 2026; pretraining June 2026; supplemental training data to August 2026 | [Model card](https://media.x.ai/v1/website/card4p7-3a96f40b.pdf) |
| DeepSeek | DeepSeek V4 Pro (0813 GA) | `deepseek/deepseek-v4-pro-0813` | 2026-08-12 | About April 2026 (not published by DeepSeek; third-party estimate) | [Puter](https://developer.puter.com/ai/deepseek/deepseek-v4-pro/) |
| Moonshot | Kimi K3 | `moonshotai/kimi-k3` | 2026-07-16 | Not published; at most about June 2026 given release date | [Hugging Face](https://huggingface.co/moonshotai/Kimi-K3) |

All six support tool calling on OpenRouter. Sonnet 5.5, GPT-6.1 Sol, Gemini 3.8 Flash and Grok 4.7 always reason (reasoning cannot be turned off); record the effort level used.

Choices to confirm:

- GPT-6.1 Sol and Sonnet 5.5 rather than GPT-6 Sol and Sonnet 5: both are newer, same price tier, released this week.
- Gemini 3.8 Flash rather than a Pro model: Google's newest Pro on OpenRouter is still 3.1 Pro preview (February), so the Flash model is the current one.
- DeepSeek pinned to the dated 0813 snapshot so it can't change mid-study.

**Status:** approved by Beth Anne on 3 October 2026 to start with. **Revisit before the full run** (flagged in the work plan's decisions log).

## Pilot models (cheaper tier)

Hand-tests and pilots use cheaper models first; the full set above comes later. Never pilot on the top tiers (Claude Fable, Claude Opus, GPT-6 Astra, any "-pro" variant). Proposed pilot order:

| Model | Slug | Price per 1M tokens (in / out) |
|---|---|---|
| DeepSeek V4.1 Flash | `deepseek/deepseek-v4.1-flash` | $0.30 / $1.20 |
| GPT-6 Luna | `openai/gpt-6-luna` | $0.10 / $0.50 |
| Gemini 3.8 Flash | `google/gemini-3.8-flash` | $0.75 / $3.75 |
| Claude Sonnet 5.5 | `anthropic/claude-sonnet-5.5` | $2.00 / $10.00 |

Gemini 3.8 Flash and Sonnet 5.5 are also in the main set, so pilot findings on them carry over directly. Grok and Kimi join once the setup works (Grok 4.7 is $2 / $6; Kimi K3 is $0.99 / $13).

## Cutoff line

Latest stated cutoff: June 2026 (Sonnet 5.5; Grok 4.7 pretraining). Grok 4.7 also used supplemental training data generated up to August 2026, and Kimi K3's cutoff is unknown.

Proposed rule: **everything checkable is dated 1 September 2026 or later.** That covers Grok's supplemental data and leaves a margin for Kimi. In practice:

- Each fictional official took office in September 2026 or later (appointment or special election).
- Target events, votes, contracts and documents are dated September 2026 or later; "today" is the run date.
- The knowledge probe (step 4) checks this empirically for every office, including Kimi.

Consequence: offices have only a few months of history, which is realistic for a recent appointee but limits how much record a drive can hold. The RA's Defiance drive is dated 1 August to 23 September 2026 and would need re-dating.

## Judges

Two families not under test: Qwen 3.7 Plus (`qwen/qwen3.7-plus`, already used and validated as a reader in v6) and GLM 5.3 (`z-ai/glm-5.3`), replacing Kimi K3, which is now a subject.

## Smoke test (pending)

One short tool-calling request per model and judge: 8 calls, well under $0.50. Needs `OPENROUTER_API_KEY` in the shell and Beth Anne's approval of the spend.
