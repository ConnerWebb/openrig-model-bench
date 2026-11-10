from orchestrator import *
init_services();atomic(O/'models.json',model_config('bootstrap',[('next',42)]));healthy_wait();c=Case('qualification-native-python-v3','py-csv',{'lead':'next','developer':'next','reviewer':'next'},42,3,phase='qualification');r=c.run();atomic(O/'native-qualification-v3.json',r);print(json.dumps(r),flush=True)
