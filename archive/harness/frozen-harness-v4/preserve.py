from common import *
import shutil

def check(label):
 before=json.load(open(O/'before.json'));after={'files':{p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in before['files']},'services':{n:subprocess.check_output(['systemctl','--user','show',n,'-p','MainPID','-p','Environment'],text=True) for n in before['services']},'game_status':subprocess.check_output(['git','-C','/home/cow/Documents/Programming/Gremlin-Garden','status','--porcelain'],text=True)};record={'at':time.time(),'matches_before':after==before,'after':after};atomic(O/'preservation'/f'{label}-{time.time_ns()}.json',record);return record

def checkpoint(label):
 check(label);target=pathlib.Path(P['backup'])/(label+'-'+str(time.time_ns()));target.mkdir()
 for src in O.iterdir():
  if src.name=='isolation':
   dest=target/'isolation';dest.mkdir()
   for name in ['instance','home','config','data','state']:
    if (src/name).exists():subprocess.run(['cp','-a','--reflink=always',str(src/name),str(dest/name)],check=True)
   # Immutable weight blobs remain in the independent initial copy; record its path rather than copying live alias metadata here.
   (dest/'model-store-location.txt').write_text(str(src/'models'))
  else:subprocess.run(['cp','-a','--reflink=always',str(src),str(target/src.name)],check=True)
 return str(target)
