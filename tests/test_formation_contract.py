import tempfile,unittest
from dataclasses import replace
from datetime import UTC,datetime
from kam_market_ai.analysis.evidence import DescriptiveEvidenceCriteria,DescriptiveEvidenceEngine
from kam_market_ai.analysis.formation_contract import FormationDraft,FormationStatus,FormationStore,FormationType
from kam_market_ai.analysis.knowledge_contract import KnowledgeContractStore,KnowledgeDraft,KnowledgeStatus,KnowledgeType
from kam_market_ai.analysis.observation import MappedMarketEvent,ObservationFactory
from kam_market_ai.models import Instrument
from kam_market_ai.storage import ObservationQueryStore,ShadowStore

class Tests(unittest.TestCase):
 def _ready(self):
  d=tempfile.TemporaryDirectory();s=ShadowStore(f'{d.name}/x.db');s.initialize();now=datetime.now(UTC);o=ObservationFactory().from_mapped_event(MappedMarketEvent('TAIFEX',Instrument.TX,'TX',now,now,1,1,'trades'));s.save_observation(o);e=s.save_descriptive_evidence(DescriptiveEvidenceEngine(ObservationQueryStore(s.path)).summarize(DescriptiveEvidenceCriteria(symbol='TX')));k=KnowledgeContractStore(s.path);knowledge=k.append(KnowledgeDraft(KnowledgeType.OBSERVED_KNOWLEDGE,KnowledgeStatus.CURRENT_UNDERSTANDING,'Observed','A recorded observation.',(e.evidence_family_id,),(e.evidence_id,)));event={'sequence_index':0,'entity':'TX','event_type':'STATE_CHANGE','state_before':'INITIAL','state_after':'CHANGED','observed_at':None,'source_observation_ids':(o.observation_id,),'notes':'descriptive'};draft=FormationDraft('Formation','A descriptive formation sequence.',FormationType.SEQUENTIAL_FORMATION,FormationStatus.FORMING,(o.observation_id,),(e.evidence_id,),(knowledge.knowledge_id,),(event,),initial_state='INITIAL',result_state='RESULT',lead_entities=('TX',),lag_entities=('TMF',),timing_relationships=({'lead_entity':'TX','lag_entity':'TMF','delay_value':127,'delay_unit':'MILLISECONDS','basis':'EXCHANGE_EVENT_TIME','source_observation_ids':(o.observation_id,)},),persistence_state={'classification':'TRANSIENT','duration_value':1,'duration_unit':'EVENTS','event_count':1,'notes':'descriptive'});return d,s,o,e,knowledge,draft
 def test_sources_sequence_versions_and_traceability(self):
  d,s,o,e,k,draft=self._ready()
  with d:
   store=FormationStore(s.path);a=store.append(draft);b=store.append(replace(draft,formation_status=FormationStatus.PERSISTING));c=store.append(replace(draft,formation_status=FormationStatus.COMPLETED));self.assertEqual((a.formation_version,b.formation_version,c.formation_version),(1,2,3));self.assertEqual((a.previous_formation_id,b.previous_formation_id,c.previous_formation_id),(None,a.formation_id,b.formation_id));self.assertEqual(a.source_observation_ids,(o.observation_id,));self.assertEqual(a.source_evidence_ids,(e.evidence_id,));self.assertEqual(a.source_knowledge_ids,(k.knowledge_id,));self.assertEqual([x.formation_version for x in store.history(a.formation_family_id)],[1,2,3]);self.assertEqual(store.latest(a.formation_family_id).formation_id,c.formation_id);self.assertEqual(a.transition_events[0]['observed_at'],None);self.assertEqual(a.payload(),store.get(a.formation_id).payload())
 def test_validation_invalidation_and_source_immutability(self):
  d,s,o,e,k,draft=self._ready()
  with d:
   store=FormationStore(s.path);self.assertRaises(ValueError,store.append,replace(draft,source_observation_ids=(),source_evidence_ids=(),source_knowledge_ids=()))
   self.assertRaises(LookupError,store.append,replace(draft,source_observation_ids=('missing',)))
   self.assertRaises(ValueError,store.append,replace(draft,transition_events=()))
   bad=dict(draft.transition_events[0]);bad['sequence_index']=1;self.assertRaises(ValueError,store.append,replace(draft,transition_events=(bad,)))
   self.assertRaises(ValueError,store.append,replace(draft,formation_status=FormationStatus.INVALIDATED))
   invalid=store.append(replace(draft,formation_status=FormationStatus.INVALIDATED,invalidation_conditions=({'condition_id':'x','description':'manual','condition_type':'MANUAL_RESEARCH_CONDITION','target_field':'state','expected_state':'missing','observation_requirement':'manual','notes':'descriptive'},)));self.assertEqual(invalid.formation_status,FormationStatus.INVALIDATED)
   self.assertRaises(ValueError,store.append,replace(draft,timing_relationships=({'delay_unit':'BAD','basis':'EXCHANGE_EVENT_TIME'},)))
if __name__=='__main__':unittest.main()
