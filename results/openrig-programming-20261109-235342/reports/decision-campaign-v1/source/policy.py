"""Pure selection policy for the smaller dispatch; never controls services."""
import statistics

def final_solo(row):
    return (row.get('harness_revision') == 'h5.5' and row.get('phase') == 'solo'
            and row.get('finished') and not row.get('interrupted')
            and 'resource_limited' in row)

def balanced_rows(rows, plan):
    out = {}
    for row in rows:
        if (final_solo(row) and row['seed'] == plan['balanced_seed'] and row.get('variant',0) == 0
                and row['task'] in plan['balanced_tasks'] and row['models'].get('developer') in plan['models']):
            key = row['models']['developer'],row['task']
            if key in out:
                raise ValueError('Duplicate finalized balanced cell: '+str(key))
            out[key] = row
    return out

def select(rows, plan):
    cells = balanced_rows(rows,plan)
    scored = []
    for model in plan['models']:
        items = [cells.get((model,t)) for t in plan['balanced_tasks']]
        if any(r is None for r in items):
            continue
        scored.append(dict(model=model,accepted=sum(bool(r['complete']) for r in items),total=len(items),
                           resource_limited=sum(bool(r['resource_limited']) for r in items),
                           seconds=sum(r['seconds'] for r in items),case_ids=[r['id'] for r in items]))
    # Resource failures remain reported, but cannot qualify an operational choice.
    eligible = [r for r in scored if not r['resource_limited']]
    eligible.sort(key=lambda r:(-r['accepted'],r['seconds'],plan['models'].index(r['model'])))
    if not eligible:
        raise ValueError('No model completed the balanced operational screen')
    shortlist = [r['model'] for r in eligible[:plan['shortlist_count']]]
    if plan['retain_baseline'] not in shortlist:
        shortlist.append(plan['retain_baseline'])
    language = {}
    for lang,prefix in [('python','py-'),('cpp','cpp-')]:
        choices = []
        for model in shortlist:
            items = [cells.get((model,t)) for t in plan['balanced_tasks'] if t.startswith(prefix)]
            if any(r is None or r['resource_limited'] for r in items):
                continue
            choices.append((sum(bool(r['complete']) for r in items),sum(r['seconds'] for r in items),model))
        choices.sort(key=lambda r:(-r[0],r[1],plan['models'].index(r[2])))
        if not choices:
            raise ValueError('No balanced operational candidate for '+lang)
        language[lang] = choices[0][2]
    return dict(rankings=scored,ranked_eligible=eligible,shortlist=shortlist,developer_by_language=language,
                balanced_complete=len(cells)==len(plan['models'])*len(plan['balanced_tasks']),
                selection_rule='Equal weight per balanced task; accepted count first, total recorded time including failures/retries second. Resource-limited candidates do not qualify. One seed only; provisional practical shortlist.')

def choose_reviewer(probes, roster, language, developer):
    task = 'py-refactor' if language == 'python' else 'cpp-binary'
    scored = []
    for model in roster:
        items = [r for r in probes if r.get('model')==model and r.get('task')==task
                 and r.get('harness_revision')=='h5.5' and 'correct_patch' in r]
        # Both a correct and a defective fixture must be judged; missing is unknown.
        if len(items)!=2 or {r['correct_patch'] for r in items}!={True,False}:
            continue
        score=sum(r.get('state')=='complete' and r.get('correct_decision') is True for r in items)
        false_approvals=sum(r.get('correct_patch') is False and r.get('approved') is True for r in items)
        if score==2 and false_approvals==0:
            scored.append((false_approvals,-score,sum(r.get('seconds',0) for r in items),roster.index(model),model))
    different = [r for r in scored if r[-1]!=developer]
    candidates = different or scored
    return min(candidates)[-1] if candidates else developer

def profiles(selection, reviewers, leaders):
    out = {}
    for lang,developer in selection['developer_by_language'].items():
        reviewer=reviewers[lang]
        out[lang] = {
            'solo':dict(topology=1,models={'developer':developer}),
            'review-pair':dict(topology=2,models={'developer':developer,'reviewer':reviewer}),
            'uniform-three':dict(topology=3,models={'lead':developer,'developer':developer,'reviewer':developer}),
            'mixed-three':dict(topology=3,models={'lead':leaders[lang],'developer':developer,'reviewer':reviewer})}
    return out

def choose_workflow(rows, expected, language):
    ranked=[]
    for label,ids in expected[language].items():
        cases=[r for r in rows if r.get('id') in ids and r.get('finished') and not r.get('interrupted')]
        if len(cases)!=len(ids) or any(r.get('resource_limited') for r in cases):
            continue
        ranked.append((sum(bool(r['complete']) for r in cases),sum(r['seconds'] for r in cases),label,cases))
    if not ranked:
        return None
    ranked.sort(key=lambda x:(-x[0],x[1],x[2]))
    best=ranked[0]
    return dict(label=best[2],accepted=best[0],total=len(best[3]),seconds=best[1],
                reliable=best[0]==len(best[3]),case_ids=[r['id'] for r in best[3]])

def choose_parallel(batches):
    groups={}
    for batch in batches:
        groups.setdefault(batch['slots'],[]).append(batch)
    good=[]
    for slots,items in groups.items():
        if len(items)!=3 or {b['seed'] for b in items}!={42,43,44}:
            continue
        accepted=sum(b['accepted'] for b in items);total=sum(b['concurrent_jobs'] for b in items)
        if any(b['resource_limited'] for b in items) or accepted!=total:
            continue
        seconds=sum(b['seconds'] for b in items)
        good.append(dict(slots=slots,accepted=accepted,total=total,seconds=seconds,accepted_per_machine_hour=accepted*3600/max(seconds,.001)))
    if not good:
        return dict(slots=1,qualified=False,reason='No fully accepted repeated profile; conservative fallback for stability only.')
    baseline=next((r for r in good if r['slots']==1),None)
    if baseline is None:
        return dict(slots=1,qualified=False,reason='Sequential control did not qualify; no concurrency recommendation.')
    faster=[r for r in good if r['accepted_per_machine_hour']>=1.15*baseline['accepted_per_machine_hour']]
    winner=max(faster,key=lambda r:r['accepted_per_machine_hour']) if faster else baseline
    return dict(**winner,qualified=True,minimum_meaningful_gain=0.15,
                reason='All requests accepted in three repetitions; higher concurrency requires at least 15% higher accepted-work throughput than one slot.')
