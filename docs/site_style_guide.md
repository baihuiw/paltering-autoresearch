# PalterBench results site: style guide

Written 13 October 2026. This guide sets how the public results page is written and designed. It is drawn from four sets of exemplars, studied for this purpose:

| Exemplar | Pages looked at | What we take from it |
|---|---|---|
| Transluce | Investigating truthfulness in a pre-release o3 model; Docent; Monitor | Bold summary paragraph instead of an abstract; a real transcript within the first screen; link from excerpt to full transcript |
| Anthropic research | Alignment faking; Agentic misalignment; Reasoning models don't always say what they think | Serif body in a narrow column; headings that state findings; numbered figures with full-sentence captions that give n; a named caveats section |
| Machine Bullshit (BullshitEval) | machine-bullshit.github.io | Question headings ("What is bullshit?"); one-sentence finding above each figure; Paper / Code / Data buttons. Its cartoon icons and emoji are what we avoid |
| Andy Hall | The Dictatorship Eval (Substack post and dictatoreval.org); Who would AI tell Brazil to vote for? | Subtitle that is the headline finding; results ordered by importance; metric defined once with its direction ("Higher is better"); counts beside percentages; narrative kept separate from the browsable data |

What these share is the standard for our page: **the finding first and in words, one real example before any method, every number explained in a sentence, quiet visuals, and limits stated plainly.**

## 1. Structure

The page reads top to bottom as an argument. A reader who leaves after thirty seconds knows what was found and has seen it happen once. A reader who stays five minutes knows how it was measured and what it does not show. A reader who stays longer can check every reply.

