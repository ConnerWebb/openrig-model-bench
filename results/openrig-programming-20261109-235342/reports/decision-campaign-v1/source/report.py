"""Decision report; matched cells only for selection. No inference or controls."""
import json
from pathlib import Path
import time
from policy import select

HERE=Path(__file__).resolve().parent

def load_rows(output):
    rows=[]
    for path in sorted((output/'runs').glob('*/result.json')):
        row=json.loads(path.read_bytes())
        if (row.get('harness_revision')=='h5.5' and row.get('finished')
                and not row.get('interrupted') and 'resource_limited' in row):
            rows.append(row)
    return rows

def write_report(final=False):
    plan=json.loads((HERE/'plan.json').read_bytes());output=Path(plan['output'])
    state=output/'progress/decision-campaign-v1/state'
    state.mkdir(parents=True,exist_ok=True)
    rows=load_rows(output)
    summary=json.loads((state/'progress.json').read_bytes()) if (state/'progress.json').exists() else {}
    selection=json.loads((state/'selection.json').read_bytes()) if (state/'selection.json').exists() else None
    data=dict(at=time.time(),dispatch=plan['id'],harness_revision='h5.5',final=final,
              full_original_matrix_complete=False,scope=plan,progress=summary,selection=selection,
              score_note='Only the four balanced tasks at seed42 determine the shortlist. Extra historical tasks are retained and reported separately, never silently pooled into that ranking.',
              all_h55_solo_scores={lang:dict(accepted=sum(r['phase']=='solo' and r['language']==lang and r['complete'] for r in rows),finished=sum(r['phase']=='solo' and r['language']==lang for r in rows)) for lang in ['python','cpp']},
              limits=['Small, fixed task sample; practical local selection, not a broad capability ranking.',
                      'Qualification uses supplied reference implementations and is excluded from coding scores.',
                      'Planner probes measure protocol compliance, not objective plan quality.',
                      'Direct API inference is separate from guarded agent work.',
                      'Guarded parallel throughput uses batch wall time, never summed overlapping task time.',
                      'Missing, deferred, interrupted and resource-limited evidence is explicitly labeled.',
                      'Production defaults are not promoted or changed.'])
    for name in ['workflow-results','parallel-choice','stability','comparison-plan','role-selection']:
        path=state/(name+'.json')
        if path.exists():data[name.replace('-','_')]=json.loads(path.read_bytes())
    lines=['OPENRIG — SHORTENED DECISION CAMPAIGN',
           'Status: '+('FINISHED DECISION SCOPE' if final else 'RUNNING'),
           'Original exhaustive schedule is deferred, not completed.',
           'Same immutable h5.5 harness, tasks, acceptance and sampling.','',
           'Progress: '+json.dumps(summary,sort_keys=True),
           'All h5.5 solo outcomes (coverage differs; not a ranking): '+json.dumps(data['all_h55_solo_scores']), '']
    if selection:
        lines+=['MATCHED FOUR-TASK SCREEN — seed42, equal task weights','Model | accepted | resource-limited | total recorded minutes']
        for r in selection['ranked_eligible']:
            lines.append(f"{r['model']} | {r['accepted']}/{r['total']} | {r['resource_limited']} | {r['seconds']/60:.2f}")
        lines+=['Provisional shortlist: '+', '.join(selection['shortlist']),
                'Developer by language: '+json.dumps(selection['developer_by_language']),'']
    for name in ['workflow_results','parallel_choice','stability']:
        if name in data:lines+=[name.upper(),json.dumps(data[name],indent=2),'']
    lines+=['LIMITS']+data['limits']
    blob=json.dumps(data,indent=2)
    (state/'decision-report.json').write_text(blob)
    (state/'decision-report.txt').write_text('\n'.join(lines)+'\n')
    if final:
        (output/'FINAL-COMPARISON.json').write_text(blob)
        (output/'FINAL-COMPARISON.txt').write_text('\n'.join(lines)+'\n')
        (output/'RESULTS.txt').write_text('\n'.join(lines)+'\n')
    return data

if __name__=='__main__':
    plan=json.loads((HERE/'plan.json').read_bytes());output=Path(plan['output'])
    write_report(final=(output/'COMPLETED.json').exists())
