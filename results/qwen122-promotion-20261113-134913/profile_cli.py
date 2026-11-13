#!/usr/bin/python3
"""Resolve the approved default when creating new general-programming tasks."""
import argparse,json
from pathlib import Path
DEFAULTS=Path('/home/cow/.local/state/openrig-fleet/v2/programming-defaults.json')
def resolve(language):
 language={'c++':'cpp','cxx':'cpp','py':'python'}.get(language.lower(),language.lower())
 if language not in ['python','cpp']:raise ValueError('Only Python and C++ use this selector; Unity has its own launcher.')
 profile=json.loads(Path(json.loads(DEFAULTS.read_text())[language]).read_text())
 assert profile['status']=='approved-production-profile'
 return {'language':language,'profile':profile['name'],'model':'ollama/'+profile['model'],'agent_count':1,'context':profile['inference']['context_length'],'resident_models':1,'parallel_slots':1,'optional_roles':profile['optional_roles'],'definition':profile}
if __name__=='__main__':
 p=argparse.ArgumentParser(description='Default profile for new Python/C++ OpenRig tasks. This resolves configuration; it does not launch an unguarded agent.')
 p.add_argument('language',choices=['python','cpp','c++','py','cxx']);a=p.parse_args();print(json.dumps(resolve(a.language),indent=2))