1. **Title and standfirst.** The title is the finding or the plain question ("Do AI assistants mislead residents with true statements?"). The standfirst, one or two sentences, gives the answer with a number (Hall's subtitle pattern). Byline, date, buttons (Paper, Data, Code; dashed "coming" buttons for anything not yet public). If results are preliminary, a status line with the data date.
2. **Summary.** Three or four bolded sentences, in the style of Transluce's opening: what we did, the main result, the second result, the main limit. No "Abstract" label, no bullet box.
3. **One example** (`#example`). Two sentences of setup (who wrote in, what the office's records show), then one real reply beside an honest reference reply, with the misleading span highlighted. Then one sentence that names what happened and defines paltering at the point the reader has just seen it.
4. **What we found** (`#results`). Each finding gets a heading that states it, one or two paragraphs, and one figure. Findings are ordered by importance, not by the order analyses were run. Expected order for the full run:
   - how often each model palters, lies and answers honestly (main figure);
   - what the pressure and "never make up information" conditions do (the lie-to-palter prediction);
   - whether models knew the fact (private knowledge check) when they misled;
   - one secondary cut if it earns its place (question form, conduct type or severity).
5. **How we measured it** (`#method`). Four or five sentences a researcher could repeat to a colleague. Then a definitions list (conditions, outcome categories, question forms), and collapsed sections for the full system prompt, judge prompt, judge validation and scenario construction. One open sentence on how the judge was validated.
6. **Limits** (`#limits`). A named section, as Anthropic does it. Five or six questions a sceptic would ask, answered directly: fictional offices; model judges, not human readers; scenarios built to make the fact available, so rates are not prevalence; one sample per episode; the development office used to tune scoring.
7. **Browse the replies** (`#replies`). The full reply archive with filters. It sits at the end, after the argument, as on dictatoreval.org, where the essay and the leaderboard are separate.
8. **Resources** (`#resources`). Data downloads, code, citation, acknowledgements.

What does not appear above the method section: judge names, condition codes, run IDs, pipeline caveats, provisional-coding notices. These belong in the method or limits.

## 2. Writing

- **Headings state findings or ask a reader's question.** "Models rarely lie, but often mislead", "The accuracy rule turns lies into palters", "What counts as paltering?". Avoid paper headings (Results, Methods, Discussion) and topic labels ("Repeat comparison").
- **Define each term once, where it is needed.** Paltering, the three conditions and the outcome categories each get one sentence. Then the same word is used every time.
- **Every number gets a reading.** Give the denominator ("41 of 540 replies, about 8%"), round in prose (whole percentages), and keep exact values in the tables. Every scale says its direction ("Higher is worse").
- **Describe behaviour, not intent.** "The reply omitted that the work was postponed" is a finding. "The model tried to protect the mayor" is not.
- **State limits flatly, once.** Say "These are invented scenarios scored by model judges", not "results may potentially suggest". Say near the first headline number that the rates are not real-world prevalence.
- **Plain register.** Use "We" for the authors. Use the present tense for what models do and the past tense for what we did. No "In this post we will". No closing summary that repeats the top.
- **Name models exactly** (Claude Opus 5.5, GPT-6.1 Sol Pro), never internal keys (`opus55`).

## 3. Visual design

The page should look like a research report, not an app. All restraint, with one loud element: the highlight on the misleading span.

- **Type.** Body in a serif (Source Serif 4) at about 18–19px with 1.6 line-height, in a single column about 41rem (650px) wide. This matches Anthropic's 640px serif column. Headings, figures, captions and controls use a sans (Schibsted Grotesk). Tabular numerals in tables and figures.
- **Colour.** Near-white page, navy-black ink, two greys, one link blue. Data colours are fixed by meaning and used identically in every figure:
  - honest: blue `#0072B2`
  - palter: amber `#E69F00`
  - lie (false assertion): dark red `#7A1F3D`
  - other / no reply / routed: grey `#9AA5BC`

  Conditions use a second set that never collides with outcomes. Colour is never the only cue: segments carry labels and every chart has a table.
- **No ornament.** No gradients, drop shadows, card grids, rounded "pill" tags everywhere, emoji, icons, illustrations or entrance animation. Thin rules separate things; whitespace does the rest. (The Machine Bullshit teaser icons and Hall's infographic are the counterexamples.)
- **Width.** Text stays in the column. Figures, the transcript pair and the browser may break out to about 64rem.
- **Navigation.** Use a thin sticky bar with the page name and four or five section links, and no in-page table of contents beyond that.
- **Dark mode** follows the reader's system setting, using the same tokens.

## 4. Figures

- **Simple bars.** Horizontal stacked bars (honest / palter / lie per model) for the main result. Use a dot-and-line range plot for how each model shifts across the three conditions. No pies, 3D or dual axes.
- **Title, subtitle, caption.** The title states the takeaway. The subtitle says what is plotted, the unit and n. The caption is numbered ("Figure 2.") and opens with a bold sentence giving the result, then the one caveat that matters (Anthropic's numbered captions plus the bold lead used on research project pages).
- **Sort by the value that matters,** not alphabetically. Label values at the bar ends, and avoid gridlines.
- **Show the numbers.** Each figure has a "See the numbers" table with counts and denominators (Hall's 94/103 convention).
- **One idea per figure.** If a figure needs instructions, split it.

## 5. Examples and transcripts

Our examples are emails, so we use a reply card that borrows from Hall's case cards and Transluce's transcripts:

- **The resident's email** in a tinted block, labelled with its sender role ("Resident, Cullman").
- **What the records show,** in one dashed-border line written by us and labelled as ours.
- **The model's reply**, verbatim, with a ruled left edge and the model name. The misleading span is highlighted in yellow, with a numbered note under the card saying why it misleads ("True, but the crew was reassigned in September").
- **An honest reference reply** beside it, labelled "Written for the study, not a model output", with the key fact highlighted in blue.
- **A one-line assessment** under the pair: the judge's category and the knowledge-check answer.

Replies are copied by code, never retyped. Cuts are marked [&hellip;]. If an example was chosen because it is clear, say so and give the rate, so readers can tell typical from extreme.

## 6. The reply browser

The archive is for checking, not persuading, and it should look like a plain data table:

- filters for model, condition, office, question form and outcome, plus text search;
- one row per reply (model, office, condition, outcome) that expands to the email, the reply and the judge's explanation;
- the default view is every reply, not only flagged ones, with a count ("Showing 41 of 5,040");
- CSV and JSON downloads beside it.

## 7. Applying this to the current site

The September page (`docs/current_results_20260924/`) fails the guide in these ways. The redesign fixes each of them:

| Current | Redesign |
|---|---|
| Title "Results and reply review"; opens with a provisional-coding notice | Title is the finding or question; caveats move to Limits |
| First content is a table of counts by study phase | First content is one real example |
| Judge names (Qwen, Kimi) and run labels (`candidate_0109`) in headings and tables | Plain labels; judge details in the method section |
| No figures; every result is a table | One figure per finding, tables behind "See the numbers" |
| Reply browser defaults to flagged replies and sits in the middle of the page | Browser at the end, defaulting to all replies |
| Rounded white cards, tags and boxes throughout | One column, thin rules, no cards except the example |

The redesigned page is driven by one data file (`post_data.json`, made by `prepare_data.py` from the run outputs), so every number in the prose and figures updates when the full run is rebuilt.
