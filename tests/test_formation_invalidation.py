import tempfile,unittest
from dataclasses import replace
from datetime import UTC,datetime
from kam_market_ai.analysis.evidence import DescriptiveEvidenceCriteria,DescriptiveEvidenceEngine
from kam_market_ai.analysis.formation_contract import FormationDraft,FormationStatus,FormationStore,FormationType
from kam_market_ai.analysis.formation_invalidation import AssessmentMethod,FormationInvalidationDraft,FormationInvalidationStore,InvalidationStatus,InvalidationType
from kam_market_ai.analysis.knowledge_contract import KnowledgeContractStore,KnowledgeDraft,KnowledgeStatus,KnowledgeType
from kam_market_ai.analysis.observation import MappedMarketEvent,ObservationFactory
from kam_market_ai.models import Instrument
from kam_market_ai.storage import ObservationQueryStore,ShadowStore

class Tests(unittest.TestCase):
 def _ready(self):
  d=tempfile.TemporaryDirectory();s=ShadowStore(f'{d.name}/x.db');s.initialize();now=datetime.now(UTC);o=ObservationFactory().from_mapped_event(MappedMarketEvent('TAIFEX',Instrument.TX,'TX',now,now,1,1,'trades'));s.save_observation(o);e=s.save_descriptive_evidence(DescriptiveEvidenceEngine(ObservationQueryStore(s.path)).summarize(DescriptiveEvidenceCriteria(symbol='TX')));k=KnowledgeContractStore(s.path).append(KnowledgeDraft(KnowledgeType.OBSERVED_KNOWLEDGE,KnowledgeStatus.CURRENT_UNDERSTANDING,'Observed','A recorded observation.',(e.evidence_family_id,),(e.evidence_id,)));event={'sequence_index':0,'entity':'TX','event_type':'STATE_CHANGE','state_before':'INITIAL','state_after':'CHANGED','observed_at':None,'source_observation_ids':(o.observation_id,),'notes':'descriptive'};condition={'condition_id':'sequence-broken','description':'Sequence no longer holds.','condition_type':'SEQUENCE_BROKEN','target_field':'transition_events','expected_state':'BROKEN','observation_requirement':'manual research','notes':'descriptive'};f=FormationStore(s.path).append(FormationDraft('Formation','A descriptive formation.',FormationType.SEQUENTIAL_FORMATION,FormationStatus.FORMING,(o.observation_id,),(e.evidence_id,),(k.knowledge_id,),(event,),invalidation_conditions=(condition,)));return d,s,o,e,k,f
 def test_exact_pinning_versioning_history_and_traceability(self):
  d,s,o,e,k,f=self._ready()
  with d:
   store=FormationInvalidationStore(s.path);draft=FormationInvalidationDraft(f.formation_id,InvalidationType.SEQUENCE_BROKEN,InvalidationStatus.PENDING_ASSESSMENT,'Sequence assessment.',('sequence-broken',),(o.observation_id,),(e.evidence_id,),(k.knowledge_id,),detected_at=datetime.now(UTC),effective_sequence_index=0,assessment_method=AssessmentMethod.SEQUENCE_REVIEW);a=store.append(draft);b=store.append(replace(draft,invalidation_status=InvalidationStatus.CONFIRMED_INVALIDATED));c=store.append(replace(draft,invalidation_status=InvalidationStatus.REVISED));self.assertEqual((a.invalidation_version,b.invalidation_version,c.invalidation_version),(1,2,3));self.assertEqual((a.previous_invalidation_id,b.previous_invalidation_id,c.previous_invalidation_id),(None,a.invalidation_id,b.invalidation_id));self.assertEqual(a.formation_id,f.formation_id);self.assertEqual(len(store.for_formation(f.formation_id)),3);self.assertEqual(store.latest(a.invalidation_family_id).invalidation_id,c.invalidation_id);self.assertEqual(store.traceability_chain(a.invalidation_id)[1].formation_id,f.formation_id)
 def test_validation_boundaries_and_no_formation_mutation(self):
  d,s,o,e,k,f=self._ready()
  with d:
   store=FormationInvalidationStore(s.path);base=FormationInvalidationDraft(f.formation_id,InvalidationType.SEQUENCE_BROKEN,InvalidationStatus.NOT_INVALIDATED,'Assessment.',('sequence-broken',),(o.observation_id,))
   self.assertRaises(LookupError,store.append,replace(base,formation_id='missing'))
   self.assertRaises(ValueError,store.append,replace(base,condition_ids=()))
   self.assertRaises(ValueError,store.append,replace(base,condition_ids=('missing',)))
   self.assertRaises(ValueError,store.append,replace(base,trigger_observation_ids=()))
   self.assertRaises(LookupError,store.append,replace(base,trigger_observation_ids=('missing',)))
   self.assertRaises(ValueError,store.append,replace(base,effective_sequence_index=2))
   result=store.append(replace(base,effective_sequence_index=None));self.assertEqual(FormationStore(s.path).get(f.formation_id).formation_status,FormationStatus.FORMING);self.assertEqual(result.effective_sequence_index,None)
if __name__=='__main__':unittest.main()
