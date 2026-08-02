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
  d=tempfile.TemporaryDirectory();s=ShadowStore(f'{d.name}/x.db');s.initialize();now=datetime.now(UTC);s.save_observation(ObservationFactory().from_mapped_event(MappedMarketEvent('TAIFEX',Instrument.TX,'TX',now,now,1,1,'trades')));e=s.save_descriptive_evidence(DescriptiveEvidenceEngine(ObservationQueryStore(s.path)).summarize(DescriptiveEvidenceCriteria(symbol='TX')));k=KnowledgeContractStore(s.path);base=KnowledgeDraft(KnowledgeType.OBSERVED_KNOWLEDGE,KnowledgeStatus.CURRENT_UNDERSTANDING,'Observed','A recorded observation.',(e.evidence_family_id,),(e.evidence_id,));return d,k,e,k.append(base),base
 def test_exact_observed_pinning_validation_and_identity(self):
  d,k,e,observed,base=self._ready()
  with d:
   self.assertEqual(observed.interprets_knowledge_ids,())
   draft=KnowledgeDraft(KnowledgeType.INTERPRETED_KNOWLEDGE,KnowledgeStatus.DRAFT,'Interpreted','An interpretation is recorded.',(e.evidence_family_id,),(e.evidence_id,),interpretation='Descriptive interpretation only.',interpretation_evidence_ids=(e.evidence_id,),interprets_knowledge_ids=(observed.knowledge_id,))
   i=k.append(draft);self.assertEqual(i.interprets_knowledge_ids,(observed.knowledge_id,));self.assertEqual(k.traceability_chain(i.knowledge_id)[1][0].evidence_id,e.evidence_id)
   self.assertRaises(ValueError,k.append,replace(draft,interprets_knowledge_ids=()))
   self.assertRaises(ValueError,k.append,replace(draft,interprets_knowledge_ids=(i.knowledge_id,)))
   self.assertRaises(ValueError,k.append,replace(draft,interprets_knowledge_ids=(observed.knowledge_id,observed.knowledge_id)))
   observed_v2=k.append(replace(base,status=KnowledgeStatus.REVISED));i2=k.append(replace(draft,status=KnowledgeStatus.REVISED,interpretation='Revised description.'))
   self.assertEqual(i.interprets_knowledge_ids,(observed.knowledge_id,));self.assertEqual(i.knowledge_family_id,i2.knowledge_family_id);self.assertNotEqual(observed_v2.knowledge_id,observed.knowledge_id)
 def test_retired_observed_cannot_be_newly_pinned(self):
  d,k,e,observed,base=self._ready()
  with d:
   retired=k.append(replace(base,status=KnowledgeStatus.RETIRED));draft=KnowledgeDraft(KnowledgeType.INTERPRETED_KNOWLEDGE,KnowledgeStatus.DRAFT,'Interpreted','No causal claim.',(e.evidence_family_id,),(e.evidence_id,),interpretation='Description only.',interpretation_evidence_ids=(e.evidence_id,),interprets_knowledge_ids=(retired.knowledge_id,));self.assertRaises(ValueError,k.append,draft)
if __name__=='__main__':unittest.main()
