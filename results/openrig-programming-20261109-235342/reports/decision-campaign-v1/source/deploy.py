"""Wait for an idle result boundary, checkpoint, replace only private dispatch."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import struct
import subprocess
import sys
import time
import traceback
from boundary import safe_boundary

HERE=Path(__file__).resolve().parent
PLAN=json.loads((HERE/'plan.json').read_bytes());O=Path(PLAN['output'])
D=O/'progress/decision-campaign-v1';STATE=D/'state'
sys.path.insert(0,PLAN['harness_path'])
from common import atomic,I,P
from preserve import check,checkpoint
from orchestrator import archive_db
UNIT=P['unit']+'.service'

def show(prop):
    return subprocess.check_output(['systemctl','--user','show',UNIT,'-p',prop,'--value'],text=True).strip()

def verify_sources():
    manifest=json.loads((HERE/'SOURCE-MANIFEST.json').read_bytes())
    assert all(hashlib.sha256((HERE/p).read_bytes()).hexdigest()==h for p,h in manifest.items())
    frozen=json.loads((O/'frozen-harness-v5.5-sha256.json').read_bytes())
    assert all(hashlib.sha256((Path(PLAN['harness_path'])/p).read_bytes()).hexdigest()==h for p,h in frozen.items())

def wait_pause(pid):
    # Linux rename notifications detect the atomic final write. Re-check after
    # SIGSTOP; if the controller already admitted another case, resume and wait.
    libc=ctypes.CDLL(None,use_errno=True)
    fd=libc.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC)
    if fd<0:raise OSError(ctypes.get_errno(),'inotify_init1')
    watched=None;wd=-1;deadline=time.monotonic()+2*3600
    try:
        while time.monotonic()<deadline:
            if int(show('MainPID'))!=pid:raise RuntimeError('Original private controller PID changed; inspect before any stop')
            status=json.loads((O/'campaign-status.json').read_bytes());case_id=status.get('current')
            case=O/'runs'/str(case_id)
            if not case.is_dir():time.sleep(.05);continue
            if watched!=case:
                if wd>=0:libc.inotify_rm_watch(fd,wd)
                wd=libc.inotify_add_watch(fd,os.fsencode(case),0x80)
                if wd<0:raise OSError(ctypes.get_errno(),'inotify_add_watch')
                watched=case
                atomic(STATE/'waiting-boundary.json',dict(at=time.time(),pid=pid,current=case_id,policy='Wait for final resource flag, archived transcripts and native-final; no active case cancellation.'))
            row=safe_boundary(O,case_id)
            if row:
                os.kill(pid,signal.SIGSTOP)
                paused=False
                for _ in range(50):
                    if '\nState:\tT' in Path(f'/proc/{pid}/status').read_text():paused=True;break
                    time.sleep(.002)
                if paused and safe_boundary(O,case_id):
                    result=dict(at=time.time(),pid=pid,case=case_id,result_sha256=hashlib.sha256((case/'result.json').read_bytes()).hexdigest(),cleanup_complete=True,active_trial_interrupted=False)
                    atomic(STATE/'boundary-pause.json',result)
                    return result
                os.kill(pid,signal.SIGCONT)
            ready,_,_=select.select([fd],[],[],.25)
            if ready:
                try:os.read(fd,65536)
                except BlockingIOError:pass
        raise TimeoutError('No verified idle boundary within two hours; campaign left running')
    finally:
        os.close(fd)

def run():
    if (STATE/'DEPLOYMENT.json').exists():return
    verify_sources();prepared=json.loads((STATE/'prepared.json').read_bytes());pid=prepared['old_main_pid']
    assert str(Path(PLAN['harness_path'])/'main.py') in Path(f'/proc/{pid}/cmdline').read_bytes().decode().replace('\x00',' ')
    try:
        boundary=wait_pause(pid)
        assert check('decision-idle-boundary')['matches_before']
        # Consistent SQLite and complete CoW filesystem evidence precede restart.
        archive_db('decision-idle-boundary');backup=checkpoint('decision-idle-boundary')
        atomic(STATE/'boundary-checkpoint.json',dict(at=time.time(),backup=backup,boundary=boundary))
        subprocess.run(['systemctl','--user','stop','--no-block',UNIT],check=True)
        try:os.kill(pid,signal.SIGCONT)
        except ProcessLookupError:pass
        end=time.monotonic()+180
        while show('MainPID')!='0' and time.monotonic()<end:time.sleep(.25)
        assert show('MainPID')=='0','Old private process must finish cleanup'
        assert not (O/'COMPLETED.json').exists()
        verify_sources()
        previous=D/'previous-campaign.service';text=previous.read_text()
        text=text.replace('WorkingDirectory='+PLAN['harness_path'],'WorkingDirectory='+str(HERE))
        text=text.replace('ExecStart=/usr/bin/python3 -u '+PLAN['harness_path']+'/main.py','ExecStart=/usr/bin/python3 -B -u '+str(HERE/'dispatch.py'))
        text=text.replace('ExecStopPost=/usr/bin/python3 '+PLAN['harness_path']+'/final_analysis.py','ExecStopPost=/usr/bin/python3 -B '+str(HERE/'report.py'))
        assert str(HERE/'dispatch.py') in text and str(HERE/'report.py') in text
        unit=Path('/home/cow/.config/systemd/user')/UNIT
        unit.write_text(text)
        active=json.loads((O/'active-harness-revision.json').read_bytes())
        active.update(dispatch='decision-v1',dispatch_source=str(HERE),schedule_changed_at=time.time(),harness_scoring_changed=False,full_matrix_deferred=True)
        atomic(O/'active-harness-revision.json',active)
        subprocess.run(['systemctl','--user','daemon-reload'],check=True)
        subprocess.run(['systemctl','--user','reset-failed',UNIT],capture_output=True)
        subprocess.run(['systemctl','--user','start',UNIT],check=True)
        until=time.monotonic()+120
        while time.monotonic()<until:
            newpid=int(show('MainPID'));hb=json.loads((O/'heartbeat.json').read_bytes())
            if newpid and newpid!=pid and hb['pid']==newpid and time.time()-hb['at']<5:break
            time.sleep(.5)
        else:raise RuntimeError('Replacement monitor did not become fresh; inspect private service')
        old=json.loads((D/'pre-change-result-sha256.json').read_bytes())
        assert all(hashlib.sha256((O/p).read_bytes()).hexdigest()==h for p,h in old.items())
        assert check('decision-after-switch')['matches_before'];verify_sources()
        deployment=dict(at=time.time(),harness_revision='h5.5',dispatch='decision-v1',previous_main_pid=pid,new_main_pid=newpid,boundary=boundary,checkpoint=backup,previous_results_verified=len(old),source_manifest_verified=True,production_unchanged=True,active_trial_interrupted=False)
        atomic(STATE/'DEPLOYMENT.json',deployment);print(json.dumps(deployment),flush=True)
    except Exception as exc:
        atomic(STATE/'deployment-error.json',dict(at=time.time(),error=str(exc),traceback=traceback.format_exc(),note='No result deleted or rewritten. See rollback instructions; do not stop a healthy trial.'))
        raise
    finally:
        try:
            if '\nState:\tT' in Path(f'/proc/{pid}/status').read_text():os.kill(pid,signal.SIGCONT)
        except (ProcessLookupError,FileNotFoundError):pass

if __name__=='__main__':run()
