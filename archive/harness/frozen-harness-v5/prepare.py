import pathlib,json,datetime,subprocess,hashlib,sqlite3,socket,shutil
R=pathlib.Path(__file__).resolve().parent;BASE=pathlib.Path('/home/cow/.local/opt/framework-ai/openrig-fleet');STATE=pathlib.Path('/home/cow/.local/state/openrig-fleet');stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S');O=pathlib.Path.cwd()/'outputs'/('openrig-programming-'+stamp);O.mkdir();B=pathlib.Path('/home/cow/Documents/Codex/Backups/openrig-programming')/stamp;B.mkdir(parents=True,mode=0o700)
for port in [18979,11437]:
 with socket.socket() as s:s.bind(('127.0.0.1',port))
files=[BASE/'bin/pi',STATE/'v2/coding-current.txt',STATE/'v2/current-rig.txt',pathlib.Path('/home/cow/.local/bin/local-code')]+list((BASE/'v2/generic-staged').glob('*.py'))+list((BASE/'v2/generic-staged').glob('*.ts'))
before={'files':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},'services':{n:subprocess.check_output(['systemctl','--user','show',n,'-p','MainPID','-p','Environment'],text=True) for n in ['framework-ollama','framework-comfyui']},'game_status':subprocess.check_output(['git','-C','/home/cow/Documents/Programming/Gremlin-Garden','status','--porcelain'],text=True)};(O/'before.json').write_text(json.dumps(before,indent=2));subprocess.run(['cp','-a','--reflink=always',str(STATE),str(B/'fleet-state')],check=True)
s=sqlite3.connect('file:'+str(STATE/'instance/openrig.sqlite')+'?mode=ro',uri=True);d=sqlite3.connect(B/'consistent-before.sqlite');s.backup(d);assert d.execute('pragma integrity_check').fetchone()[0]=='ok';s.close();d.close()
I=O/'isolation';I.mkdir();runtime=I/'runtime';(runtime/'bin').mkdir(parents=True)
for n in ['npm','node-v22.23.4-linux-x64']:(runtime/n).symlink_to(BASE/n,target_is_directory=True)
for n in ['home','config','data','state','instance','models']:(I/n).mkdir()
subprocess.run(['cp','-a','--reflink=always','/home/cow/.ollama/models/.',str(I/'models')],check=True)
p={'output':str(O),'backup':str(B),'isolation':str(I),'base':str(BASE),'stamp':stamp,'runtime':str(runtime),'ollama_port':11437,'rig_port':18979,'unit':'openrig-programming-'+stamp};(R/'paths.json').write_text(json.dumps(p,indent=2));shutil.copy2(R/'paths.json',O/'paths.json')
script='#!/bin/sh\nset -eu\n'
for k,v in {'HOME':str(I/'home'),'XDG_CONFIG_HOME':str(I/'config'),'XDG_DATA_HOME':str(I/'data'),'XDG_STATE_HOME':str(I/'state'),'OPENRIG_HOME':str(I/'instance'),'OPENRIG_BIND_HOST':'127.0.0.1','OPENRIG_PORT':'18979','OPENRIG_NO_KERNEL':'1','PATH':str(runtime/'bin')+':'+str(BASE/'node-v22.23.4-linux-x64/bin')+':'+str(BASE/'npm/node_modules/.bin')+':/usr/bin:/bin'}.items():script+='export '+k+'="'+v+'"\n'
script+='exec "'+str(BASE/'npm/node_modules/.bin/rig')+'" "$@"\n';(I/'rig').write_text(script);(I/'rig').chmod(0o700)
pi='#!/bin/sh\nset -eu\nif [ -n "${PI_CODING_AGENT_DIR:-}" ]; then mkdir -p "$PI_CODING_AGENT_DIR"; cp "'+str(O/'models.json')+'" "$PI_CODING_AGENT_DIR/models.json"; fi\nexec "'+str(BASE/'npm/node_modules/.bin/pi')+'" --offline --no-builtin-tools --no-extensions -e "'+str(R/'extension.ts')+'" "$@"\n';(runtime/'bin/pi').write_text(pi);(runtime/'bin/pi').chmod(0o700)
print(json.dumps(p,indent=2))
