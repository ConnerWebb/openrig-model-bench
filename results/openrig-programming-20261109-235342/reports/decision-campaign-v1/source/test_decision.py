import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from policy import select,choose_reviewer,choose_parallel,choose_workflow
from boundary import safe_boundary

HERE=Path(__file__).resolve().parent
PLAN=json.loads((HERE/'plan.json').read_bytes())

def row(model,task,passed=True,seconds=60,**extra):
    return dict(id=f'solo-{model}-{task}-s42-h5.5',harness_revision='h5.5',phase='solo',
                task=task,language='python' if task.startswith('py-') else 'cpp',seed=42,
                variant=0,models={'developer':model},topology=1,finished=time.time()-5,
                resource_limited=False,complete=passed,seconds=seconds,**extra)

class PolicyTests(unittest.TestCase):
    def test_balanced_selection_ignores_extra_tasks_and_other_revisions(self):
        rows=[row(k,t,seconds=60+10*i) for i,k in enumerate(PLAN['models']) for t in PLAN['balanced_tasks']]
        extra=row('next','py-archive',False);rows.append(extra)
        old=row('next','py-csv',False);old['harness_revision']='h5.4';rows.append(old)
        s=select(rows,PLAN)
        self.assertEqual(s['shortlist'],PLAN['models'][:3])
        self.assertTrue(s['balanced_complete'])
        self.assertEqual(s['ranked_eligible'][0]['accepted'],4)

    def test_missing_interrupted_and_resource_rows_do_not_qualify(self):
        rows=[row(k,t) for k in PLAN['models'] for t in PLAN['balanced_tasks']]
        rows[0]['interrupted']=True
        rows[4]['resource_limited']=True
        s=select(rows,PLAN)
        self.assertNotIn('next',[r['model'] for r in s['ranked_eligible']])
        self.assertNotIn('coder30',[r['model'] for r in s['ranked_eligible']])
        self.assertIn('next',s['shortlist'],'Baseline retained as explicitly labeled control')
        self.assertFalse(s['balanced_complete'])

    def test_duplicate_balanced_cell_rejected(self):
        r=row('next','py-csv')
        with self.assertRaises(ValueError):select([r,r],PLAN)

    def test_reviewer_requires_both_correct_and_defective_judgments(self):
        probes=[]
        for model in ['next','coder30']:
            for correct in [True,False]:
                probes.append(dict(model=model,task='cpp-binary',harness_revision='h5.5',correct_patch=correct,state='complete',correct_decision=True,approved=correct,seconds=30))
        self.assertEqual(choose_reviewer(probes,['next','coder30'],'cpp','next'),'coder30')
        probes[-1].update(approved=True,correct_decision=False)
        self.assertEqual(choose_reviewer(probes,['next','coder30'],'cpp','next'),'next')

    def test_parallel_requires_three_good_repetitions_and_meaningful_gain(self):
        batches=[dict(slots=s,seed=seed,concurrent_jobs=2,accepted=2,resource_limited=False,seconds=duration) for s,duration in [(1,100),(2,90)] for seed in [42,43,44]]
        self.assertEqual(choose_parallel(batches)['slots'],1)
        batches += [dict(slots=3,seed=seed,concurrent_jobs=2,accepted=2,resource_limited=False,seconds=60) for seed in [42,43,44]]
        self.assertEqual(choose_parallel(batches)['slots'],3)
        batches[-1]['resource_limited']=True
        self.assertEqual(choose_parallel(batches)['slots'],1)

    def test_missing_sequential_control_forbids_parallel_recommendation(self):
        batches=[dict(slots=3,seed=seed,concurrent_jobs=2,accepted=2,resource_limited=False,seconds=60) for seed in [42,43,44]]
        self.assertFalse(choose_parallel(batches)['qualified'])

    def test_workflow_comparison_uses_declared_cells_only(self):
        a=row('next','py-queue');b=row('next','py-csv',False)
        expected={'python':{'solo':[a['id']]}}
        choice=choose_workflow([a,b],expected,'python')
        self.assertEqual(choice['accepted'],1)
        self.assertEqual(choice['total'],1)

class BoundaryTests(unittest.TestCase):
    def test_waits_for_final_resource_flag_and_all_archived_seats(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);case=out/'runs/fixture';case.mkdir(parents=True)
            (out/'campaign-status.json').write_text(json.dumps({'current':'fixture'}))
            (case/'rig.yaml').write_text(json.dumps({'pods':[{'members':[{'id':'developer'}]}]}))
            r=row('next','py-csv');del r['resource_limited']
            (case/'result.json').write_text(json.dumps(r));(case/'native-final.json').write_text('{}')
            self.assertFalse(safe_boundary(out,'fixture'))
            r['resource_limited']=False;(case/'result.json').write_text(json.dumps(r))
            self.assertFalse(safe_boundary(out,'fixture'))
            (case/'transcripts/developer').mkdir(parents=True)
            self.assertTrue(safe_boundary(out,'fixture'))
            (out/'campaign-status.json').write_text(json.dumps({'current':'new-case'}))
            self.assertFalse(safe_boundary(out,'fixture'),'Race to a new admission must resume, not stop it')

