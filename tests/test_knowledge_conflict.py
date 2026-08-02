import tempfile,unittest
from dataclasses import replace
from datetime import UTC,datetime
from kam_market_ai.analysis.evidence import DescriptiveEvidenceCriteria,DescriptiveEvidenceEngine
from kam_market_ai.analysis.knowledge_conflict import ConflictType,KnowledgeConflictDraft,KnowledgeConflictStore,conflict_family_id
from kam_market_ai.analysis.knowledge_contract import KnowledgeContractStore,KnowledgeDraft,KnowledgeStatus,KnowledgeType
from kam_market_ai.analysis.observation import MappedMarketEvent,ObservationFactory
from kam_market_ai.models import Instrument
from kam_market_ai.storage import ObservationQueryStore,ShadowStore
class Tests(unittest.TestCase):
 def _ready(self):
  d=tempfile.TemporaryDirectory();s=ShadowStore(f'{d.name}/x.db');s.initialize();now=datetime.now(UTC);s.save_observation(ObservationFactory().from_mapped_event(MappedMarketEvent('TAIFEX',Instrument.TX,'TX',now,now,1,1,'trades')));e=s.save_descriptive_evidence(DescriptiveEvidenceEngine(ObservationQueryStore(s.path)).summarize(DescriptiveEvidenceCriteria(symbol='TX')));k=KnowledgeContractStore(s.path);a=k.append(KnowledgeDraft(KnowledgeType.OBSERVED_KNOWLEDGE,KnowledgeStatus.CURRENT_UNDERSTANDING,'A','A observed.',(e.evidence_family_id,),(e.evidence_id,)));b=k.append(KnowledgeDraft(KnowledgeType.INTERPRETED_KNOWLEDGE,KnowledgeStatus.DRAFT,'B','B interpreted.',(e.evidence_family_id,),(e.evidence_id,),interpretation='Description.',interpretation_evidence_ids=(e.evidence_id,),interprets_knowledge_ids=(a.knowledge_id,)));return d,k,a,b
 def test_append_identity_history_and_traceability(self):
  d,k,a,b=self._ready()
  with d:
   store=KnowledgeConflictStore(k.path);draft=KnowledgeConflictDraft((b.knowledge_id,a.knowledge_id),ConflictType.INTERPRETATION_CONFLICT,'Declared difference.');v1=store.append(draft);v2=store.append(draft);self.assertEqual(v1.knowledge_ids,tuple(sorted((a.knowledge_id,b.knowledge_id))));self.assertEqual((v1.conflict_version,v2.conflict_version),(1,2));self.assertEqual(v2.previous_conflict_id,v1.conflict_id);self.assertEqual(store.latest(v1.conflict_family_id).conflict_id,v2.conflict_id);self.assertEqual(len(store.traceability_chain(v1.conflict_id)[1]),2)
 def test_validation_and_retired_pinning(self):
  d,k,a,b=self._ready()
  with d:
   store=KnowledgeConflictStore(k.path);self.assertRaises(ValueError,store.append,KnowledgeConflictDraft((a.knowledge_id,),ConflictType.UNSPECIFIED_CONFLICT,'x'));self.assertRaises(ValueError,store.append,KnowledgeConflictDraft((a.knowledge_id,a.knowledge_id),ConflictType.UNSPECIFIED_CONFLICT,'x'));self.assertRaises(LookupError,store.append,KnowledgeConflictDraft((a.knowledge_id,'missing'),ConflictType.UNSPECIFIED_CONFLICT,'x'));retired=k.append(replace(a,status=KnowledgeStatus.RETIRED));r=store.append(KnowledgeConflictDraft((retired.knowledge_id,b.knowledge_id),ConflictType.UNSPECIFIED_CONFLICT,'Historical comparison.'));self.assertIn(retired.knowledge_id,r.knowledge_ids)
if __name__=='__main__':unittest.main()
