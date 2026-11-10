"""Independent, low-priority GitHub backup; no campaign control operations."""
import argparse,fcntl,json,pathlib,subprocess,time,traceback,datetime,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from tools.snapshot import snapshot,write_json
def git(repository,*args):
 return subprocess.run(['git','-C',str(repository),'-c','pack.threads=1','-c','pack.windowMemory=32m','-c','core.compression=1',*args],capture_output=True,text=True,timeout=300)
def run_once(repository,source,push=True):
 summary=snapshot(source,repository);r=git(repository,'add','--','results')
 if r.returncode:raise RuntimeError(r.stderr[-2000:])
 if git(repository,'diff','--cached','--quiet','--','results').returncode:
  r=git(repository,'commit','-m','Preserve campaign progress '+summary['as_of_utc'])
  if r.returncode:raise RuntimeError(r.stderr[-2000:])
 if push:
  r=git(repository,'push','origin','HEAD:main')
  if r.returncode:raise RuntimeError('GitHub push failed; local commits retained for retry: '+r.stderr[-1500:])
 result={'success':True,'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'head':git(repository,'rev-parse','HEAD').stdout.strip(),'finished_case_records':summary['completed_case_records'],'finished_transport_streams':summary['finished_transport_streams'],'export_errors':summary['export_errors']};write_json(repository/'.local-backup/status.json',result);print(json.dumps(result),flush=True)
 if summary['export_errors']:raise RuntimeError('Partial export; see SNAPSHOT.json and retained local originals')
 return result
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',required=True,type=pathlib.Path);p.add_argument('--source',required=True,type=pathlib.Path);p.add_argument('--interval',default=900,type=int);p.add_argument('--once',action='store_true');p.add_argument('--unit');a=p.parse_args();a.repo=a.repo.resolve();a.source=a.source.resolve();(a.repo/'.local-backup').mkdir(exist_ok=True);lock=open(a.repo/'.local-backup/backup.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 while True:
  try:
   run_once(a.repo,a.source)
   if a.once:return
   if (a.source/'COMPLETED.json').exists():
    if a.unit:subprocess.run(['systemctl','--user','disable',a.unit],capture_output=True)
    return
  except Exception as e:
   write_json(a.repo/'.local-backup/status.json',{'success':False,'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'error':str(e),'local_commits_retained':True});print(traceback.format_exc(),flush=True)
   if a.once:raise
  time.sleep(max(60,a.interval))
if __name__=='__main__':main()
