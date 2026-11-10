import pathlib,json,shutil,hashlib,subprocess,os
R=pathlib.Path(__file__).resolve().parent;P=json.load(open(R/'paths.json'));O=pathlib.Path(P['output']);F=O/'frozen-harness';F.mkdir()
for p in R.iterdir():
 if p.is_file() and p.suffix in ['.py','.ts','.json']:
  text=p.read_text();text=text.replace(str(R),str(F));(F/p.name).write_text(text)
if (R/'replay-profile').exists():shutil.copytree(R/'replay-profile',F/'replay-profile',ignore=shutil.ignore_patterns('__pycache__'))
wrapper=pathlib.Path(P['runtime'])/'bin/pi';wrapper.write_text(wrapper.read_text().replace(str(R),str(F)))
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in F.iterdir() if p.is_file()};(O/'frozen-harness-sha256.json').write_text(json.dumps(manifest,indent=2));versions={}
for key,args in {'python':['python3','--version'],'clang':['clang++','--version'],'cmake':['cmake','--version'],'rig':[str(pathlib.Path(P['isolation'])/'rig'),'--version']}.items():r=subprocess.run(args,capture_output=True,text=True);versions[key]=r.stdout+r.stderr
(O/'toolchains.json').write_text(json.dumps(versions,indent=2));(O/'RUNNING-READ-ME.txt').write_text('''PYTHON / C++ GUARDED OPENRIG CAMPAIGN

This is a finite scheduled campaign, not just a one-off smoke test.
The benchmark service runs independently of this chat and resumes from case checkpoints after a process restart. It is enabled only for its own campaign and disables its own automatic startup after completion.

Progress: campaign-status.json and heartbeat.json
Live results: RESULTS.txt and leaderboard.json
Original baseline replay: baseline-replay/result.json
Guarded new Python baseline: native-qualification-v3.json
All scored artifacts: runs/*/result.json
Native receipts, exact source, tests and histories: corresponding runs/ folders
Measured request streams: transport/
Parallel API batches: parallel-inference/
Parallel guarded job batches: parallel-jobs/
Completion: COMPLETED.json
Unexpected infrastructure stop: ATTENTION.json (never silently counted as a model failure)

All benchmark endpoints are loopback-only: inference11437, measured transport11438, independent OpenRig18979. The production endpoints/settings, selected fleet, existing histories and Unity game project stay untouched. No model is automatically promoted to production.
Model weights use an independent copy-on-write store; configured aliases are private to this campaign. Backups are same-disk snapshots, not off-disk disaster recovery.

Python and C++ results are separate. Main candidate list has13 variants plus a tiny-model protocol control. Tool-incompatible candidates remain explicitly recorded and cannot receive a valid guarded task score.
The schedule includes individual coding attempts, planner/reviewer probes, three-seat combinations,1/2/3/4/5/6-agent teams, four/five/six distinct-model teams, controlled inference slots, distinct model residency, simultaneous complete jobs and a six-hour finalist soak. Larger contexts/parallel configurations remain subject to memory guards; unsafe/incompatible cells are recorded rather than forced.
Topology qualification uses known-correct source to test workflow/merging and receipts; those are NOT coding-quality results. Scored integration cases include fresh and planted-bug starting trees. Team held-out instances/compositions use new data seeds, not a claim of new unseen programming domains.

Do not edit frozen-harness while this version is running. Versions, task contracts, private oracles and settings are hashed and preserved. The helper source contains reference solutions and must not be exposed to scored agents. Agents only see their isolated workspaces and role-scoped tools.

Important: the campaign can continue with chat closed. It does not send unsolicited chat messages; live results are written here. There is no promise that individual models, task combinations or resource profiles will pass.
''')
unit=P['unit']+'.service';unitfile=O/unit;unitfile.write_text(f'''[Unit]
Description=Isolated OpenRig Python and C++ model campaign
StartLimitIntervalSec=600
StartLimitBurst=3

[Service]
Type=simple
WorkingDirectory={F}
ExecStart=/usr/bin/python3 -u {F}/main.py
Environment=PYTHONUNBUFFERED=1
Environment=XDG_RUNTIME_DIR=/run/user/{os.getuid()}
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{os.getuid()}/bus
Restart=on-failure
RestartPreventExitStatus=78
RestartSec=20
KillMode=mixed
TimeoutStopSec=180
MemoryMax=8G
TasksMax=1024
Nice=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
''')
subprocess.run(['systemctl','--user','link',str(unitfile)],check=True);subprocess.run(['systemctl','--user','daemon-reload'],check=True);subprocess.run(['systemctl','--user','enable','--now',unit],check=True);print(unit);print(O)
