import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest

from server import Observer,collect,handler,http

class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.campaign=self.root/'fixture-campaign'
        (self.campaign/'runs').mkdir(parents=True)
        self.state=self.root/'separate-observer-state'
        self.write('active-harness-revision.json',{'revision':'h5.5'})
        self.write('heartbeat.json',{'pid':12345,'at':time.time(),'active_jobs':['fixture-running']})
        self.write('campaign-status.json',{'phase':'solo','current':'fixture-running'})
        (self.campaign/'events.jsonl').write_text('')
        self.row=dict(id='fixture-one',phase='solo',models={'developer':'next'},topology=1,
                      harness_revision='h5.5',task='py-csv',language='python',seed=42,variant=0,
                      complete=True,seconds=60,started=time.time()-100,finished=time.time()-40,
                      attempts=1,resource_limited=False)

    def tearDown(self):
        self.temp.cleanup()

    def write(self,name,data):
        path=self.campaign/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(data))
        os.utime(path,(time.time()-5,time.time()-5))
        return path

    def hashes(self):
        return {str(p.relative_to(self.campaign)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.campaign.rglob('*') if p.is_file()}

    def test_new_final_result_appears_without_source_mutation(self):
        first=self.write('runs/one/result.json',self.row)
        observer=Observer(self.campaign,self.state)
        observer.scan()
        original=self.hashes()
        data=json.loads((self.state/'data.json').read_text())
        self.assertEqual(len(data['cases']),1)
        self.assertEqual(original,self.hashes())
        identity=data['result_identity']
        second=copy.deepcopy(self.row)
        second.update(id='fixture-two',language='cpp',task='cpp-buffer',complete=False)
        self.write('runs/two/result.json',second)
        original=self.hashes()
        status=observer.scan()
        new=json.loads((self.state/'data.json').read_text())
        self.assertNotEqual(new['result_identity'],identity)
        self.assertEqual(status['finished_solo_trials'],2)
        self.assertEqual(original,self.hashes())
        self.assertEqual(len(list((self.state/'snapshots').iterdir())),2)
        observer.scan()
        self.assertEqual(len(list((self.state/'snapshots').iterdir())),2)

    def test_incomplete_cleanup_and_interruptions_excluded(self):
        pending=copy.deepcopy(self.row)
        del pending['resource_limited']
        self.write('runs/pending/result.json',pending)
        interrupted=copy.deepcopy(self.row)
        interrupted['interrupted']=True
        self.write('runs/interrupted/result.json',interrupted)
        self.assertEqual(collect(self.campaign)[0]['cases'],[])
        self.write('runs/pending/result.json',self.row)
        self.assertEqual(len(collect(self.campaign)[0]['cases']),1)

    def test_age_delay_rechecked_without_another_file_change(self):
        path=self.write('runs/fresh/result.json',self.row)
        observer=Observer(self.campaign,self.state)
        observer.scan()
        os.utime(path,None)
        observer.scan()
        self.assertEqual(json.loads((self.state/'data.json').read_text())['cases'],[])
        # Deterministic clock advancement, not a real sleep or campaign edit.
        import unittest.mock
        real=time.time()
        with unittest.mock.patch('time.time',return_value=real+3):
            observer.scan()
        self.assertEqual(len(json.loads((self.state/'data.json').read_text())['cases']),1)

    def test_partial_json_keeps_last_good_snapshot(self):
        path=self.write('runs/one/result.json',self.row)
        observer=Observer(self.campaign,self.state)
        observer.scan()
        previous=(self.state/'data.json').read_bytes()
        path.write_text('{')
        status=observer.scan()
        self.assertIn('JSONDecodeError',status['error'])
        self.assertEqual((self.state/'data.json').read_bytes(),previous)

    def test_event_aliases_restricted_to_trial_interval(self):
        self.write('runs/one/result.json',self.row)
        base=dict(kind='inference_request',prefix='fixture-one/developer',complete=True,
                  first_delivered_seconds=1,usage={'completion_tokens':50},seconds=10)
        good=dict(base,at=self.row['started']+1)
        old=dict(base,at=self.row['started']-1)
        (self.campaign/'events.jsonl').write_text('\n'.join(map(json.dumps,[old,good]))+'\n{')
        data,_=collect(self.campaign)
        self.assertEqual(data['cases'][0]['tokens'],50)
        self.assertEqual(data['cases'][0]['ttft'],[1])

    def test_readonly_routes_origin_checks_and_no_file_browsing(self):
        Observer(self.campaign,self.state).scan()
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler(self.state,0))
        port=server.server_port
        server.RequestHandlerClass=handler(self.state,port)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            conn=http.client.HTTPConnection('127.0.0.1',port)
            for route,expected in [('/status.json',200),('/data.json',200),('/',200),('/../server.py',404),('/server.py',404)]:
                conn.request('GET',route)
                response=conn.getresponse()
                self.assertEqual(response.status,expected)
                response.read()
            conn.request('GET','/data.json',headers={'Host':'attacker.invalid'})
            response=conn.getresponse();self.assertEqual(response.status,403);response.read()
            conn.request('GET','/data.json',headers={'Origin':'https://attacker.invalid'})
            response=conn.getresponse();self.assertEqual(response.status,403);response.read()
            conn.request('POST','/data.json',body=b'change')
            response=conn.getresponse();self.assertEqual(response.status,501);response.read()
        finally:
            server.shutdown();server.server_close()

if __name__=='__main__':
    unittest.main(verbosity=2)
