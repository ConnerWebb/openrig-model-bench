"""Smaller finite dispatch importing the unchanged h5.5 runtime."""
import concurrent.futures
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import traceback

HERE=Path(__file__).resolve().parent
PLAN=json.loads((HERE/'plan.json').read_bytes())
OUTPUT=Path(PLAN['output']);STATE=OUTPUT/'progress/decision-campaign-v1/state'
# Import our own report before the frozen runtime's report module occupies that name.
spec=importlib.util.spec_from_file_location('decision_report',HERE/'report.py')
decision_report=importlib.util.module_from_spec(spec);spec.loader.exec_module(decision_report)
from policy import select,choose_reviewer,profiles,choose_workflow,choose_parallel
sys.path.insert(0,PLAN['harness_path'])
import main as m

original_status=m.status
def dispatch_status(phase,**values):
    values.update(dispatch=PLAN['id'],dispatch_plan='shortened-decision-campaign-v1')
    return original_status(phase,**values)
m.status=dispatch_status

class BudgetDone(Exception):
    pass

class Campaign:
    def __init__(self):
        self.save_lock=threading.RLock()
        STATE.mkdir(parents=True,exist_ok=True)
        window=STATE/'admission-window.json'
        if not window.exists():m.atomic(window,dict(started=time.time(),deadline=time.time()+PLAN['admission_hours']*3600))
        self.window=json.loads(window.read_bytes())
        self.progress=json.loads((STATE/'progress.json').read_bytes()) if (STATE/'progress.json').exists() else {}

    def save(self,**values):
        with self.save_lock:
            self.progress.update(values,at=time.time(),dispatch=PLAN['id'],harness_revision='h5.5',deadline=self.window['deadline'])
            m.atomic(STATE/'progress.json',self.progress)
            decision_report.write_report()

    def admit(self):
        if time.time()>=self.window['deadline']:
            raise BudgetDone('36-hour admission window reached; active trials were allowed to finish.')

    def phase(self,phase,**extra):
        self.save(phase=phase,**extra)
        m.status(phase,dispatch=PLAN['id'],**extra)

    def case(self,id,task,models,seed=42,topology=1,variant=0,phase='solo',reserved=False):
        path=OUTPUT/'runs'/(id+'-h5.5')/'result.json'
        if path.exists():
            row=json.loads(path.read_bytes())
            if row.get('finished') and not row.get('interrupted') and 'resource_limited' in row:
                return row
        if not reserved:self.admit()
        row=m.execute(id,task,models,seed,topology,variant,phase)
        self.save(last_finished=row['id'])
        return row

    def profile(self,slots=1):
        self.admit()
        previous=json.loads((OUTPUT/'inference-profile.json').read_bytes())
        if (previous['slots'],previous['resident'],previous['context'])!=(slots,1,32768) or m.STOP.is_set():
            assert not m.ACTIVE,'No profile change with active trial'
            m.archive_db('decision-before-profile-'+str(slots))
            backup=m.checkpoint('decision-before-profile-'+str(slots))
            m.atomic(STATE/('profile-checkpoint-'+str(time.time_ns())+'.json'),dict(backup=backup,previous=previous,next_slots=slots))
        m.own_memory_reset()
        m.set_profile(slots,1,32768)

    def balanced(self):
        self.phase('decision-balanced-screen')
        for model in PLAN['models']:
            for task in PLAN['balanced_tasks']:
                self.case(f'solo-{model}-{task}-s42',task,{'developer':model})
        selection=select(decision_report.load_rows(OUTPUT),PLAN)
        m.atomic(STATE/'selection.json',selection)
        self.save(balanced_finished=48,shortlist=selection['shortlist'])
        return selection

    def roles(self,selection):
        self.phase('decision-focused-roles')
        roster=selection['shortlist']
        for model in roster:
            for task in ['py-refactor','cpp-binary']:
                for correct in [True,False]:
                    self.admit();m.role_probe(model,task,correct)
        probes=[json.loads(p.read_bytes()) for p in (OUTPUT/'role-probes').glob('*/result.json')]
        reviewers={lang:choose_reviewer(probes,roster,lang,dev) for lang,dev in selection['developer_by_language'].items()}
        leaders={}
        for lang,dev in selection['developer_by_language'].items():
            task=PLAN['comparison_tasks'][lang];self.admit();r=m.planner_probe(dev,task)
            leaders[lang]=dev if r.get('state')=='complete' and r.get('plan') else PLAN['retain_baseline']
        role_data=dict(reviewers=reviewers,leaders=leaders,note='Reviewers must correctly judge both correct and defective fixtures; different qualified reviewer preferred for the mixed comparison. If none qualifies, developer is the unqualified fallback and no specialist quality claim is made. Planning is protocol-only; Coder-Next is fallback.')
        m.atomic(STATE/'role-selection.json',role_data)
        return profiles(selection,reviewers,leaders)

    def teams(self,configurations):
        self.phase('decision-focused-teams')
        expected={};aliases={}
        # Declare the whole matched comparison before any new team outcome.
        for lang,configs in configurations.items():
            expected[lang]={};seen={}
            for label,config in configs.items():
                signature=json.dumps(config,sort_keys=True)
                if signature in seen:
                    expected[lang][label]=expected[lang][seen[signature]];aliases[lang+'/'+label]=seen[signature];continue
                seen[signature]=label;ids=[]
                for seed in PLAN['comparison_seeds']:
                    id=(f"solo-{config['models']['developer']}-{PLAN['comparison_tasks'][lang]}-s{seed}" if label=='solo' else f'decision-v1-{lang}-{label}-s{seed}')
                    ids.append(id+'-h5.5')
                expected[lang][label]=ids
        manifest=dict(profiles=configurations,case_ids=expected,identical_profile_aliases=aliases,seeds=PLAN['comparison_seeds'],variant=0,notes='Same task/seed/variant per profile. Solo control has no reviewer; all final acceptance remains private and unchanged. Duplicated identical profiles reuse the same evidence, never count as independent repetitions.')
        m.atomic(STATE/'comparison-plan.json',manifest)
        completed=set()
        for lang,configs in configurations.items():
            for label,config in configs.items():
                for seed,id in zip(PLAN['comparison_seeds'],expected[lang][label]):
                    if id in completed:continue
                    self.case(id.removesuffix('-h5.5'),PLAN['comparison_tasks'][lang],config['models'],seed,config['topology'],0,'solo' if label=='solo' else 'teams')
                    completed.add(id)
        winners={lang:choose_workflow(decision_report.load_rows(OUTPUT),expected,lang) for lang in configurations}
        m.atomic(STATE/'workflow-results.json',winners)
        return winners

    def direct(self,selection):
        key=selection['ranked_eligible'][0]['model']
        self.phase('decision-direct-concurrency',model=key)
        index=[]
        for slots in PLAN['direct_slots']:
            self.profile(slots)
            for seed in PLAN['direct_seeds']:
                self.admit();m.healthy_wait();r=m.direct_batch(key,slots,32768,seed)
                index.append(dict(id=r['id'],model=key,slots=slots,seed=seed,harness_revision='h5.5'))
                m.atomic(STATE/'direct-index.json',index)
            m.capture_runtime(f'decision-v1-direct-{key}-p{slots}')
        return key

    def batch(self,key,slots,seed,phase='parallel-jobs',stability_index=None):
        label=(f'decision-v1-solo-{key}-p{slots}-s{seed}' if stability_index is None else f'decision-v1-stability-{stability_index}')
        folder=OUTPUT/'parallel-jobs'/label;folder.mkdir(parents=True,exist_ok=True)
        if (folder/'result.json').exists():return json.loads((folder/'result.json').read_bytes())
        self.admit();m.healthy_wait();self.admit();begin=time.time()
        attempt=str(time.time_ns())
        m.atomic(folder/('attempt-'+attempt+'.json'),dict(started=begin,case_prefix=label+'-a'+attempt,note='An interrupted batch is retained; a fresh attempt reruns both jobs so cached work never inflates batch throughput.'))
        def call(i):
            # Work is identical across slot counts: two independent solo jobs,
            # one per language, with unchanged seed/variant and fixed acceptance.
            return self.case(label+'-a'+attempt+'-'+str(i),'py-csv' if i==0 else 'cpp-buffer',{'developer':key},seed,1,300+i,phase,reserved=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            rows=list(pool.map(call,range(2)))
        elapsed=time.time()-begin
        r=dict(id=label,dispatch=PLAN['id'],harness_revision='h5.5',models={'developer':key},slots=slots,max_loaded_models=1,concurrent_jobs=2,seed=seed,seconds=elapsed,accepted=sum(bool(r['complete']) for r in rows),accepted_tasks_per_hour=sum(bool(r['complete']) for r in rows)*3600/max(elapsed,.001),resource_limited=any(r.get('resource_limited') for r in rows) or m.STOP.is_set(),case_ids=[r['id'] for r in rows],per_language={l:dict(accepted=sum(r['language']==l and r['complete'] for r in rows),attempts=sum(r['language']==l for r in rows)) for l in ['python','cpp']})
        m.atomic(folder/'result.json',r)
        return r

    def parallel(self,key):
        self.phase('decision-guarded-concurrency',model=key)
        batches=[]
        for slots in PLAN['guarded_slots']:
            self.profile(slots)
            for seed in PLAN['guarded_seeds']:
                batches.append(self.batch(key,slots,seed))
            m.capture_runtime(f'decision-v1-guarded-{key}-p{slots}')
        choice=choose_parallel(batches)
        choice.update(model=key,note='This is actual two-job solo workflow throughput. Team comparisons remain separate. Requested slot counts require the saved runtime runner evidence to claim GPU overlap.')
        m.atomic(STATE/'parallel-choice.json',choice)
        return choice

    def stability(self,key,choice):
        self.phase('decision-stability')
        window=STATE/'stability-window.json'
        if not window.exists():m.atomic(window,dict(started=time.time(),target_exercised_seconds=PLAN['stability_seconds']))
        items=[];index=0
        self.profile(choice['slots'])
        while sum(b['seconds'] for b in items)<PLAN['stability_seconds']:
            self.admit();batch=self.batch(key,choice['slots'],[42,43,44][index%3],'soak',index)
            items.append(batch);index+=1
            m.atomic(STATE/'stability.json',dict(requested_seconds=PLAN['stability_seconds'],exercised_seconds=sum(b['seconds'] for b in items),started=json.loads(window.read_bytes())['started'],last_at=time.time(),batches=len(items),accepted=sum(b['accepted'] for b in items),attempted=2*len(items),resource_limited=any(b['resource_limited'] for b in items),complete=sum(b['seconds'] for b in items)>=PLAN['stability_seconds'],note='One hour of completed batch work, excluding downtime. Focused stability check; not the original six-hour soak or restart-recovery certification.'))

def run():
    if (OUTPUT/'COMPLETED.json').exists():return
    lock=(OUTPUT/'campaign.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    campaign=Campaign()
    try:
        m.init_services();threading.Thread(target=m.monitor,daemon=True).start()
        campaign.profile(1)
        outcome='completed_shortened_scope'
        try:
            selection=campaign.balanced();configurations=campaign.roles(selection)
            campaign.teams(configurations);key=campaign.direct(selection)
            choice=campaign.parallel(key);campaign.stability(key,choice)
        except BudgetDone as exc:
            outcome='admission_limit_reached';campaign.save(stop_reason=str(exc))
        campaign.save(phase='complete',outcome=outcome,full_original_matrix_complete=False)
        m.status('complete',dispatch=PLAN['id'],outcome=outcome)
        decision_report.write_report(final=True)
        m.archive_db('decision-v1-final');backup=m.checkpoint('decision-v1-final')
        m.atomic(OUTPUT/'COMPLETED.json',dict(at=time.time(),harness_revision='h5.5',dispatch=PLAN['id'],scope='shortened decision campaign',outcome=outcome,full_original_matrix_complete=False,final_checkpoint=backup,report=str(OUTPUT/'FINAL-COMPARISON.txt'),no_production_promotion=True))
        m.event('campaign_complete',dispatch=PLAN['id'],outcome=outcome)
        subprocess.run(['systemctl','--user','disable',m.P['unit']+'.service'],capture_output=True)
    except (SystemExit,KeyboardInterrupt):
        raise
    except Exception as exc:
        m.atomic(OUTPUT/'ATTENTION.json',dict(at=time.time(),dispatch=PLAN['id'],error=str(exc),traceback=traceback.format_exc(),note='Preserved for investigation. No production changes.'))
        m.status('needs_attention',dispatch=PLAN['id'],error=str(exc));raise SystemExit(78)
    finally:
        subprocess.run(['systemctl','--user','stop',m.INFER_UNIT],capture_output=True)
        try:m.native('daemon','stop',timeout=90)
        except Exception:pass
        lock.close()

if __name__=='__main__':
    signal.signal(signal.SIGTERM,m.request_stop);signal.signal(signal.SIGINT,m.request_stop)
    run()
