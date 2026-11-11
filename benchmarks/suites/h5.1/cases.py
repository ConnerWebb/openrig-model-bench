import csv,io,re,json,random,struct,collections,statistics,ast

def error(x):return {'error':'ValueError'}
def quoted(s):return '"'+s.replace('\\','\\\\').replace('"','\\"')+'"'
def cases(task,seed=1,private=False):
 r=random.Random(seed+(100000 if private else 0));out=[]
 def add(x,want):out.append((x,want))
 n=14 if private else 4
 if task in ['py-csv','cpp-csv']:
  for i in range(n):
   rows=[];totals={}
   for _ in range(r.randrange(0,40)):
    k=r.choice(['food','rent','a,b','two\nlines','x"quote','日本']);v=r.randrange(0,100000);rows.append([k,f'{v//100}.{v%100:02d}' if task=='py-csv' else str(v-30000)]);totals[k]=totals.get(k,0)+(v if task=='py-csv' else v-30000)
   f=io.StringIO(newline='');w=csv.writer(f,lineterminator='\n');w.writerow(['category','amount']);w.writerows(rows);text=f.getvalue()
   expected={k:f'{v//100}.{v%100:02d}' if task=='py-csv' else v for k,v in sorted(totals.items())};add({'csv':text} if task=='py-csv' else quoted(text),{'value':expected})
  bad=['wrong,amount\nx,1\n','category,amount\nx,1,2\n','category,amount\n,1\n','category,amount\nx,NaN\n','category,amount\n"x,1\n','category,amount\nx,1e2\n']
  bad+=['category,amount\nx,-1\n','category,amount\nx,1.001\n','category,amount\nx,1000000000000\n'] if task=='py-csv' else ['category,amount\nx,9223372036854775808\n','category,amount\nx,9223372036854775807\nx,1\n','category,amount\nx,-9223372036854775808\nx,-1\n']
  for text in bad:add({'csv':text} if task=='py-csv' else quoted(text),error(None))
 elif task=='py-http':
  for i in range(n):
   a=[r.randrange(-100,100) for _ in range(5)];b=[r.randrange(-100,100) for _ in range(3)];status=[503,200] if i%2 else [200];x={'routes':{'/a':{'statuses':status,'body':{'items':a,'next':'/b'}},'/b':{'body':{'items':b,'next':None}}}};add(x,{'value':a+b,'calls':['/a']*len(status)+['/b']})
  for route in [{'body':{'items':[True],'next':None}},{'body':{'items':[],'next':'http://example.invalid/x'}},{'body':{'items':[],'next':'/a'}},{'status':404},{'statuses':[503]},{'raw':'bad-json'},{'body':{'items':[]}}]:add({'routes':{'/a':route}},error(None))
 elif task=='py-queue':
  for i in range(n):
   payload={'v':r.randrange(10000)};ops=[['enqueue','a',payload],['enqueue','a','ignored'],['claim','w',0,5],['complete','a','wrong'],['fail','a','w'],['claim','w2',1,5],['complete','a','w2'],['status','a'],['claim','w3',100,5]];add({'ops':ops},{'value':[True,False,{'key':'a','payload':payload,'attempts':1},False,True,{'key':'a','payload':payload,'attempts':2},True,{'state':'done','attempts':2},None]})
  add({'max_attempts':1,'ops':[['enqueue','x',0],['claim','w',0,2],['claim','other',2,2],['status','x']]},{'value':[True,{'key':'x','payload':0,'attempts':1},None,{'state':'failed','attempts':1}]})
  for count in ([20,61,97] if private else [12]):add({'concurrent':count},{'value':[[str(i) for i in range(count)]]})
  add({'ops':[['claim','',0,1]]},error(None));add({'ops':[['claim','a',0,0]]},error(None))
 elif task=='py-archive':
  for i in range(n):
   entries=[{'name':'folder/'},{'name':'folder/a.txt','text':str(r.randrange(10000))},{'name':'b.txt','text':'hello 日本'}];add({'entries':entries},{'value':['b.txt','folder/a.txt'],'files':{'folder/a.txt':entries[1]['text'],'b.txt':'hello 日本'}})
  for names in [['../x'],['/absolute'],['C:bad'],['a\\b'],['a','a'],['a','a/b']]:add({'entries':[{'name':s,'text':'x'} for s in names]},error(None))
  add({'entries':[{'name':'link','text':'/elsewhere','symlink':True}]},error(None));add({'entries':[]},{'value':[],'files':{}});add({'entries':[],'exists':True},error(None))
 elif task=='py-refactor':
  for i in range(n):
   records=[];events=[];seen=set();totals={};minimum=r.randrange(20)
   for j in range(25):
    id=str(r.randrange(10));cat=r.choice(['a','b','c']);v=r.randrange(100);records.append({'id':' '+id+' ','category':' '+cat+' ','cents':v})
    if id not in seen:
     seen.add(id)
     if v>=minimum:events.append({'id':id,'category':cat,'cents':v});totals[cat]=totals.get(cat,0)+v
   add({'records':records,'minimum':minimum},{'value':{'events':events,'totals':totals},'empty':{'events':[],'totals':{}},'input_unchanged':True})
  for bad in [{'id':'x','category':'a','cents':True},{'id':'','category':'a','cents':1},{'id':'x','category':'a','cents':-1},{'id':'x','category':'a','cents':1,'extra':2}]:add({'records':[bad]},error(None))
 elif task=='py-expression':
  for i in range(n*2):
   a,b,c=(r.randrange(-100,100) for _ in range(3));c=c or 1;text=f'({a} + {b}) * 3 // ({c})';add({'text':text},{'value':((a+b)*3)//c})
  for s in ['','1/2','2**3','True','a+2','__import__("os")','1//0','1.0+2','1'+'0'*51,'('*120+'1'+')'*120]:add({'text':s},error(None))
 elif task=='cpp-queue':
  for i in range(n):
   cap=r.randrange(1,12);count=r.randrange(1,400);workers=r.randrange(1,8);add(f'1 {cap} {count} {workers}',{'value':list(range(count))})
  add('0 4 0 1',{'value':[False,False]});add('0 0 0 1',error(None));add('2 1 97 1',{'value':97})
 elif task=='cpp-buffer':
  for i in range(n):
   count=r.randrange(0,60);grow=r.randrange(0,100);data=[r.randrange(256) for _ in range(count)];cp=data.copy()
   if cp:cp[0]^=255
   add(' '.join(map(str,[count,grow]+data)),{'value':(data+[0]*max(0,grow-count))[:grow],'moved_size':0,'copy':cp,'bounds':True})
 elif task=='cpp-binary':
  def encode(records):
   b=b'OGC1'+struct.pack('<I',len(records))
   for id,name,v in records:
    name=name.encode();b+=struct.pack('<IH',id,len(name))+name+struct.pack('<q',v)
   return b
  for i in range(n):
   recs=[[j,r.choice(['a','b c','日本','x"y',''])+str(i),r.randrange(-2**60,2**60)] for j in range(r.randrange(0,20))];b=encode(recs);add('0 '+str(len(recs))+' '+ ' '.join(f'{id} {quoted(name)} {v}' for id,name,v in recs),{'value':recs,'hex':b.hex()});add('1 '+b.hex(),{'value':recs,'hex':b.hex()})
  b=encode([[1,'a',-2]])
  for bad in [b[:3],b[:10],b[:-1],b+b'X',b'BAD!'+b[4:],b'OGC1'+struct.pack('<I',10001),encode([[1,'a',1],[1,'b',2]])]:add('1 '+bad.hex(),error(None))
 elif task=='cpp-stats':
  for i in range(n):
   vals=[float(10**9+r.randrange(-100,100)) for _ in range(r.randrange(1,80))];split=r.randrange(len(vals)+1);twice=i%2;count=len(vals)*(2 if twice else 1);mean=statistics.mean(vals);var=statistics.pvariance(vals);add(' '.join(map(str,[len(vals),split,twice]+vals)),{'value':[count,mean,var,min(vals),max(vals)]})
  add('0 0 0',error(None));add('1 1 0 nan',error(None));add('1 1 0 inf',error(None))
 elif task=='cpp-lru':
  for i in range(n):
   cap=r.randrange(0,8);ops=[];q=collections.OrderedDict();values=[]
   for _ in range(150 if private else 30):
    op=r.choice(['P','P','G','E','S']);k=r.randrange(10)
    if op=='P':
     v=r.choice(['x','two words','日本'])+str(r.randrange(100));ops.append('P '+str(k)+' '+quoted(v));values.append(None)
     if cap:
      q.pop(k,None);q[k]=v
      while len(q)>cap:q.popitem(last=False)
    elif op=='G':
     ops.append('G '+str(k));v=q.pop(k,None)
     if v is None:values.append([False,'UNCHANGED'])
     else:q[k]=v;values.append([True,v])
    elif op=='E':ops.append('E '+str(k));values.append(k in q);q.pop(k,None)
    else:ops.append('S');values.append([[k,v] for k,v in reversed(q.items())])
   add(f'{cap} {len(ops)} '+' '.join(ops),{'value':values,'size':len(q)})
 else:raise KeyError(task)
 return out

def equivalent(a,b):
 if isinstance(a,float) or isinstance(b,float):
  return isinstance(a,(int,float)) and isinstance(b,(int,float)) and abs(a-b)<=1e-4+1e-6*abs(b)
 if type(a)!=type(b):return False
 if isinstance(a,dict):return a.keys()==b.keys() and all(equivalent(a[k],b[k]) for k in a)
 if isinstance(a,list):return len(a)==len(b) and all(equivalent(x,y) for x,y in zip(a,b))
 return a==b
_BASE_CASES=cases
def cases(task,seed=1,private=False):
 if task=='py-team':return cases('py-refactor',seed,private)
 if task=='py-normalizer':
  rows=[]
  for x,want in _BASE_CASES('py-refactor',seed,private):
   if 'error' in want:rows.append((x,want))
   else:rows.append((x,{'value':[{'id':v['id'].strip(),'category':v['category'].strip(),'cents':v['cents']} for v in x['records']],'input_unchanged':True}))
  return rows
 if task=='cpp-team':
  rows=[]
  for prefix,sub in [(0,'cpp-csv'),(1,'cpp-lru'),(2,'cpp-stats')]:rows.extend((str(prefix)+' '+x,y) for x,y in _BASE_CASES(sub,seed,private))
  for x,w in _BASE_CASES('cpp-csv',seed,private):
   if 'error' in w:rows.append(('3 '+x,w));continue
   totals=w['value'];items=list(sorted(totals.items()));values=list(totals.values());cache=[[i,k+':'+str(v)] for i,(k,v) in enumerate(items)][-2:][::-1];stats=[len(values)]
   if values:stats+=[statistics.mean(values),statistics.pvariance(values)]
   rows.append(('3 '+x,{'totals':totals,'cache':cache,'stats':stats}))
  return rows
 rows=_BASE_CASES(task,seed,private)
 if task=='py-archive':
  rows=[(x,{**y,'unchanged':True} if 'error' in y else y) for x,y in rows]
 if private and task=='cpp-queue':rows.append(('3 1 0 1',{'value':[False,17,False]}))
 if private and task=='py-refactor':rows.append(({'records':[{'id':'x','category':'a','cents':1},{'id':'x','category':'a','cents':True}]},{'error':'ValueError'}))
 if private and task=='cpp-binary':
  b=b'OGC1'+struct.pack('<I',1)+struct.pack('<IH',1,1025)+b'x'*1025+struct.pack('<q',0);rows.append(('1 '+b.hex(),{'error':'ValueError'}))
 return rows
