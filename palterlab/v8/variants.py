"""Email variants (v9, docs/v9/PLAN.md section 2.5): the same scenario asked in another question form.

A variant is run and scored as its own scenario id, '<scenario_id>@<question_form>', with the key's fact, evidence and
private check, and its own email and references.
"""
import copy


def expand(keys):
    """keys: {scenario_id: key}. Returns the keys plus one entry per email variant."""
    out = dict(keys)
    for sid, key in keys.items():
        for v in key.get('email_variants') or []:
            k = copy.deepcopy(key)
            vid = f"{sid}@{v['question_form']}"
            k.pop('email_variants', None)
            k['scenario_id'], k['base_scenario'] = vid, sid
            k['email'] = v['email']
            k['classification']['question_form'] = v['question_form']
            k['references'] = dict(v['references'])
            out[vid] = k
    return out
