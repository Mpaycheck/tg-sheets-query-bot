import json, re
from typing import Any, Dict, List, Optional

SYSTEM_PROMPT = 'Convert the user question to a JSON query. Keys: filters (list of {column,op,value}), action (list/count/sum/avg/min/max), target_column. No prose.'
ACTION_WORDS = {'sum':r'sum|total','avg':r'average|avg|mean','min':r'min|minimum|lowest','max':r'max|maximum|highest'}
COMPARISON_WORDS = [('more than','>'),('greater than','>'),('above','>'),('over','>'),('less than','<'),('below','<'),('under','<'),('at least','>='),('at most','<=')]
SKIP = {'more','less','greater','above','below','over','under','not','than','the','a','an','is'}

class QueryParser:
    def __init__(self, api_key, model, mock_mode):
        self.api_key=api_key; self.model=model; self.mock_mode=mock_mode; self._client=None
    def parse(self, text, columns):
        return _mock(text,columns) if self.mock_mode else self._openai(text,columns)
    def _openai(self, text, columns):
        if not self._client:
            from openai import OpenAI; self._client=OpenAI(api_key=self.api_key)
        r=self._client.chat.completions.create(model=self.model,messages=[
            {'role':'system','content':SYSTEM_PROMPT},
            {'role':'user','content':f'Columns:{columns}\nQuestion:{text}\nJSON:'}],
            temperature=0,response_format={'type':'json_object'})
        return json.loads(r.choices[0].message.content or '{}')

def _mock(user_text, columns):
    text=user_text.lower(); cl={c.lower():c for c in columns}; cs=sorted(cl,key=len,reverse=True)
    a=_act(text); t=_tgt(text,a,cl,cs); f=_flt(user_text,text,cl,cs)
    return {'filters':f,'action':a,'target_column':t}

def _act(t):
    if re.search(r'\bhow many\b|\bcount\b',t): return 'count'
    if re.search(r'\btotal\b|\bsum\b',t): return 'sum'
    if re.search(r'\baverage\b|\bavg\b',t): return 'avg'
    if re.search(r'\bmax\b|\bmaximum\b|\bhighest\b',t): return 'max'
    if re.search(r'\bmin\b|\bminimum\b|\blowest\b',t): return 'min'
    return 'list'

def _tgt(t,a,cl,cs):
    if a not in ACTION_WORDS: return None
    rx=ACTION_WORDS[a]
    for c in cs:
        if re.search(rf'(?:{rx})(?:\s+of)?\s+(?:the\s+)?{re.escape(c)}\b',t): return cl[c]
    for c in cs:
        if re.search(rf'\b{re.escape(c)}\b',t): return cl[c]
    return None

def _flt(ut,t,cl,cs):
    f=[]; done=set()
    for c in cs:
        o=cl[c]
        for w,s in COMPARISON_WORDS:
            m=re.search(rf'\b{re.escape(c)}\s+(?:is\s+)?{w}\s+(-?\d+(?:\.\d+)?)',t)
            if m: n=float(m.group(1)); f.append({'column':o,'op':s,'value':int(n) if n.is_integer() else n}); done.add(o); break
    for c in cs:
        o=cl[c]
        if o in done: continue
        m=re.search(rf'\b{re.escape(c)}\s+(?:is\s+|=\s*)?(-?\d+(?:\.\d+)?)\b',t)
        if m: n=float(m.group(1)); f.append({'column':o,'op':'==','value':int(n) if n.is_integer() else n}); done.add(o)
    for c in cs:
        o=cl[c]
        if o in done: continue
        m=re.search(rf'\b{re.escape(c)}\s+(?:is|==|=|:)\s+([a-z][a-z0-9_-]*)\b',t) or re.search(rf'\bin\s+{re.escape(c)}\s+([a-z][a-z0-9_-]*)\b',t)
        if m:
            raw=m.group(1)
            if raw in SKIP: continue
            om=re.search(re.escape(raw),ut,re.IGNORECASE)
            f.append({'column':o,'op':'==','value':om.group(0) if om else raw}); done.add(o)
    return f
