from orchestrator import *
import replay
init_services();atomic(O/'models.json',model_config('bootstrap',[('next',42)]));healthy_wait();r=replay.run();print(json.dumps(r),flush=True)
