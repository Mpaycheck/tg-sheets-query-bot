from dataclasses import dataclass
from typing import Any, Dict, List

ALLOWED_OPS={'==','!=','>','>=','<','<=','contains','in'}
ALLOWED_ACTIONS={'list','count','sum','avg','min','max'}
NUMERIC_OPS={'>','>=','<','<='}
AGG={'sum','avg','min','max'}

@dataclass
class ValidationResult:
    ok:bool; errors:List[str]; normalized_query:Dict[str,Any]

def validate(q,cols,dtypes):
    err=[]; norm={'filters':[],'action':None,'target_column':None}
    a=q.get('action')
    if a not in ALLOWED_ACTIONS: err.append(f"Unknown action '{a}'")
    norm['action']=a; t=q.get('target_column')
    if a in AGG:
        if not t: err.append(f"'{a}' needs target_column")
        elif t not in cols: err.append(f"Column '{t}' not found")
        elif dtypes.get(t) not in ('int','float'): err.append(f"'{t}' not numeric")
    norm['target_column']=t
    for i,f in enumerate(q.get('filters',[]) or []):
        c,op,v=f.get('column'),f.get('op'),f.get('value')
        if c not in cols: err.append(f"F{i}: col '{c}' unknown"); continue
        if op not in ALLOWED_OPS: err.append(f"F{i}: bad op '{op}'"); continue
        if op in NUMERIC_OPS and dtypes.get(c) not in ('int','float'): err.append(f"F{i}: numeric op on string"); continue
        cv,e=_cv(v,dtypes.get(c,'str'),op)
        if e: err.append(f"F{i}: {e}"); continue
        norm['filters'].append({'column':c,'op':op,'value':cv})
    return ValidationResult(ok=not err,errors=err,normalized_query=norm)

def _cv(v,dtype,op):
    if op=='in': return (v,'') if isinstance(v,list) else (None,"needs list")
    if dtype in ('int','float'):
        try: return (int(float(v)),'') if dtype=='int' else (float(v),'')
        except: return None,f"can't coerce '{v}'"
    return v,''
