import time
import pandas as pd

MOCK = [
    {'Customer':'Acme Corp','Phase':2,'Payment_Percent':75,'Status':'Active','Amount':12000,'Region':'North'},
    {'Customer':'Globex','Phase':2,'Payment_Percent':62,'Status':'Active','Amount':8500,'Region':'South'},
    {'Customer':'Initech','Phase':1,'Payment_Percent':45,'Status':'Active','Amount':5000,'Region':'North'},
    {'Customer':'Umbrella','Phase':2,'Payment_Percent':90,'Status':'Closed','Amount':22000,'Region':'East'},
    {'Customer':'Stark Industries','Phase':3,'Payment_Percent':100,'Status':'Closed','Amount':50000,'Region':'West'},
    {'Customer':'Wayne Enterprises','Phase':2,'Payment_Percent':55,'Status':'Active','Amount':18000,'Region':'East'},
    {'Customer':'Cyberdyne','Phase':1,'Payment_Percent':30,'Status':'Paused','Amount':3200,'Region':'South'},
    {'Customer':'Soylent','Phase':2,'Payment_Percent':68,'Status':'Active','Amount':9800,'Region':'West'},
    {'Customer':'Tyrell Corp','Phase':3,'Payment_Percent':85,'Status':'Active','Amount':34000,'Region':'North'},
    {'Customer':'Oscorp','Phase':1,'Payment_Percent':20,'Status':'Paused','Amount':2100,'Region':'East'},
]

class SheetsHandler:
    def __init__(self,sid,cp,sr,ttl,mock):
        self.sid=sid;self.cp=cp;self.sr=sr;self.ttl=ttl;self.mock=mock;self._df=None;self._t=0.
    def get_dataframe(self):
        if self._df is not None and time.time()-self._t<self.ttl: return self._df
        self._df=pd.DataFrame(MOCK) if self.mock else self._live(); self._t=time.time(); return self._df
    def schema(self):
        df=self.get_dataframe(); cols=list(df.columns)
        return cols,{c:('int' if df[c].dtype.kind in 'iu' else 'float' if df[c].dtype.kind=='f' else 'str') for c in cols}
    def execute(self,q):
        df=self.get_dataframe()
        for f in q.get('filters',[]): df=_f(df,f)
        a=q['action']; t=q.get('target_column')
        if a=='list': return {'action':'list','row_count':len(df),'rows':df.to_dict(orient='records')}
        if a=='count': return {'action':'count','value':int(len(df))}
        if a in ('sum','avg','min','max'):
            if not t or t not in df: return {'action':a,'value':None}
            s=pd.to_numeric(df[t],errors='coerce').dropna()
            return {'action':a,'target_column':t,'value':float({'sum':s.sum,'avg':s.mean,'min':s.min,'max':s.max}[a]()),'row_count':int(len(s))}
    def _live(self):
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        c=Credentials.from_service_account_file(self.cp,scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
        v=build('sheets','v4',credentials=c,cache_discovery=False).spreadsheets().values().get(spreadsheetId=self.sid,range=self.sr).execute().get('values',[])
        if not v: return pd.DataFrame()
        h,*rows=v; w=len(h); df=pd.DataFrame([r+['']*(w-len(r)) for r in rows],columns=h)
        for col in df.columns: df[col]=pd.to_numeric(df[col],errors='ignore')
        return df

def _f(df,f):
    c,op,v=f['column'],f['op'],f['value']; s=df[c]
    if op=='==': return df[s==v]
    if op=='!=': return df[s!=v]
    if op=='>': return df[pd.to_numeric(s,errors='coerce')>v]
    if op=='>=': return df[pd.to_numeric(s,errors='coerce')>=v]
    if op=='<': return df[pd.to_numeric(s,errors='coerce')<v]
    if op=='<=': return df[pd.to_numeric(s,errors='coerce')<=v]
    if op=='contains': return df[s.astype(str).str.contains(str(v),case=False,na=False)]
    if op=='in': return df[s.isin(v)]
    return df
