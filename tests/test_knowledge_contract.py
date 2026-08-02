import tempfile,unittest
from dataclasses import replace
from datetime import UTC,datetime
from kam_market_ai.analysis.evidence import DescriptiveEvidenceCriteria,DescriptiveEvidenceEngine
from kam_market_ai.analysis.knowledge_contract import KnowledgeContractStore,KnowledgeDraft,KnowledgeStatus,KnowledgeType,knowledge_family_id
from kam_market_ai.analysis.observation import MappedMarketEvent,ObservationFactory
from kam_market_ai.models import Instrument
from kam_market_ai.storage import ObservationQueryStore,ShadowStore

class Tests(unittest.TestCase):
 def _ready(self):
  d=tempfile.TemporaryDirectory();s=ShadowStore(f'{d.name}/x.db');s.initialize();now=datetime.now(UTC);s.save_observation(ObservationFactory().from_mapped_event(MappedMarketEvent('TAIFEX',Instrument.TX,'TX',now,now,1,1,'trades')));e=DescriptiveEvidenceEngine(ObservationQueryStore(s.path)).summarize(DescriptiveEvidenceCriteria(symbol='TX'));saved=s.save_descriptive_evidence(e);return d,s,saved
 def test_observed_validation_identity_versioning_and_pinning(self):
  d,s,e=self._ready()
  with d:
   draft=KnowledgeDraft(KnowledgeType.OBSERVED_KNOWLEDGE,KnowledgeStatus.DRAFT,'Observed tick','TX observation count is recorded.',(e.evidence_family_id,),(e.evidence_id,),supporting_evidence_ids=(e.evidence_id,),counter_evidence_ids=(e.evidence_id,));k=KnowledgeContractStore(s.path);a=k.append(draft);b=k.append(replace(draft,status=KnowledgeStatus.REVISED));c=k.append(replace(draft,status=KnowledgeStatus.RETIRED));self.assertEqual((a.knowledge_version,b.knowledge_version,c.knowledge_version),(1,2,3));self.assertEqual((a.previous_knowledge_id,b.previous_knowledge_id,c.previous_knowledge_id),(None,a.knowledge_id,b.knowledge_id));self.assertEqual(a.source_evidence_ids,(e.evidence_id,));self.assertEqual(k.get(a.knowledge_id).statement,a.statement);self.assertEqual(len(k.history(a.knowledge_family_id)),3);self.assertEqual(knowledge_family_id(draft),knowledge_family_id(replace(draft,title='Other title')));self.assertNotEqual(knowledge_family_id(draft),knowledge_family_id(replace(draft,statement='Different statement.')));self.assertEqual(k.traceability_chain(a.knowledge_id)[1][0].evidence_id,e.evidence_id)
 def test_interpreted_and_safety_validation(self):
  d,s,e=self._ready()
  with d:
   k=KnowledgeContractStore(s.path);base=dict(status=KnowledgeStatus.CURRENT_UNDERSTANDING,title='Interpretation',statement='A descriptive interpretation is recorded.',source_evidence_family_ids=(e.evidence_family_id,),source_evidence_ids=(e.evidence_id,))
   self.assertRaises(ValueError,k.append,KnowledgeDraft(KnowledgeType.OBSERVED_KNOWLEDGE,**base,interpretation='why'))
   self.assertRaises(ValueError,k.append,KnowledgeDraft(KnowledgeType.INTERPRETED_KNOWLEDGE,**base))
   observed=k.append(KnowledgeDraft(KnowledgeType.OBSERVED_KNOWLEDGE,**base));interpreted=k.append(KnowledgeDraft(KnowledgeType.INTERPRETED_KNOWLEDGE,**base,interpretation='This is an interpretation, not a truth claim.',interpretation_evidence_ids=(e.evidence_id,),interprets_knowledge_ids=(observed.knowledge_id,)));self.assertEqual(interpreted.knowledge_type,KnowledgeType.INTERPRETED_KNOWLEDGE)
   self.assertRaises(LookupError,k.append,replace(KnowledgeDraft(KnowledgeType.OBSERVED_KNOWLEDGE,**base),source_evidence_ids=('missing',)))
   self.assertRaises(ValueError,k.append,replace(KnowledgeDraft(KnowledgeType.OBSERVED_KNOWLEDGE,**base),title='BUY now'))
if __name__=='__main__':unittest.main()
