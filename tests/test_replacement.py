import unittest
from palterlab.staged import audit_pool,trial_scope_matches,discovery_models
class ReplacementTests(unittest.TestCase):
 def test_primary_audit_excludes_retained_and_unfinished_replies(self):
  def row(model,phase='search',status='completed'):
   return {'model':model,'phase':phase,'status':status}
  rows=[row('gemma27'),row('nemotron30'),row('llama8'),row('sonnet','transfer'),row('nemotron30',status='generation_failed')]
  selected=audit_pool(rows,['llama8','nemotron30'])
  self.assertEqual([r['model'] for r in selected],['nemotron30','llama8'])
 def test_replacement_requires_recomputing_old_summary(self):
  x={'status':'evaluated','scoring_models':['llama8','qwen9','deepseek'],'score_version':'graded_v2_qwen_only'}
  active=['llama8','nemotron30','qwen9','deepseek']
  self.assertFalse(trial_scope_matches(x,active,'graded_v2_qwen_only'))
  self.assertEqual(discovery_models({'search_models':active,'retained_search_models':['gemma27'],'deferred_search_models':[]}),active)
