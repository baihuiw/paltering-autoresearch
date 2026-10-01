# Office archive prototype

Local, authored design for review. No model experiments have been run on this pack.

- `downloads/rochester_mayor_internal.zip`: agent office records only. Extract read-only. No answer key or evaluation labels.
- `downloads/public_site_snapshot.zip`: human-readable public preview at the initial timestamp. Clearly labeled fiction for reviewers.
- `runner_pack/`: runner-owned tool-service inputs, including publication versions and mailbox alternatives. Do not give this entire folder to an agent.
- `researcher/`: question-specific evidence and scoring rules. Never exposed by tools.
- `index.html`: full design and record review.

The document archive is a representation of a managed office workspace, not a claim that a particular real office uses this storage arrangement. The ZIP is a distribution format. The current adapter is an offline prototype and is not connected to paid model runs, actual email or the internet.

Rebuild: `python3 scripts/build_office_archive_prototype.py`
Validate: `python3 -m unittest discover -s tests -p test_office_workspace.py`
