import json,pathlib,subprocess,tempfile,unittest
from tools.live_backup import run_once
def command(*args):return subprocess.run(args,check=True,capture_output=True,text=True)
class GitBackup(unittest.TestCase):
 def test_only_results_committed_and_failed_push_is_recoverable(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp);repo=root/'repo';source=root/'source';remote=root/'remote.git';repo.mkdir();source.mkdir();(source/'runs').mkdir();(source/'transport').mkdir();(source/'campaign-status.json').write_text('{"phase":"test"}')
   command('git','init','-b','main',str(repo));command('git','-C',str(repo),'config','user.name','Backup test');command('git','-C',str(repo),'config','user.email','test@example.invalid');(repo/'README').write_text('test');command('git','-C',str(repo),'add','README');command('git','-C',str(repo),'commit','-m','initial');command('git','init','--bare',str(remote));command('git','-C',str(repo),'remote','add','origin',str(remote));(repo/'unrelated.txt').write_text('leave staged');command('git','-C',str(repo),'add','unrelated.txt')
   run_once(repo,source);self.assertNotIn('unrelated.txt',command('git','-C',str(repo),'ls-tree','--name-only','HEAD').stdout);self.assertIn('unrelated.txt',command('git','-C',str(repo),'diff','--cached','--name-only').stdout)
   before=command('git','-C',str(repo),'rev-parse','HEAD').stdout.strip();command('git','-C',str(repo),'remote','set-url','origin',str(root/'missing.git'))
   with self.assertRaisesRegex(RuntimeError,'local commits retained'):run_once(repo,source)
   pending=command('git','-C',str(repo),'rev-parse','HEAD').stdout.strip();self.assertNotEqual(before,pending);command('git','-C',str(repo),'remote','set-url','origin',str(remote));run_once(repo,source);self.assertEqual(command('git','-C',str(repo),'rev-parse','HEAD').stdout.strip(),command('git','--git-dir',str(remote),'rev-parse','refs/heads/main').stdout.strip())
   command('git','-C',str(repo),'checkout','-b','feature')
   with self.assertRaisesRegex(RuntimeError,'other than main'):run_once(repo,source)
if __name__=='__main__':unittest.main()
