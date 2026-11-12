"""A completed Case.run plus execute.finally, never the early result write."""
import json
from pathlib import Path

def safe_boundary(output, case_id):
    try:
        status=json.loads((output/'campaign-status.json').read_bytes())
        if status.get('current')!=case_id:return False
        case=output/'runs'/case_id
        row=json.loads((case/'result.json').read_bytes())
        if not row.get('finished') or row.get('interrupted') or 'resource_limited' not in row:return False
        if not (case/'native-final.json').is_file():return False
        rig=json.loads((case/'rig.yaml').read_bytes())
        roles=[r['id'] for pod in rig['pods'] for r in pod['members']]
        if not roles or any(not (case/'transcripts'/role).is_dir() for role in roles):return False
        return row
    except (OSError,ValueError,KeyError):
        return False
