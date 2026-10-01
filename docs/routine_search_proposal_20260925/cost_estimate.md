# Scaling cost estimate

Estimate based on saved routine-condition token usage and OpenRouter prices checked on 25 September 2026. All figures are USD for one archive-access profile, with both Qwen and Kimi judging every reply. No paid model calls were made to prepare this estimate.

| Plan | Unique scenarios | Office episodes | Planning budget |
|---|---:|---:|---:|
| First stage: six models, three replies each | 100 | 1,800 | $100–$160 |
| Staged discovery, repetition and held-out evaluation | 1,000 | 14,000 | $750–$1,100 |
| Every scenario × six models × ten replies | 1,000 | 60,000 | $2,600–$4,100 |

The 14,000-episode plan comprises 700 × 4 × 2 = 5,600 discovery replies, 50 selected scenarios × 6 × 10 = 3,000 fresh repeated replies, and 300 locked scenarios × 6 × 3 = 5,400 evaluation replies. The 50 selected scenarios come from the discovery set.

## Components of the staged plan

| Component | Estimated base cost |
|---|---:|
| Create and validate 1,000 usable dossiers | $198 |
| Generate replies, research the archive, and run comprehension checks | $135 |
| Qwen judging: 14,000 replies | $39 |
| Kimi judging: 14,000 replies, current InferenceNet route | $206 |
| Total before calibration and contingency | $578 |

Using Kimi's catalog price instead raises its component to approximately $352. A $5–$10 calibration allowance and 25–50% contingency produce the $750–$1,100 planning range. This is an estimate, not a completion guarantee or authorized hard cap.

## Assumptions

Target-model usage comes from 16–20 completed routine episodes per model, so it reflects the setting we propose rather than only the shorter 0109/0136 replies. Judge usage comes from 710 completed replies under v4: approximately 4,550 input / 1,038 output tokens for Qwen and 4,496 input / 776 output tokens for Kimi. Completion usage already includes billed reasoning where reported. Pricing ignores cache discounts. No external web-search tool is budgeted: archive tools are local and their returned text contributes to API token usage.

Authoring and validation cost $1.9777 for ten accepted dossiers in the last batch (18 initial slots). The $198 extrapolation includes those rejected drafts, but cannot guarantee the same yield or quality for 1,000 distinct cases. A substantially longer archive trajectory or more extensive human revision changes the estimate.

Testing both private and shared access doubles target and judging work but reuses dossier authoring. The staged plan would then be approximately $1,200–$1,900, and the full crossing approximately $5,000–$7,900.

These estimates exclude recipient-reader tests, human annotation payments, fine-tuning/GPU training, subscriptions, payment fees and taxes. The target models stay unchanged. No run has been started, and previous budget caps have not been extended.

For the first step, 100 scenarios × six models × three replies, with a $200 hard cap, offers room to test the revised scorer. The cap is a stopping rule, not a promise that all requests complete.

Sources: [OpenRouter model prices](https://openrouter.ai/api/v1/models), [Kimi provider prices](https://openrouter.ai/api/v1/models/moonshotai/kimi-k3/endpoints). Exact calculations, token averages and assumptions are in cost_estimate.json.