class DispatchTests(unittest.TestCase):
    def setUp(self):
        # Importing the frozen runtime declares functions only. Every inference,
        # service and reporting entry point is replaced before any execution.
        import dispatch
        self.d=dispatch
        self.temp=tempfile.TemporaryDirectory();self.out=Path(self.temp.name)
        (self.out/'runs').mkdir();(self.out/'role-probes').mkdir()
        self.state=self.out/'state';self.state.mkdir()
        self.calls=[];self.profiles=[];self.patches=[]
        self.replace(self.d,'OUTPUT',self.out);self.replace(self.d,'STATE',self.state)
        self.replace(self.d.decision_report,'write_report',lambda **k:{})
        self.replace(self.d.m,'execute',self.execute)
        self.replace(self.d.m,'healthy_wait',lambda:None)
        self.replace(self.d.m,'status',lambda *a,**k:None)
        self.replace(self.d.m,'archive_db',lambda *a:None)
        self.replace(self.d.m,'checkpoint',lambda *a:'fixture-checkpoint')
        self.replace(self.d.m,'own_memory_reset',lambda:None)
        self.replace(self.d.m,'set_profile',self.set_profile)
        self.replace(self.d.m,'capture_runtime',lambda *a:None)
        self.replace(self.d.m,'STOP',threading.Event())
        self.replace(self.d.m,'ACTIVE',{})
        self.replace(self.d.m,'init_services',lambda:None)
        self.replace(self.d.m,'monitor',lambda:None)
        self.replace(self.d.m,'event',lambda *a,**k:None)
        self.replace(self.d.m,'native',lambda *a,**k:{})
        self.replace(self.d.subprocess,'run',lambda *a,**k:None)
        self.replace(self.d.m,'role_probe',self.role)
        self.replace(self.d.m,'planner_probe',lambda *a:dict(state='complete',plan=['Implement and test']))
        self.replace(self.d.m,'direct_batch',lambda key,slots,ctx,seed:dict(id=f'fixture-{key}-{slots}-{ctx}-{seed}'))
        self.set_profile(1,1,32768)

    def replace(self,obj,key,value):
        p=patch.object(obj,key,value);p.start();self.patches.append(p)

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def set_profile(self,slots,resident,context):
        self.profiles.append(slots)
        self.d.m.atomic(self.out/'inference-profile.json',dict(slots=slots,resident=resident,context=context))

    def execute(self,id,task,models,seed,topology,variant,phase):
        self.calls.append((id,task,models,seed,topology,variant,phase))
        r=dict(id=id+'-h5.5',harness_revision='h5.5',task=task,language='python' if task.startswith('py-') else 'cpp',models=models,seed=seed,variant=variant,phase=phase,topology=topology,finished=time.time(),complete=True,resource_limited=False,seconds=1800 if phase=='soak' else 60)
        self.d.m.atomic(self.out/'runs'/r['id']/'result.json',r)
        return r

    def role(self,model,task,correct):
        r=dict(model=model,task=task,correct_patch=correct,harness_revision='h5.5',state='complete',approved=correct,correct_decision=True,seconds=30)
        self.d.m.atomic(self.out/'role-probes'/f'{model}-{task}-{correct}'/'result.json',r)
        return r

    def test_reuses_completed_cells_without_overwriting_or_inference(self):
        c=self.d.Campaign();r=row('next','py-csv',False)
        path=self.out/'runs'/r['id']/'result.json';self.d.m.atomic(path,r);before=path.read_bytes()
        c.case('solo-next-py-csv-s42','py-csv',{'developer':'next'})
        self.assertEqual(path.read_bytes(),before);self.assertEqual(self.calls,[])

    def test_admission_deadline_does_not_start_new_trial(self):
        c=self.d.Campaign();c.window['deadline']=time.time()-1
        with self.assertRaises(self.d.BudgetDone):c.case('new','py-csv',{'developer':'next'})
        self.assertEqual(self.calls,[])

    def test_partial_parallel_batch_restarts_both_fresh_jobs(self):
        c=self.d.Campaign();folder=self.out/'parallel-jobs/decision-v1-solo-next-p1-s42';folder.mkdir(parents=True)
        self.d.m.atomic(folder/'attempt-old.json',dict(case_prefix='old-partial'))
        result=c.batch('next',1,42)
        self.assertEqual(len(self.calls),2)
        self.assertTrue(all('-a' in r[0] for r in self.calls))
        self.assertEqual(result['accepted'],2)
        self.assertLess(result['seconds'],sum(60 for _ in self.calls))
        c.batch('next',1,42);self.assertEqual(len(self.calls),2,'Finished whole batches may be reused')

    def test_full_finite_dispatch_with_no_real_tools_or_models(self):
        # Simulate all phases. Stability gets exactly two 30-minute fake batches.
        actual_batch=self.d.Campaign.batch
        def timed_batch(c,key,slots,seed,phase='parallel-jobs',stability_index=None):
            result=actual_batch(c,key,slots,seed,phase,stability_index)
            result['seconds']=1800 if phase=='soak' else 100
            return result
        with patch.object(self.d.Campaign,'batch',timed_batch):
            self.d.run()
        marker=json.loads((self.out/'COMPLETED.json').read_bytes())
        self.assertEqual(marker['outcome'],'completed_shortened_scope')
        self.assertFalse(marker['full_original_matrix_complete'])
        self.assertEqual(sum(r[-1]=='solo' and r[3]==42 for r in self.calls),48)
        self.assertEqual(len(list((self.out/'role-probes').glob('*/result.json'))),12)
        direct=json.loads((self.state/'direct-index.json').read_bytes())
        self.assertEqual(len(direct),12)
        parallel=json.loads((self.state/'parallel-choice.json').read_bytes())
        self.assertEqual(parallel['slots'],1,'Tiny fixture timing changes must not qualify unsupported concurrency')
        stability=json.loads((self.state/'stability.json').read_bytes())
        self.assertTrue(stability['complete']);self.assertEqual(stability['exercised_seconds'],3600)

if __name__=='__main__':unittest.main(verbosity=2)
