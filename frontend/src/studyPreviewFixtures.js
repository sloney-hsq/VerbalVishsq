const task = Object.freeze({
  title:'Investigate delivery time and review score evidence',
  prompt:'For delivered orders purchased in 2017 and sent to SP or RJ, assess whether delivery duration is associated with 1–5 review scores. Explain what the evidence supports, identify where the interpretation needs qualification, and cite the frozen dashboard versions used in your conclusion.',
});

const base = {remaining_ms:null,task:null,freeze_status:null,answer_status:null,evidence_refs_ready:[],allowed_actions:[],error_code:null};

export const STUDY_PREVIEW_STATES = Object.freeze({
  ready:{...base,phase:'ready',allowed_actions:['trial.start']},
  exploring:{...base,phase:'exploring',remaining_ms:487000,task,allowed_actions:['control.stop']},
  freeze_pending:{...base,phase:'answering',freeze_status:'pending',task},
  answering:{...base,phase:'answering',freeze_status:'ready',remaining_ms:142000,task,
    evidence_refs_ready:[{revision:2,artifact_id:'fixture-artifact-2'},{revision:4,artifact_id:'fixture-artifact-4'}],
    allowed_actions:['answer.save','answer.submit']},
  completed:{...base,phase:'completed',freeze_status:'ready',task,answer_status:'submitted',allowed_actions:['questionnaire.submit']},
  error:{...base,phase:'aborted',task,error_code:'synthetic_fixture_error'},
});
