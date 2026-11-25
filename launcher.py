"""Local Windows launcher. Updates only on launch or explicit request."""
import os, sys, subprocess, time, hashlib, secrets, webbrowser, urllib.request, json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
os.chdir(ROOT)
PY=ROOT/'.venv'/'Scripts'/'python.exe'
MARK=ROOT/'.restart-request'
STAMP=ROOT/'.venv'/'requirements.sha256'
URL='http://127.0.0.1:8000'
def run(args, timeout=120):
    return subprocess.run(args,timeout=timeout,check=True)
def reachable(url):
    try:
        with urllib.request.urlopen(url,timeout=2) as r: return r.status==200
    except Exception: return False
def update():
    try:
        dirty=subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],timeout=10,text=True)
        if dirty.strip():
            print('Tracked edits detected; skipping update to preserve your work.',flush=True)
            return
        run(['git','pull','--ff-only'],45)
    except (OSError,subprocess.SubprocessError) as e:
        print('Update unavailable; using installed code:',e,flush=True)
def dependencies():
    if not PY.exists(): run([sys.executable,'-m','venv','.venv'])
    digest=hashlib.sha256(Path('requirements.txt').read_bytes()).hexdigest()
    if not STAMP.exists() or STAMP.read_text()!=digest:
        run([str(PY),'-m','pip','install','-r','requirements.txt'],300)
        STAMP.write_text(digest)
def main():
    if reachable(URL+'/health'):
        print('A tavern server is already running. Close it before launching again.')
        webbrowser.open(URL)
        return
    offline='--offline' in sys.argv
    if not offline: update()
    dependencies()
    env=os.environ.copy()
    env.update(MODE='local',MODEL=Path('model.txt').read_text().strip() if Path('model.txt').exists() else 'qwen2.5:1.5b',LLM_URL='http://127.0.0.1:11434/v1',MAX_DAILY_CALLS='10000',OLLAMA_NUM_PARALLEL='1',OLLAMA_CONTEXT_LENGTH='2048')
    if not reachable('http://127.0.0.1:11434/api/tags'):
        subprocess.Popen(['ollama','serve'],env=env)
        for _ in range(30):
            if reachable('http://127.0.0.1:11434/api/tags'): break
            time.sleep(1)
        else: raise RuntimeError('Ollama did not start')
    first=True
    while True:
        token=secrets.token_hex(32)
        env['TAVERN_RESTART_TOKEN']=token
        if MARK.exists(): MARK.unlink()
        child=subprocess.Popen([str(PY),'app.py'],env=env)
        restart=False
        try:
            for _ in range(40):
                if child.poll() is not None: raise RuntimeError('Game server exited')
                if reachable(URL+'/health'): break
                time.sleep(.5)
            else: raise RuntimeError('Game server did not start')
            if first: webbrowser.open(URL); first=False
            while child.poll() is None:
                if MARK.exists() and MARK.read_text().strip()==token:
                    restart=True
                    time.sleep(1)
                    break
                time.sleep(.5)
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=15)
            if MARK.exists(): MARK.unlink()
        if not restart: return
        update()
        dependencies()
if __name__=='__main__':
    try: main()
    except KeyboardInterrupt: pass
    except Exception as e:
        print('Launcher error:',e)
        sys.exit(1)
