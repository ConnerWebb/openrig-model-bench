"""Frozen coding contracts; never mounted with reference implementations."""
TASKS={}
def add(id,language,contract,reference,driver,cases,starter=None):
 TASKS[id]={'id':id,'language':language,'contract':contract,'reference':reference,'driver':driver,'cases':cases,'starter':starter or {}}
# Drivers consume one JSON input and emit one JSON result. Oracles stay outside candidate processes.
PY_COMMON='''import sys,json,tempfile,pathlib,traceback\nsys.path.insert(0,'/work')\nx=json.load(sys.stdin)\ntry:\n import solution\n'''
PY_END='''\nexcept Exception as e:\n print(json.dumps({'error':type(e).__name__}))\n'''
add('py-csv','python',r'''Implement solution.py aggregate(path: str)->dict[str,str]. Read UTF-8 CSV as a stream. Header must be exactly category,amount. Ignore completely blank records; every other record has exactly two fields. Strip category/amount whitespace; category must not be empty. Amount has optional +, 1–12 decimal digits, optional decimal point followed by 1 or 2 digits; nonnegative, finite, no exponent. Reject all malformed input with ValueError. Accumulate using exact decimal arithmetic. Return category keys sorted, totals formatted with exactly two decimal places. CSV quoted commas and embedded newlines are valid. Add your own tests and README.md. Do not read the whole file merely to parse it.''',r'''
import csv,re
from decimal import Decimal
def aggregate(path):
 out={}
 with open(path,encoding='utf-8',newline='') as f:
  rd=csv.reader(f,strict=True)
  if next(rd,None)!=['category','amount']:raise ValueError('header')
  try:
   for row in rd:
    if not row:continue
    if len(row)!=2:raise ValueError('columns')
    k,v=(s.strip() for s in row)
    if not k or not re.fullmatch(r'\+?\d{1,12}(?:\.\d{1,2})?',v,flags=re.ASCII):raise ValueError('record')
    out[k]=out.get(k,Decimal(0))+Decimal(v)
  except csv.Error as e:raise ValueError('csv') from e
 return {k:format(out[k],'.2f') for k in sorted(out)}
''',PY_COMMON+''' with tempfile.TemporaryDirectory() as d:
  p=pathlib.Path(d)/'input.csv';p.write_text(x['csv'],encoding='utf-8');del x
  result=solution.aggregate(str(p));print(json.dumps({'value':result},ensure_ascii=False))
'''+PY_END, 'csv')
add('py-http','python',r'''Implement solution.py fetch_pages(url,retries=2,timeout=1.0)->list. Fetch JSON pages over HTTP using Python stdlib. Each page is exactly an object with items (list of integers; bool is not an integer here) and next (same-origin absolute URL, relative URL, or null). Preserve item order across pages. Resolve relative next URLs. Reject cross-origin URLs, repeated page URLs, invalid schema/JSON and non-HTTP initial URLs with ValueError. Retry only status 429/500/502/503/504, up to retries additional attempts PER PAGE; no sleep required. Other HTTP/network failures and exhausted retries raise ValueError. Timeout is passed to the HTTP request. Validate retries >=0 and timeout >0. No external dependencies. Add tests and README.md.''',r'''
import json,urllib.request,urllib.parse,urllib.error
def fetch_pages(url,retries=2,timeout=1.):
 if isinstance(retries,bool) or not isinstance(retries,int) or retries<0 or timeout<=0:raise ValueError('options')
 def origin(u):
  p=urllib.parse.urlsplit(u)
  if p.scheme not in ['http','https'] or not p.hostname or p.username or p.password:raise ValueError('url')
  return p.scheme,p.hostname,p.port or (443 if p.scheme=='https' else 80)
 org=origin(url);seen=set();out=[]
 while url:
  if origin(url)!=org or url in seen:raise ValueError('origin/cycle')
  seen.add(url)
  for n in range(retries+1):
   try:
    with urllib.request.urlopen(url,timeout=timeout) as r:obj=json.load(r)
    break
   except urllib.error.HTTPError as e:
    if e.code not in [429,500,502,503,504] or n==retries:raise ValueError('http') from e
   except Exception as e:raise ValueError('request') from e
  if not isinstance(obj,dict) or set(obj)!= {'items','next'} or not isinstance(obj['items'],list) or any(type(v)!=int for v in obj['items']) or (obj['next'] is not None and not isinstance(obj['next'],str)):raise ValueError('schema')
  out+=obj['items'];url=urllib.parse.urljoin(url,obj['next']) if obj['next'] is not None else None
 return out
''',PY_COMMON+''' import http.server,threading
 calls=[];routes=x['routes'];counts={}
 class Handler(http.server.BaseHTTPRequestHandler):
  def log_message(self,*a):pass
  def do_GET(self):
   calls.append(self.path);n=counts.get(self.path,0);counts[self.path]=n+1;route=routes.get(self.path,{'status':404});statuses=route.get('statuses',[route.get('status',200)]);status=statuses[min(n,len(statuses)-1)];self.send_response(status);self.end_headers();self.wfile.write(route.get('raw',json.dumps(route.get('body',{}))).encode())
 server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  result=solution.fetch_pages('http://127.0.0.1:'+str(server.server_port)+'/a',x.get('retries',2),.3);print(json.dumps({'value':result,'calls':calls}))
 finally:server.shutdown();server.server_close()
'''+PY_END, 'http')
add('py-queue','python',r'''Implement solution.py JobQueue(path,max_attempts=3), using SQLite. Methods: enqueue(key,payload)->bool (first unique key wins); claim(worker,now,lease)->dict or None; complete(key,worker)->bool; fail(key,worker)->bool; status(key)->dict or None. payload is a JSON-compatible value. enqueue state queued, attempts0. claim atomically chooses oldest insertion that is queued or leased with lease_until<=now and attempts<max_attempts; increments attempts, sets owner/expiry, returns {key,payload,attempts}. Expired final-attempt jobs become failed. complete/fail require matching currently leased owner; complete sets done, fail queues again unless attempts exhausted, then failed. status returns {state,attempts}. lease>0, nonempty worker/key, max_attempts positive integer; invalid arguments raise ValueError. Separate instances/processes share the DB. No lost/duplicate live claims. Add tests and README.md.''',r'''
import sqlite3,json
class JobQueue:
 def __init__(self,path,max_attempts=3):
  if type(max_attempts)!=int or max_attempts<1:raise ValueError('attempts')
  self.path=path;self.max=max_attempts
  with self.db() as c:c.execute('create table if not exists jobs(id integer primary key,k text unique,p text,s text,a integer,owner text,until real)')
 def db(self):return sqlite3.connect(self.path,timeout=10)
 def enqueue(self,key,payload):
  if not isinstance(key,str) or not key:raise ValueError('key')
  with self.db() as c:return c.execute('insert or ignore into jobs(k,p,s,a) values(?,?,?,0)',(key,json.dumps(payload),'queued')).rowcount==1
 def claim(self,worker,now,lease):
  if not isinstance(worker,str) or not worker or lease<=0:raise ValueError('claim')
  with self.db() as c:
   c.execute('begin immediate');c.execute("update jobs set s='failed' where s='leased' and until<=? and a>=?",(now,self.max));r=c.execute("select id,k,p,a from jobs where a<? and (s='queued' or (s='leased' and until<=?)) order by id limit 1",(self.max,now)).fetchone()
   if r is None:return None
   c.execute("update jobs set s='leased',a=a+1,owner=?,until=? where id=?",(worker,now+lease,r[0]));return {'key':r[1],'payload':json.loads(r[2]),'attempts':r[3]+1}
 def complete(self,key,worker):
  with self.db() as c:return c.execute("update jobs set s='done' where k=? and owner=? and s='leased'",(key,worker)).rowcount==1
 def fail(self,key,worker):
  with self.db() as c:return c.execute("update jobs set s=case when a>=? then 'failed' else 'queued' end where k=? and owner=? and s='leased'",(self.max,key,worker)).rowcount==1
 def status(self,key):
  with self.db() as c:r=c.execute('select s,a from jobs where k=?',(key,)).fetchone();return None if r is None else {'state':r[0],'attempts':r[1]}
''',PY_COMMON+''' with tempfile.TemporaryDirectory() as d:
  q=solution.JobQueue(str(pathlib.Path(d)/'q.db'),x.get('max_attempts',3));out=[]
  for op in x.get('ops',[]):out.append(getattr(q,op[0])(*op[1:]))
  if 'concurrent' in x:
   import multiprocessing
   n=x['concurrent'];[q.enqueue(str(i),i) for i in range(n)]
   def f(i):
    other=solution.JobQueue(str(pathlib.Path(d)/'q.db'),x.get('max_attempts',3));return other.claim('worker'+str(i),100.,10.)
   with multiprocessing.get_context('fork').Pool(processes=8) as pool:claims=list(pool.map(f,range(n+8)))
   out.append(sorted([r['key'] for r in claims if r is not None],key=int))
  print(json.dumps({'value':out}))
'''+PY_END,'queue')
add('py-archive','python',r'''Implement solution.py extract_zip(archive_path,outdir)->list[str]. Extract a ZIP into a NEW directory, returning sorted member file paths. Reject with ValueError before creating any output if outdir exists, any member is absolute, contains .. components, backslashes, a drive-colon, duplicate normalized file/directory path, or a symbolic link; validate all entries before extraction. Preserve UTF-8 file contents and nested directories. No output on malformed ZIP or validation failure. Directories end with /. Empty ZIP creates empty outdir. No existing files may be overwritten. Add tests and README.md.''',r'''
import pathlib,zipfile,stat,tempfile,os,shutil
def extract_zip(archive_path,outdir):
 out=pathlib.Path(outdir)
 if out.exists():raise ValueError('exists')
 staging=None
 try:
  with zipfile.ZipFile(archive_path) as z:
   seen=set();items=[]
   for i in z.infolist():
    p=pathlib.PurePosixPath(i.filename);name=str(p)
    if not i.filename or p.is_absolute() or '..' in p.parts or '\\' in i.filename or ':' in i.filename or name in seen or stat.S_ISLNK(i.external_attr>>16):raise ValueError('unsafe')
    seen.add(name);items.append(i)
   for i in items:
    p=pathlib.PurePosixPath(i.filename)
    if any(str(parent) in seen and not any(q.is_dir() and str(pathlib.PurePosixPath(q.filename))==str(parent) for q in items) for parent in p.parents if str(parent)!='.'):raise ValueError('parent-file')
   staging=pathlib.Path(tempfile.mkdtemp(dir=out.parent))
   for i in items:
    p=staging/i.filename
    if i.is_dir():p.mkdir(parents=True,exist_ok=True)
    else:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(i))
  os.rename(staging,out);return sorted(i.filename for i in items if not i.is_dir())
 except Exception as e:
  if staging and staging.exists():shutil.rmtree(staging)
  if isinstance(e,ValueError):raise
  raise ValueError('archive') from e
''',PY_COMMON+''' import zipfile
 with tempfile.TemporaryDirectory() as d:
  d=pathlib.Path(d);p=d/'a.zip';out=d/'out'
  with zipfile.ZipFile(p,'w') as z:
   for item in x['entries']:
    i=zipfile.ZipInfo(item['name']);i.external_attr=((0o120777 if item.get('symlink') else 0o100644)<<16);z.writestr(i,item.get('text',''))
  if x.get('exists'):out.mkdir();(out/'keep').write_text('preserve')
  try:names=solution.extract_zip(str(p),str(out))
  except Exception as e:
   unchanged=(out.is_dir() and sorted(f.name for f in out.iterdir())==['keep'] and (out/'keep').read_text()=='preserve') if x.get('exists') else not out.exists();print(json.dumps({'error':type(e).__name__,'unchanged':unchanged}));sys.exit(0)
  files={str(f.relative_to(out)):f.read_text() for f in out.rglob('*') if f.is_file()};print(json.dumps({'value':names,'files':files}))
'''+PY_END,'archive')
add('py-refactor','python',r'''Repair/refactor the provided ledger.py into ledger.py (public facade) plus engine.py (implementation). Preserve process(records) API. Each record has exactly id (nonempty stripped str), category (nonempty stripped str), cents (nonnegative integer; boolean values are invalid). Validate EVERY record including duplicates. First occurrence of an id wins. Return {events:[normalized records in input order],totals:{category:sum cents}} with totals keys sorted. Never mutate inputs, retain state between calls or return shared mutable data. Invalid input raises ValueError. process([]) returns empty events/totals. Add an optional keyword-only minimum_cents=0 filter: validate all records, deduplicate first, then include unique records whose cents>=minimum_cents (nonnegative integer; boolean values are invalid). Add tests and README.md.''',r'''
def process(records,*,minimum_cents=0):
 if type(minimum_cents)!=int or minimum_cents<0:raise ValueError('minimum')
 seen=set();events=[];totals={}
 for r in records:
  if not isinstance(r,dict) or set(r)!={'id','category','cents'} or not isinstance(r['id'],str) or not r['id'].strip() or not isinstance(r['category'],str) or not r['category'].strip() or type(r['cents'])!=int or r['cents']<0:raise ValueError('record')
  v={'id':r['id'].strip(),'category':r['category'].strip(),'cents':r['cents']}
  if v['id'] in seen:continue
  seen.add(v['id'])
  if v['cents']<minimum_cents:continue
  events.append(v);totals[v['category']]=totals.get(v['category'],0)+v['cents']
 return {'events':events,'totals':dict(sorted(totals.items()))}
''',PY_COMMON.replace(' import solution',' import ledger as solution')+''' import copy
 original=copy.deepcopy(x['records']);a=solution.process(x['records'],minimum_cents=x.get('minimum',0));b=solution.process([],minimum_cents=0);print(json.dumps({'value':a,'empty':b,'input_unchanged':original==x['records']}))
'''+PY_END,'refactor',{'ledger.py':"_events=[]\ndef process(records, minimum_cents=0):\n for r in records:\n  r['category']=r['category'].strip()\n  if r['cents']>=minimum_cents:_events.append(r)\n return {'events':_events,'totals':{}}\n",'engine.py':'# Move the validated implementation here.\n'})
add('py-expression','python',r'''Implement solution.py evaluate(text)->int: integer arithmetic with +, -, *, //, parentheses and unary +/-. Follow normal precedence and Python floor division for negatives. Whitespace allowed. No eval/exec or external packages. Reject unsupported syntax, names, floats, bools, division by zero, text length>4096, integer tokens with more than50 digits, nesting/depth>100, or any intermediate abs(value)>10**100, all with ValueError. Leading-zero integer tokens may be rejected. Add tests and README.md.''',r'''
import ast,re
def evaluate(text):
 if not isinstance(text,str) or len(text)>4096 or any(len(s)>50 for s in re.findall(r'\d+',text)):raise ValueError('limit')
 depth=0
 for char in text:
  if char=='(':depth+=1
  elif char==')':depth-=1
  if depth>100:raise ValueError('depth')
 try:tree=ast.parse(text.strip(),mode='eval')
 except Exception as e:raise ValueError('syntax') from e
 def visit(n,depth=0):
  if depth>100:raise ValueError('depth')
  if isinstance(n,ast.Constant) and type(n.value)==int:v=n.value
  elif isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.UAdd,ast.USub)):v=visit(n.operand,depth+1)*(1 if isinstance(n.op,ast.UAdd) else -1)
  elif isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Add,ast.Sub,ast.Mult,ast.FloorDiv)):
   a,b=visit(n.left,depth+1),visit(n.right,depth+1)
   try:v=a+b if isinstance(n.op,ast.Add) else a-b if isinstance(n.op,ast.Sub) else a*b if isinstance(n.op,ast.Mult) else a//b
   except Exception as e:raise ValueError('arithmetic') from e
  else:raise ValueError('syntax')
  if abs(v)>10**100:raise ValueError('magnitude')
  return v
 return visit(tree.body)
''',PY_COMMON+''' print(json.dumps({'value':solution.evaluate(x['text'])}))
'''+PY_END,'expression')
CPP_COMMON=r'''#include <iostream>
#include <sstream>
#include <iomanip>
#include <string>
#include <vector>
#include <map>
#include <set>
#include <algorithm>
#include <thread>
#include <memory>
#include <atomic>
#include <type_traits>
#include <cstdint>
#include <stdexcept>
#include "solution.hpp"
std::string js(const std::string&s){std::ostringstream o;o<<'"';for(unsigned char c:s){if(c=='"'||c=='\\')o<<'\\'<<c;else if(c=='\n')o<<"\\n";else if(c=='\r')o<<"\\r";else if(c=='\t')o<<"\\t";else if(c<32)o<<"\\u00"<<std::hex<<std::setw(2)<<std::setfill('0')<<(int)c<<std::dec;else o<<c;}o<<'"';return o.str();}
int main(){try{
'''
CPP_END=r'''}catch(const std::exception&e){std::cout<<"{\"error\":\"ValueError\"}";}catch(...){std::cout<<"{\"error\":\"ValueError\"}";}std::cout<<std::endl;}
'''
add('cpp-csv','cpp',r'''C++20, implement header-only solution.hpp: std::map<std::string,std::int64_t> aggregate(std::istream&). Parse CSV whose header is exactly category,amount; amount is a signed base10 int64 integer (optional + or -, no decimals/exponents/whitespace within digits). Strip outer spaces/tabs/CR from fields, category nonempty. Quoted fields allow commas, newlines and escaped double quotes. Empty physical records ignored. Reject malformed quoting, wrong field count/header, empty fields and overflow in parsing OR category accumulation with std::invalid_argument (other std::exception accepted as error by driver). Do not load all input merely to parse it. Return map's sorted keys. Add tests and README.md.''',r'''
#pragma once
#include <map>
#include <string>
#include <cstdint>
#include <istream>
#include <stdexcept>
#include <limits>
#include <vector>
inline std::map<std::string,std::int64_t> aggregate(std::istream& in){
 std::map<std::string,std::int64_t> out;std::vector<std::string> row;std::string f;bool quote=false,closed=false,at_start=true,header=false;int ch;
 auto trim=[](std::string s){auto a=s.find_first_not_of(" \t\r"),b=s.find_last_not_of(" \t\r");return a==std::string::npos?std::string():s.substr(a,b-a+1);};
 auto record=[&]{if(row.empty()&&f.empty()&&!closed)return;row.push_back(f);f.clear();closed=false;at_start=true;if(!header){if(row!=std::vector<std::string>{"category","amount"})throw std::invalid_argument("header");header=true;}else{if(row.size()!=2)throw std::invalid_argument("columns");auto k=trim(row[0]),v=trim(row[1]);if(k.empty()||v.empty())throw std::invalid_argument("empty");std::size_t p=0;if(v[0]=='+'||v[0]=='-')p++;if(p==v.size())throw std::invalid_argument("number");for(auto i=p;i<v.size();i++)if(v[i]<'0'||v[i]>'9')throw std::invalid_argument("digit");std::size_t end=0;auto n=std::stoll(v,&end);if(end!=v.size())throw std::invalid_argument("number");auto old=out[k];if((n>0&&old>std::numeric_limits<std::int64_t>::max()-n)||(n<0&&old<std::numeric_limits<std::int64_t>::min()-n))throw std::invalid_argument("overflow");out[k]=old+n;}row.clear();};
 while((ch=in.get())!=EOF){char c=ch;if(quote){if(c=='"'){if(in.peek()=='"'){in.get();f+='"';}else{quote=false;closed=true;}}else f+=c;continue;}if(c=='"'){if(!at_start||closed)throw std::invalid_argument("quote");quote=true;at_start=false;}else if(c==','){row.push_back(f);f.clear();at_start=true;closed=false;}else if(c=='\n'){record();}else{if(closed&&c!='\r')throw std::invalid_argument("after quote");if(!closed){f+=c;at_start=false;}}}
 if(quote)throw std::invalid_argument("quote");record();if(!header)throw std::invalid_argument("header");return out;
}
''',CPP_COMMON+r'''std::string text;std::cin>>std::quoted(text);std::istringstream in(text);auto out=aggregate(in);std::cout<<"{\"value\":{";bool first=true;for(auto&[k,v]:out){if(!first)std::cout<<',';first=false;std::cout<<js(k)<<':'<<v;}std::cout<<"}}";
'''+CPP_END,'cpp_csv')
add('cpp-queue','cpp',r'''C++20 header-only solution.hpp: template<class T> class BoundedQueue. Explicit ctor(size_t capacity), bool push(T value), std::optional<T> pop(), void close(). Capacity zero throws std::invalid_argument. push blocks while full, returns false after close; pop blocks while empty/open, drains queued values after close, then returns nullopt. close is idempotent and wakes ALL waiting producers/consumers. FIFO; supports move-only T. Must be thread-safe and release resources on ordinary clean shutdown. Callers close then join before destruction. Add tests and README.md.''',r'''
#pragma once
#include <mutex>
#include <condition_variable>
#include <deque>
#include <optional>
#include <stdexcept>
template<class T> class BoundedQueue{std::mutex m;std::condition_variable a,b;std::deque<T> q;std::size_t cap;bool done=false;public:explicit BoundedQueue(std::size_t n):cap(n){if(!n)throw std::invalid_argument("capacity");}bool push(T v){std::unique_lock l(m);b.wait(l,[&]{return done||q.size()<cap;});if(done)return false;q.push_back(std::move(v));a.notify_one();return true;}std::optional<T> pop(){std::unique_lock l(m);a.wait(l,[&]{return done||!q.empty();});if(q.empty())return {};T v=std::move(q.front());q.pop_front();b.notify_one();return v;}void close(){std::lock_guard l(m);done=true;a.notify_all();b.notify_all();}};
''',CPP_COMMON+r'''int mode,cap,n,p;std::cin>>mode>>cap>>n>>p;if(mode==0){BoundedQueue<int> q(cap);q.close();q.close();std::cout<<"{\"value\":["<<(q.push(1)?"true":"false")<<','<<(q.pop()?"true":"false")<<"]}";}else if(mode==3){BoundedQueue<int> q(1);q.push(17);std::atomic<bool> started=false,accepted=true;std::thread t([&]{started=true;accepted=q.push(23);});while(!started.load())std::this_thread::yield();q.close();t.join();auto a=q.pop(),b=q.pop();std::cout<<"{\"value\":["<<(accepted?"true":"false")<<','<<a.value_or(-1)<<','<<(b?"true":"false")<<"]}";}else if(mode==2){BoundedQueue<std::unique_ptr<int>> q(cap);q.push(std::make_unique<int>(n));q.close();auto v=q.pop();std::cout<<"{\"value\":"<<**v<<'}';}else{BoundedQueue<int> q(cap);std::vector<int> got;std::mutex m;std::vector<std::thread> workers;for(int j=0;j<p;j++)workers.emplace_back([&]{while(auto v=q.pop()){std::lock_guard l(m);got.push_back(*v);}});std::vector<std::thread> prod;for(int j=0;j<p;j++)prod.emplace_back([&,j]{for(int i=j;i<n;i+=p){if(!q.push(i))throw std::runtime_error("closed early");std::this_thread::yield();}});for(auto&t:prod)t.join();q.close();for(auto&t:workers)t.join();std::sort(got.begin(),got.end());std::cout<<"{\"value\":[";for(std::size_t i=0;i<got.size();i++){if(i)std::cout<<',';std::cout<<got[i];}std::cout<<"]}";}
'''+CPP_END,'cpp_queue')
add('cpp-buffer','cpp',r'''Repair the provided Buffer library in solution.hpp, C++20. Buffer(size_t n=0), size() const noexcept, mutable/const operator[](size_t) with bounds-check out_of_range, resize(size_t) preserving prefix and zero-initializing new bytes. Elements uint8_t. Deep-copy construction/assignment; noexcept move construction/assignment; moved-from buffers size0 and reusable; self-copy/self-move preserve content. Use RAII, no leaks, double frees, stale reads or undefined behavior. Standard containers are allowed. Add tests and README.md.''',r'''
#pragma once
#include <vector>
#include <cstdint>
#include <utility>
class Buffer{std::vector<std::uint8_t> v;public:explicit Buffer(std::size_t n=0):v(n,0){}Buffer(const Buffer&)=default;Buffer&operator=(const Buffer&)=default;Buffer(Buffer&&o)noexcept:v(std::move(o.v)){o.v.clear();}Buffer&operator=(Buffer&&o)noexcept{if(this!=&o){v=std::move(o.v);o.v.clear();}return *this;}std::size_t size()const noexcept{return v.size();}std::uint8_t&operator[](std::size_t i){return v.at(i);}const std::uint8_t&operator[](std::size_t i)const{return v.at(i);}void resize(std::size_t n){v.resize(n,0);}};
''',CPP_COMMON+r'''static_assert(std::is_nothrow_move_constructible_v<Buffer> && std::is_nothrow_move_assignable_v<Buffer>);int n,grow;std::cin>>n>>grow;Buffer a(n);for(int i=0;i<n;i++){int v;std::cin>>v;a[i]=v;}Buffer b=a;if(n)b[0]^=255;Buffer c=std::move(b);std::size_t old=b.size();a=a;a=std::move(a);a.resize(grow);bool checked=false;try{(void)a[a.size()];}catch(const std::out_of_range&){checked=true;}const Buffer& ca=a;std::cout<<"{\"value\":[";for(std::size_t i=0;i<ca.size();i++){if(i)std::cout<<',';std::cout<<(int)ca[i];}std::cout<<"],\"moved_size\":"<<old<<",\"copy\":[";for(std::size_t i=0;i<c.size();i++){if(i)std::cout<<',';std::cout<<(int)c[i];}std::cout<<"],\"bounds\":"<<(checked?"true":"false")<<'}';
'''+CPP_END,'cpp_buffer',{'solution.hpp':'#pragma once\n#include <cstdint>\n#include <cstddef>\nclass Buffer{std::uint8_t* p;std::size_t n;public:Buffer(std::size_t n=0):p(new std::uint8_t[n]),n(n){}~Buffer(){delete p;}std::size_t size()const{return n;}std::uint8_t&operator[](std::size_t i){return p[i];}void resize(std::size_t k){n=k;}};\n'})
add('cpp-binary','cpp',r'''C++20 solution.hpp: struct Record{uint32_t id;std::string name;int64_t value;}; std::vector<uint8_t> encode(const std::vector<Record>&); std::vector<Record> decode(std::span<const uint8_t>). Format: ASCII OGC1, uint32 count little-endian, then each uint32 id, uint16 name length, name raw bytes, int64 value little-endian two's-complement. Count <=10000, name bytes<=1024, IDs unique. Reject violations, truncation, bad magic, overflow and trailing bytes with std::exception. Empty records valid. No UB from unaligned reads or signed shifts. Add tests and README.md.''',r'''
#pragma once
#include <vector>
#include <string>
#include <span>
#include <set>
#include <cstdint>
#include <bit>
#include <stdexcept>
struct Record{std::uint32_t id;std::string name;std::int64_t value;};
inline std::vector<std::uint8_t> encode(const std::vector<Record>&r){if(r.size()>10000)throw std::invalid_argument("count");std::vector<std::uint8_t>b={'O','G','C','1'};auto put=[&](std::uint64_t n,int bytes){for(int i=0;i<bytes;i++)b.push_back(n>>(8*i));};put(r.size(),4);std::set<std::uint32_t>seen;for(auto&v:r){if(v.name.size()>1024||!seen.insert(v.id).second)throw std::invalid_argument("record");put(v.id,4);put(v.name.size(),2);b.insert(b.end(),v.name.begin(),v.name.end());put(std::bit_cast<std::uint64_t>(v.value),8);}return b;}
inline std::vector<Record> decode(std::span<const std::uint8_t>b){std::size_t p=0;auto get=[&](int n){if((std::size_t)n>b.size()-p)throw std::invalid_argument("truncated");std::uint64_t v=0;for(int i=0;i<n;i++)v|=std::uint64_t(b[p++])<<(8*i);return v;};if(get(4)!=0x3143474f)throw std::invalid_argument("magic");auto count=get(4);if(count>10000)throw std::invalid_argument("count");std::set<std::uint32_t>seen;std::vector<Record>r;for(std::uint64_t i=0;i<count;i++){auto id=(std::uint32_t)get(4);auto n=get(2);if(n>1024||n>b.size()-p||!seen.insert(id).second)throw std::invalid_argument("record");std::string name((const char*)b.data()+p,n);p+=n;r.push_back({id,name,std::bit_cast<std::int64_t>(get(8))});}if(p!=b.size())throw std::invalid_argument("trailing");return r;}
''',CPP_COMMON+r'''int mode;std::cin>>mode;std::vector<std::uint8_t> bytes;if(mode==0){int n;std::cin>>n;std::vector<Record> r;for(int i=0;i<n;i++){Record a;std::cin>>a.id>>std::quoted(a.name)>>a.value;r.push_back(a);}bytes=encode(r);}else{std::string h;std::cin>>h;for(std::size_t i=0;i<h.size();i+=2)bytes.push_back(std::stoul(h.substr(i,2),nullptr,16));}auto out=decode(bytes);std::cout<<"{\"value\":[";for(std::size_t i=0;i<out.size();i++){if(i)std::cout<<',';std::cout<<"["<<out[i].id<<','<<js(out[i].name)<<','<<out[i].value<<']';}std::cout<<"],\"hex\":\""<<std::hex<<std::setfill('0');for(auto v:bytes)std::cout<<std::setw(2)<<(int)v;std::cout<<"\"}";
'''+CPP_END,'cpp_binary')
add('cpp-stats','cpp',r'''Refactor/repair this CMake project. Required files include/stats.hpp, src/stats.cpp, CMakeLists.txt. CMake target stats must be a library publicly exposing include/ and C++20. Public class RunningStats: void add(double), void merge(const RunningStats&), uint64_t count() const, double mean() const, double variance() const, double minimum() const, double maximum() const. variance is population variance. Empty mean/variance/minimum/maximum throw std::domain_error. Reject NaN/infinity with std::invalid_argument without changing state. merge empty is no-op; merging into empty copies; self-merge doubles count without changing mean/variance. Use stable online/merge formulas: results for offset1e9 inputs must stay within absolute1e-4 + relative1e-6 tolerance of a high-accuracy reference. Keep functions in proper files, clean CMake build. Add tests and README.md.''',r'''
#pragma once
#include <cstdint>
#include <cmath>
#include <algorithm>
#include <stdexcept>
class RunningStats{std::uint64_t n=0;double avg=0,m2=0,lo=0,hi=0;public:void add(double x){if(!std::isfinite(x))throw std::invalid_argument("finite");if(!n){lo=hi=avg=x;n=1;return;}lo=std::min(lo,x);hi=std::max(hi,x);n++;double d=x-avg;avg+=d/n;m2+=d*(x-avg);}void merge(const RunningStats&o){if(!o.n)return;if(!n){*this=o;return;}auto a=n,b=o.n;double otherAvg=o.avg,otherM2=o.m2,otherLo=o.lo,otherHi=o.hi;double d=otherAvg-avg;avg+=d*double(b)/(a+b);m2+=otherM2+d*d*double(a)*double(b)/(a+b);n=a+b;lo=std::min(lo,otherLo);hi=std::max(hi,otherHi);}std::uint64_t count()const{return n;}double mean()const{if(!n)throw std::domain_error("empty");return avg;}double variance()const{if(!n)throw std::domain_error("empty");return m2/n;}double minimum()const{if(!n)throw std::domain_error("empty");return lo;}double maximum()const{if(!n)throw std::domain_error("empty");return hi;}};
''',CPP_COMMON.replace('#include "solution.hpp"','#include "stats.hpp"')+r'''int n,split,self;std::cin>>n>>split>>self;RunningStats a,b;for(int i=0;i<n;i++){std::string token;std::cin>>token;double x=std::stod(token);if(i<split)a.add(x);else b.add(x);}a.merge(b);if(self)a.merge(a);auto count=a.count();auto mean=a.mean();auto var=a.variance();auto minimum=a.minimum();auto maximum=a.maximum();std::cout<<std::setprecision(17)<<"{\"value\":["<<count<<','<<mean<<','<<var<<','<<minimum<<','<<maximum<<"]}";
'''+CPP_END,'cpp_stats',{'include/stats.hpp':'#pragma once\n#include <cstdint>\nclass RunningStats{public:void add(double);void merge(const RunningStats&);std::uint64_t count()const;double mean()const;double variance()const;double minimum()const;double maximum()const;private:std::uint64_t n=0;double sum=0,squares=0;};\n','src/stats.cpp':'#include "stats.hpp"\nvoid RunningStats::add(double x){n++;sum+=x;squares+=x*x;}void RunningStats::merge(const RunningStats&o){n+=o.n;sum+=o.sum;squares+=o.squares;}std::uint64_t RunningStats::count()const{return n;}double RunningStats::mean()const{return sum/n;}double RunningStats::variance()const{return squares/n-mean()*mean();}double RunningStats::minimum()const{return 0;}double RunningStats::maximum()const{return 0;}\n','CMakeLists.txt':'cmake_minimum_required(VERSION 3.20)\nproject(stats LANGUAGES CXX)\nadd_library(stats src/stats.cpp)\ntarget_include_directories(stats PUBLIC include)\ntarget_compile_features(stats PUBLIC cxx_std_20)\n'})
add('cpp-lru','cpp',r'''Implement C++20 solution.hpp LruCache(size_t capacity): void put(int key,std::string value), bool get(int key,std::string& out), bool erase(int key), size_t size()const, std::vector<std::pair<int,std::string>> snapshot()const. Most recently used first. Successful get and every put make key MRU; miss leaves out unchanged. Updating an existing key does not evict another. On overflow evict LRU. Capacity0 stores nothing. erase true only for existing key; snapshot does not affect recency. Average O(1) get/put/erase; correct RAII. Copying may be disabled. Add tests and README.md.''',r'''
#pragma once
#include <list>
#include <unordered_map>
#include <vector>
#include <string>
class LruCache{using Item=std::pair<int,std::string>;std::size_t cap;std::list<Item> q;std::unordered_map<int,std::list<Item>::iterator> index;public:explicit LruCache(std::size_t n):cap(n){}LruCache(const LruCache&)=delete;LruCache&operator=(const LruCache&)=delete;void put(int k,std::string v){auto i=index.find(k);if(i!=index.end()){i->second->second=std::move(v);q.splice(q.begin(),q,i->second);return;}if(!cap)return;q.emplace_front(k,std::move(v));index[k]=q.begin();if(q.size()>cap){index.erase(q.back().first);q.pop_back();}}bool get(int k,std::string&v){auto i=index.find(k);if(i==index.end())return false;v=i->second->second;q.splice(q.begin(),q,i->second);return true;}bool erase(int k){auto i=index.find(k);if(i==index.end())return false;q.erase(i->second);index.erase(i);return true;}std::size_t size()const{return q.size();}std::vector<Item>snapshot()const{return {q.begin(),q.end()};}};
''',CPP_COMMON+r'''int cap,n;std::cin>>cap>>n;LruCache q(cap);std::cout<<"{\"value\":[";for(int i=0;i<n;i++){if(i)std::cout<<',';char op;int k;std::cin>>op;if(op=='P'){std::string v;std::cin>>k>>std::quoted(v);q.put(k,v);std::cout<<"null";}else if(op=='G'){std::cin>>k;std::string v="UNCHANGED";bool ok=q.get(k,v);std::cout<<"["<<(ok?"true":"false")<<','<<js(v)<<']';}else if(op=='E'){std::cin>>k;std::cout<<(q.erase(k)?"true":"false");}else if(op=='S'){std::cout<<'[';bool first=true;for(auto&[a,b]:q.snapshot()){if(!first)std::cout<<',';first=false;std::cout<<'['<<a<<','<<js(b)<<']';}std::cout<<']';}else throw std::invalid_argument("op");}std::cout<<"],\"size\":"<<q.size()<<'}';
'''+CPP_END,'cpp_lru')
# Frozen integration tasks, independent modules and explicit interfaces for team-size comparisons.
TEAM_NORMALIZE='''def normalize(records):
 out=[]
 for r in records:
  if not isinstance(r,dict) or set(r)!={'id','category','cents'} or not isinstance(r['id'],str) or not r['id'].strip() or not isinstance(r['category'],str) or not r['category'].strip() or type(r['cents'])!=int or r['cents']<0:raise ValueError('record')
  out.append({'id':r['id'].strip(),'category':r['category'].strip(),'cents':r['cents']})
 return out
'''
TEAM_DEDUP='''def deduplicate(records):
 seen=set();out=[]
 for r in records:
  if r['id'] not in seen:seen.add(r['id']);out.append(dict(r))
 return out
'''
TEAM_FACADE='''from validation import normalize
from storage import deduplicate
def process(records,*,minimum_cents=0):
 if type(minimum_cents)!=int or minimum_cents<0:raise ValueError('minimum')
 events=[r for r in deduplicate(normalize(records)) if r['cents']>=minimum_cents];totals={}
 for r in events:totals[r['category']]=totals.get(r['category'],0)+r['cents']
 return {'events':events,'totals':dict(sorted(totals.items()))}
'''
add('py-team','python',TASKS['py-refactor']['contract'].replace('provided ledger.py into ledger.py (public facade) plus engine.py (implementation)','ledger toolkit into THREE modules')+''' Required module interfaces: validation.py normalize(records)->list of fresh normalized records, validating all records and preserving duplicates; storage.py deduplicate(records)->list of fresh copies, retaining first id in input order (input already validated); ledger.py process imports and composes both helpers. No hidden global state; do not mutate input. Explicit module boundaries are required for integration. For partial work, obey the exact write scope in your assignment.''',TEAM_FACADE,TASKS['py-refactor']['driver'],'py_team',{'validation.py':'def normalize(records):\n raise NotImplementedError\n','storage.py':'def deduplicate(records):\n raise NotImplementedError\n','ledger.py':'def process(records,*,minimum_cents=0):\n raise NotImplementedError\n'})
add('py-normalizer','python','Implement ONLY validation.py normalize(records) per the team contract: exact id/category/cents fields; strip nonempty string id/category; cents nonnegative int excluding bool. Validate every record; preserve duplicates/order; return new dictionaries; no input mutation. Invalid input ValueError. README.md required.',TEAM_NORMALIZE,PY_COMMON.replace(' import solution',' import validation as solution')+''' import copy
 original=copy.deepcopy(x['records']);v=solution.normalize(x['records']);print(json.dumps({'value':v,'input_unchanged':x['records']==original}))
'''+PY_END,'py_normalizer')
cpp_parts={k:TASKS[k]['driver'][len(CPP_COMMON):-len(CPP_END)] for k in ['cpp-csv','cpp-lru']}
cpp_parts['cpp-stats']=TASKS['cpp-stats']['driver'].split('int main(){try{\n',1)[1][:-len(CPP_END)]
combined=CPP_COMMON+'int part;std::cin>>part;if(part==0){'+cpp_parts['cpp-csv']+'}else if(part==1){'+cpp_parts['cpp-lru']+'}else if(part==2){'+cpp_parts['cpp-stats']+r'''}else if(part==3){std::string text;std::cin>>std::quoted(text);std::istringstream in(text);auto totals=aggregate(in);LruCache cache(2);RunningStats stats;int index=0;for(auto&[key,value]:totals){cache.put(index++,key+":"+std::to_string(value));stats.add(double(value));}std::cout<<"{\"totals\":{";bool first=true;for(auto&[key,value]:totals){if(!first)std::cout<<',';first=false;std::cout<<js(key)<<':'<<value;}std::cout<<"},\"cache\":[";first=true;for(auto&[key,value]:cache.snapshot()){if(!first)std::cout<<',';first=false;std::cout<<'['<<key<<','<<js(value)<<']';}std::cout<<"],\"stats\":["<<stats.count();if(stats.count())std::cout<<','<<std::setprecision(17)<<stats.mean()<<','<<stats.variance();std::cout<<"]}";}else throw std::invalid_argument("part");
'''+CPP_END
add('cpp-team','cpp','Build a header-only local analytics toolkit in C++20. Required files parser.hpp, cache.hpp, stats.hpp and solution.hpp umbrella including all three. Implement the following three public APIs exactly; ordinary stdlib use permitted. The integration driver also parses CSV, pushes sorted category totals into a two-item LRU cache and accumulates RunningStats over those totals. Module boundaries are mandatory. Scope individual partial assignments carefully.\n\n'+TASKS['cpp-csv']['contract'].replace('solution.hpp','parser.hpp')+'\n'+TASKS['cpp-lru']['contract'].replace('solution.hpp','cache.hpp')+'\nRunningStats header-only in stats.hpp, same API and semantics as this contract:\n'+TASKS['cpp-stats']['contract'].replace('Required files include/stats.hpp, src/stats.cpp, CMakeLists.txt. CMake target stats must be a library publicly exposing include/ and C++20.','For this toolkit, header-only stats.hpp; no CMake required.').replace('Keep functions in proper files, clean CMake build.','Keep the class in stats.hpp.'),'',combined,'cpp_team',{'solution.hpp':'#pragma once\n#include "parser.hpp"\n#include "cache.hpp"\n#include "stats.hpp"\n','parser.hpp':'#pragma once\n// Implement aggregate(std::istream&).\n','cache.hpp':'#pragma once\n// Implement LruCache.\n','stats.hpp':'#pragma once\n// Implement RunningStats.\n'})
TASKS['cpp-stats']['reference_files']={'include/stats.hpp':r'''#pragma once
#include <cstdint>
class RunningStats{std::uint64_t n=0;double avg=0,m2=0,lo=0,hi=0;public:void add(double);void merge(const RunningStats&);std::uint64_t count()const;double mean()const;double variance()const;double minimum()const;double maximum()const;};
''','src/stats.cpp':r'''#include "stats.hpp"
#include <cmath>
#include <algorithm>
#include <stdexcept>
void RunningStats::add(double x){if(!std::isfinite(x))throw std::invalid_argument("finite");if(!n){lo=hi=avg=x;n=1;return;}lo=std::min(lo,x);hi=std::max(hi,x);n++;double d=x-avg;avg+=d/n;m2+=d*(x-avg);}
void RunningStats::merge(const RunningStats&o){if(!o.n)return;if(!n){*this=o;return;}auto a=n,b=o.n;double otherAvg=o.avg,otherM2=o.m2,otherLo=o.lo,otherHi=o.hi;double d=otherAvg-avg;avg+=d*double(b)/(a+b);m2+=otherM2+d*d*double(a)*double(b)/(a+b);n=a+b;lo=std::min(lo,otherLo);hi=std::max(hi,otherHi);}
std::uint64_t RunningStats::count()const{return n;}double RunningStats::mean()const{if(!n)throw std::domain_error("empty");return avg;}double RunningStats::variance()const{if(!n)throw std::domain_error("empty");return m2/n;}double RunningStats::minimum()const{if(!n)throw std::domain_error("empty");return lo;}double RunningStats::maximum()const{if(!n)throw std::domain_error("empty");return hi;}
''','CMakeLists.txt':TASKS['cpp-stats']['starter']['CMakeLists.txt']}
