"""Independent resource observer; leaves the immutable coding harness untouched."""
import json, os, pathlib, signal, subprocess, time

HERE = pathlib.Path(__file__).resolve().parent
OUTPUT = HERE.parents[1]
UNIT = 'openrig-programming-20261109-235342'
EXPECTED_MAIN = str(OUTPUT / 'frozen-harness-v5.4/main.py')
PROFILE = 'monitor-m1'

def atomic(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2))
    os.replace(tmp, path)

def temperatures(paths=None, read=None):
    paths = pathlib.Path('/sys/class/hwmon').glob('hwmon*/temp*_input') if paths is None else paths
    read = (lambda p: p.read_text()) if read is None else read
    values, errors = {}, {}
    try:
        for path in paths:
            try:
                values[str(path)] = int(read(path).strip())
            except (OSError, ValueError) as exc:
                errors[str(path)] = {'type': type(exc).__name__, 'errno': getattr(exc, 'errno', None), 'error': str(exc)}
    except OSError as exc:
        errors['sensor-enumeration'] = {'type': type(exc).__name__, 'errno': exc.errno, 'error': str(exc)}
    return values, errors

class Guard:
    def __init__(self):
        self.low_since = None
        self.oom_seen = 0

    def check(self, available, oom, now):
        if oom > self.oom_seen:
            self.oom_seen = oom
            return 'Private inference cgroup OOM kill'
        self.oom_seen = oom
        if available < 16 * 2**30:
            if self.low_since is None:
                self.low_since = now
            if now - self.low_since > 20:
                return 'MemAvailable below16GiB for20s'
        else:
            self.low_since = None
        return None

def critical_sample():
    memory = {line.split(':')[0]: int(line.split()[1]) * 1024 for line in pathlib.Path('/proc/meminfo').read_text().splitlines()}
    vm = dict(line.split() for line in pathlib.Path('/proc/vmstat').read_text().splitlines())
    sample = {'at': time.time(), 'monitor_profile': PROFILE, 'available': memory['MemAvailable'],
              'system_used': memory['MemTotal'] - memory['MemAvailable'], 'swap_used': memory['SwapTotal'] - memory['SwapFree'],
              'pswpin': int(vm['pswpin']), 'pswpout': int(vm['pswpout'])}
    for path in pathlib.Path('/sys/class/drm').glob('card[0-9]/device/mem_info_*'):
        try:
            sample[path.name] = int(path.read_text())
        except (OSError, ValueError):
            pass
    return sample

def state():
    result = subprocess.run(['systemctl', '--user', 'show', UNIT + '.service', '-p', 'MainPID', '-p', 'ActiveState'], capture_output=True, text=True, check=True, timeout=5)
    return dict(line.split('=', 1) for line in result.stdout.splitlines())

def interrupt_owned(pid, reason):
    # SIGTERM invokes the harness's existing interruption preservation path.
    # Never signal an unrelated PID or change production/inference settings.
    if pid <= 1 or pathlib.Path('/proc').joinpath(str(pid)).stat().st_uid != os.getuid():
        raise RuntimeError('Refuse to signal an unowned process')
    args = pathlib.Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
    if EXPECTED_MAIN.encode() not in args:
        raise RuntimeError('Refuse to signal a different campaign revision/process')
    atomic(HERE / 'RESOURCE-INTERRUPTION.json', {'at': time.time(), 'pid': pid, 'reason': reason, 'classification': 'resource/monitor interruption; exclude from coding failures'})
    os.kill(pid, signal.SIGTERM)

def main():
    import fcntl
    lock = (HERE / 'observer.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    guard = Guard()
    failures = 0
    last_pid = None
    with (HERE / 'telemetry.jsonl').open('a') as telemetry:
        while not (OUTPUT / 'COMPLETED.json').exists():
            try:
                owner = state()
                pid = int(owner['MainPID'])
                if owner['ActiveState'] != 'active' or pid == 0:
                    atomic(HERE / 'heartbeat.json', {'at': time.time(), 'state': 'waiting-for-owned-campaign', 'monitor_profile': PROFILE})
                    time.sleep(2)
                    continue
                if pid != last_pid:
                    guard = Guard()
                    last_pid = pid
                sample = critical_sample()
                cgroup = pathlib.Path('/sys/fs/cgroup/user.slice') / f'user-{os.getuid()}.slice' / f'user@{os.getuid()}.service/app.slice' / (UNIT + '-inference.service/memory.events')
                if cgroup.exists():
                    counts = dict(line.split() for line in cgroup.read_text().splitlines())
                    sample['inference_oom_kills'] = int(counts['oom_kill'])
                else:
                    sample['inference_cgroup_not_present'] = True
                # Essential resource guard runs BEFORE optional thermal I/O.
                reason = guard.check(sample['available'], sample.get('inference_oom_kills', 0), time.monotonic())
                if reason:
                    interrupt_owned(pid, reason)
                    sample['resource_interruption'] = reason
                failures = 0
                sample['temperatures'], sample['sensor_errors'] = temperatures()
                try:
                    sample['active_jobs'] = json.loads((OUTPUT / 'heartbeat.json').read_text()).get('active_jobs', [])
                except (OSError, ValueError):
                    sample['active_jobs'] = []
                telemetry.write(json.dumps(sample) + '\n')
                telemetry.flush()
                atomic(HERE / 'heartbeat.json', {'at': time.time(), 'state': 'monitoring', 'monitor_profile': PROFILE, 'owner_pid': pid, 'available': sample['available'], 'sensor_errors': sample['sensor_errors']})
            except Exception as exc:
                failures += 1
                atomic(HERE / 'critical-error.json', {'at': time.time(), 'consecutive': failures, 'error': str(exc)})
                if failures >= 5 and last_pid:
                    interrupt_owned(last_pid, 'Five consecutive independent resource-monitor failures')
                    raise
            time.sleep(1)
        atomic(HERE / 'heartbeat.json', {'at': time.time(), 'state': 'campaign-complete', 'monitor_profile': PROFILE})

if __name__ == '__main__':
    main()
