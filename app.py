import os,json,sqlite3,threading,time,uuid,urllib.request,hmac
from flask import Flask,request,jsonify,send_from_directory,session
app=Flask(__name__)
app.secret_key=os.getenv('SECRET_KEY') or os.urandom(32)
lock=threading.RLock()
DB=os.getenv('DB_PATH','tavern.db')
MODEL=os.getenv('MODEL','qwen2.5:1.5b')
BASE=os.getenv('LLM_URL','http://127.0.0.1:11434/v1')
KEY=os.getenv('LLM_KEY','')
MODE=os.getenv('MODE','demo')
ACCESS=os.getenv('TAVERN_ACCESS_CODE','')
MAX_CALLS=max(1,int(os.getenv('MAX_DAILY_CALLS','100')))
app.config['MAX_CONTENT_LENGTH']=8192
with sqlite3.connect(DB) as c: c.execute('create table if not exists inference_usage(day text primary key, calls integer not null)')
PEOPLE=[dict(id='edmund',name='Edmund',role='Innkeeper',trait='Proud, pragmatic, cautious',goal='Protect the tavern and conceal debt',secret='Roland demanded repayment yesterday.',color='#d7a254',place='bar'),dict(id='marta',name='Marta',role='Merchant',trait='Ambitious, impatient, suspicious',goal='Recover missing shipment',secret='The shipment contained valuable silk.',color='#78b9b1',place='table'),dict(id='roland',name='Roland',role='Guard',trait='Loyal, insecure, defensive',goal='Protect reputation and find evidence',secret='Saw an unfamiliar cart near the warehouse.',color='#b77c7c',place='door'),dict(id='isabel',name='Isabel',role='Traveler',trait='Observant, secretive, wary',goal='Leave town safely',secret='Saw a cart with a broken wheel near the warehouse.',color='#a69bcc',place='fire')]
def conn(): return sqlite3.connect(DB)
with conn() as c: c.execute('create table if not exists worlds(id text primary key,state text)')
def fresh(): return {'tick':0,'events':[],'npcs':[{**p,'memory':[],'trust':{q['id']:50 for q in PEOPLE if q!=p}|{'player':50}} for p in PEOPLE],'calls':0}
def load():
 if MODE=='local': session['world']='local-v2'
 if 'world' not in session: session['world']=uuid.uuid4().hex
 with conn() as c: r=c.execute('select state from worlds where id=?',(session['world'],)).fetchone()
 return json.loads(r[0]) if r else fresh()
def save(s):
 with conn() as c: c.execute('insert or replace into worlds values(?,?)',(session['world'],json.dumps(s)))
def public(s): return {**s,'mode':MODE,'model':MODEL,'locked':MODE not in ('demo','local') and not session.get('ai_authorized'), 'limit':MAX_CALLS}
@app.post('/api/unlock')
def unlock():
 b=request.get_json(silent=True) or {}
 if not ACCESS or not hmac.compare_digest(str(b.get('code','')),ACCESS): return jsonify(error='Incorrect access code.'),403
 session['ai_authorized']=True
 return {'ok':True}
def reserve_call():
 day=time.strftime('%Y-%m-%d',time.gmtime())
 with conn() as c:
  c.execute('begin immediate')
  row=c.execute('select calls from inference_usage where day=?',(day,)).fetchone()
  if row and row[0]>=MAX_CALLS: return False
  c.execute('insert into inference_usage values(?,1) on conflict(day) do update set calls=calls+1',(day,))
 return True
def decide(s,p,target,msg):
 if MODE=='demo':
  s['inference']={'source':'scripted demo'}
  lines={'edmund':['Keep your voice down. My tavern has enough troubles.','Perhaps Marta knows more about the shipment.','I should check the bar.'],'marta':['I need evidence, not another rumor. Will you help me?','The shipment contained valuable silk.','I must speak to the guard.'],'roland':['I am investigating. Do not mistake suspicion for proof.','I saw an unfamiliar cart near the warehouse.','I should keep watch at the door.'],'isabel':['There are things I would rather not discuss in public.','I noticed a cart with a broken wheel.','I prefer to stay near the fire.']}
  phase=sum('said' in m for m in p['memory'])%3
  delta=2 if any(w in msg.lower() for w in ['help','thank','friend']) else -2 if 'liar' in msg.lower() else 0
  return {'dialogue':lines[p['id']][phase],'action':'move' if phase==2 and target!='player' else 'speak','place':{'edmund':'bar','marta':'door','roland':'door','isabel':'fire'}[p['id']],'trust_delta':delta}
 prompt=f"You are {p['name']}, a {p['role']} in a medieval tavern. Personality: {p['trait']}. Answer the latest question directly and naturally before pursuing your goals. Introduce yourself when asked who you are. Clarify confusion. Do not force the shipment into unrelated conversations. Motivation: {p['goal']}. Private knowledge: {p['secret']}. Reveal only when appropriate. Reply with spoken dialogue only, no JSON."
 messages=[{'role':'system','content':prompt}]
 for m in [m for m in p['memory'] if m.get('target')==target][-4:]:
  if m.get('heard'): messages.append({'role':'user','content':str(m['heard'])[:350]})
  if m.get('said'): messages.append({'role':'assistant','content':str(m['said'])[:350]})
 messages.append({'role':'user','content':msg})
 body={'model':MODEL,'messages':messages,'temperature':0.7,'max_tokens':100,'stream':False}
 diagnostic={'source':'LLM pending','model':MODEL,'messages':messages,'raw_response':'','error':None}
 if MODE=='local': diagnostic['endpoint']=BASE
 s['inference']=diagnostic
 start=time.monotonic()
 try:
  if MODE=='local' and BASE.rstrip('/')!='http://127.0.0.1:11434/v1': raise ValueError('Local mode requires loopback Ollama')
  req=urllib.request.Request(BASE.rstrip('/')+'/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+KEY})
  with urllib.request.urlopen(req,timeout=120) as r: data=json.load(r)
  raw=data['choices'][0]['message']['content']
  diagnostic['raw_response']=raw
  if not isinstance(raw,str) or not raw.strip(): raise ValueError('Empty model reply')
  diagnostic['source']='LLM'
  diagnostic['usage']=data.get('usage')
  s['calls']+=1
  return {'dialogue':raw.strip(),'action':'speak','place':p['place'],'trust_delta':0}
 except Exception as exc:
  diagnostic['source']='error - no scripted fallback'
  diagnostic['error']=str(exc) if MODE=='local' else type(exc).__name__
  raise
 finally:
  s['last_latency']=round(time.monotonic()-start,2)
  diagnostic['latency_seconds']=s['last_latency']

def act(s,p,target,msg):
 d=decide(s,p,target,msg); action=d.get('action','speak'); action=action if action in ['speak','ask','refuse','move','wait'] else 'wait'; dialogue=str(d.get('dialogue',''))[:350]; delta=d.get('trust_delta',0); delta=max(-5,min(5,delta)) if type(delta)==int else 0
 if action=='move' and d.get('place') in ['bar','table','door','fire']: p['place']=d['place']
 p['trust'][target]=max(0,min(100,p['trust'].get(target,50)+delta)); s['tick']+=1
 e={'tick':s['tick'],'speaker':p['name'],'target':target,'input':msg,'dialogue':dialogue,'action':action,'source':s.get('inference',{}).get('source','unknown')}; s['events'].append(e); s['events']=s['events'][-200:]; p['memory'].append({'heard':msg,'said':dialogue,'target':target}); p['memory']=p['memory'][-100:]
 if target!='player' and action in ('speak','ask','refuse'):
  q=next(n for n in s['npcs'] if n['id']==target); q['memory'].append({'heard':dialogue,'from':p['name']}); q['memory']=q['memory'][-100:]
 return e
@app.get('/')
def index(): return send_from_directory('.', 'index.html')
@app.get('/health')
def health(): return {'ok':True,'mode':MODE}
@app.get('/api/state')
def state():
 with lock:
  s=load();save(s);return jsonify(public(s))
@app.post('/api/turn')
def turn():
 with lock:
  s=load(); b=request.get_json() or {}; npc=b.get('npc'); msg=str(b.get('message',''))[:500]
  try:
   if npc=='auto':
    p=s['npcs'][s['tick']%4]; q=s['npcs'][(s['tick']+1)%4]; target=q['id']; msg='Choose your next action toward '+q['name']+' at '+q['place']+' in pursuit of your goal.'
   else:
    p=next(n for n in s['npcs'] if n['id']==npc);target='player'
   if MODE!='demo':
    if MODE!='local' and (not KEY or not ACCESS): return jsonify(error='Cloud model credentials and access code must be configured.'),503
    if MODE!='local' and not session.get('ai_authorized'): return jsonify(error='Unlock cloud AI first.'),403
    if not reserve_call(): return jsonify(error='Daily AI decision limit reached.'),429
   act(s,p,target,msg);save(s);return jsonify(public(s))
  except Exception:
   app.logger.exception('Decision failed')
   save(s)
   return jsonify(error='Decision failed. See inference diagnostics.',state=public(s)),502
@app.post('/api/reset')
def reset():
 with lock:
  s=fresh();save(s);return jsonify(public(s))
if __name__=='__main__': app.run(host='127.0.0.1',port=8000)
