"""Local update notices and opt-in, reversible model-file updates."""
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
import uuid

BASE = 'https://pub-44adc607e73e477294d6f612c2888cfa.r2.dev'
VERSION_URL = BASE+'/dl-2c9e41/version.json'
CHECK_INTERVAL = 6*3600
FAST_WEIGHTS = {'dinov3.gguf','ss_flow.gguf','ss_dec.gguf','shape_dec.gguf',
                'tex_dec.gguf','birefnet.gguf','shape_flow_512.gguf','tex_flow_512.gguf'}


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    with os.fdopen(os.open(temporary, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600),'w') as f:
        json.dump(value,f,indent=2)
        f.flush();os.fsync(f.fileno())
    os.replace(temporary,path)


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024**2),b''):h.update(block)
    return h.hexdigest()


def safe_relative(value):
    if not isinstance(value,str) or '\\' in value or ':' in value or '\x00' in value:
        raise ValueError('Invalid model-file path in the update feed.')
    p=PurePosixPath(value)
    if p.is_absolute() or not p.parts or any(x in ('..','.') for x in p.parts) or value!=str(p):
        raise ValueError('Invalid model-file path in the update feed.')
    return p


def validated_files(manifest, name):
    if manifest.get('kind')!='shapecast-pack' or manifest.get('schema')!=1 or manifest.get('name')!=name:
        raise ValueError('Unexpected model-pack manifest.')
    files={}
    for entry in manifest.get('files',[]):
        if not isinstance(entry,list) or len(entry)!=3:
            raise ValueError('Invalid model-file entry.')
        rel,size,sha=entry
        safe_relative(rel)
        if rel in files or type(size)!=int or size<0 or not re.fullmatch('[0-9a-f]{64}',str(sha)):
            raise ValueError('Invalid or duplicate model-file entry.')
        files[rel]=[size,sha]
    if not files:raise ValueError('The model-pack manifest is empty.')
    return files


def version_number(value):
    if not re.fullmatch(r'\d+(?:\.\d+){1,3}',str(value)):
        raise ValueError('Unexpected software version in the update feed.')
    return tuple(map(int,value.split('.')))


class OfficialTransport:
    def open(self,url,offset=0):
        parsed=urllib.parse.urlsplit(url)
        if parsed.scheme!='https' or parsed.netloc!=urllib.parse.urlsplit(BASE).netloc:
            raise ValueError('Update downloads must use the official HTTPS feed.')
        headers={'User-Agent':'Shapecast-Linux update-check'}
        if offset:headers['Range']=f'bytes={offset}-'
        response=urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=20)
        if urllib.parse.urlsplit(response.geturl()).netloc!=parsed.netloc:
            response.close();raise ValueError('Unexpected update download redirect.')
        return response

    def json(self,url):
        with self.open(url) as response:
            body=response.read(24*1024**2+1)
        if len(body)>24*1024**2:raise ValueError('The update manifest is too large.')
        return json.loads(body)


class UpdateManager:
    def __init__(self,root,current_version,licence_valid,transport=None):
        self.root=Path(root).resolve()
        self.directory=self.root/'profiles/native/updates'
        self.directory.mkdir(parents=True,exist_ok=True)
        self.path=self.directory/'state.json'
        self.current_version=current_version
        self.licence_valid=licence_valid
        self.transport=transport or OfficialTransport()
        self.lock=threading.RLock()
        self.cancel_event=threading.Event()
        self.stop_event=threading.Event()
        self.checking=False
        self.catalog={}
        self.sources=self._sources()
        self.state=json.loads(self.path.read_text()) if self.path.exists() else {
            'schema':1,'auto_check':True,'installed':{},'operation':None,'checked_at':None,
            'checked_timestamp':0,'check_errors':[],'catalog':{},'last_backup':None}
        self.catalog=self.state.get('catalog',{})
        # Cached release notices must reflect the running binary after an
        # upgrade or rollback, even before the next network check succeeds.
        software=self.catalog.get('software')
        if software:
            software['current']=self.current_version
            software['available']=version_number(software['version'])>version_number(self.current_version)
        operation=self.state.get('operation') or {}
        if operation.get('state')=='downloading':
            operation.update(state='paused',message='Download paused when Shapecast closed. Resume when ready.')
        self._recover()
        self._save()

    def _sources(self):
        packs=self.root/'profiles/native/data/packs'
        return {
            'models':{'title':'Quality and image models','name':'models','manifest':packs/'models/pack.json','destination':packs/'models'},
            'fast':{'title':'Fast models','name':'engine2','manifest':self.root/'profiles/native/data/packs/engine2/pack.json','destination':self.root/'models/fast'},
            'rig':{'title':'Rigging models','name':'rig','manifest':packs/'rig/pack.json','destination':packs/'rig'},
            'sharpener':{'title':'Sharpening model','name':'engine','manifest':packs/'engine/pack.json','destination':packs/'engine'},
        }

    def _save(self):
        with self.lock:write_json(self.path,self.state)

    def _selected(self,component,files):
        if component=='models':
            return {p:v for p,v in files.items() if p.startswith(('models/hf/hub/','models/hy3dgen/','models/u2net/')) and '/.cache/' not in p}
        if component=='fast':
            selected={p:v for p,v in files.items() if p in {'models/'+name for name in FAST_WEIGHTS}}
            if {Path(p).name for p in selected}!=FAST_WEIGHTS:
                raise ValueError('This Fast model pack needs a Linux engine compatibility update.')
            return selected
        if component=='rig':
            return {p:v for p,v in files.items() if p.startswith('hf-cache/') or p.endswith(('.ckpt','.safetensors','.pth')) and p.startswith('rig-pack/')}
        return {p:v for p,v in files.items() if p=='engine/hy3dpaint/ckpt/RealESRGAN_x4plus.pth'}

    def _destinations(self,component,relative,for_write=True):
        source=self.sources[component]
        relative=safe_relative(relative)
        if component=='fast':relative=PurePosixPath(relative.name)
        paths=[source['destination']/str(relative)]
        if component=='rig' and relative.parts[0]=='rig-pack' and (self.root/'engines/rig').is_dir():
            paths.append(self.root/'engines/rig'/Path(*relative.parts[1:]))
        if component=='sharpener' and (self.root/'engines/quality').is_dir():
            paths.append(self.root/'engines/quality/hy3dpaint/ckpt/RealESRGAN_x4plus.pth')
        for path in paths:
            if for_write and (not path.resolve().is_relative_to(self.root) or path.is_symlink()):
                raise ValueError('A model update target leaves the local runtime or is a symbolic link.')
        return paths

    def _baseline(self,component):
        source=self.sources[component]
        if not source['manifest'].exists():return None
        manifest=json.loads(source['manifest'].read_text())
        files=self._selected(component,validated_files(manifest,source['name']))
        files.update(self.state.get('installed',{}).get(component,{}))
        return files

    def _inspect_models(self,component):
        source=self.sources[component]
        baseline=self._baseline(component)
        if baseline is None:return None
        url=BASE+'/v1/'+source['name']+'/pack.json'
        manifest=self.transport.json(url)
        selected=self._selected(component,validated_files(manifest,source['name']))
        changed=[];read_only=False
        for relative,(size,sha) in selected.items():
            destinations=self._destinations(component,relative,for_write=False)
            read_only=read_only or any(not p.resolve().is_relative_to(self.root) or p.is_symlink() for p in destinations)
            if baseline.get(relative)!=[size,sha] or any(not p.is_file() for p in destinations):
                changed.append({'relative':relative,'size':size,'sha256':sha,'url':BASE+'/v1/'+source['name']+'/'+urllib.parse.quote(relative,safe='/')})
        code_change=any(f['relative'].endswith(('.py','.pyc','.so','.pyd','.exe')) for f in changed)
        return {'id':component,'title':source['title'],'kind':'models','version':str(manifest.get('version','')),
                'read_only':read_only,'built':manifest.get('built'),'files':changed,'available':bool(changed),'compatibility_required':code_change,
                'download_bytes':sum({f['sha256']:f['size'] for f in changed}.values()),'fingerprint':hashlib.sha256(json.dumps(changed,sort_keys=True).encode()).hexdigest()}

    def _inspect_software(self):
        release=self.transport.json(VERSION_URL)
        version=str(release.get('version',''))
        newer=version_number(version)>version_number(self.current_version)
        size=release.get('size_bytes');sha=release.get('sha256')
        if type(size)!=int or size<1 or not re.fullmatch('[0-9a-f]{64}',str(sha)):
            raise ValueError('The software update has no valid size or checksum.')
        entry={'relative':f'Shapecast-Setup-{version}.exe','size':size,'sha256':sha,
               'url':BASE+f'/dl-2c9e41/archive/Shapecast-Setup-{version}.exe'}
        return {'id':'software','title':'Shapecast application','kind':'software','version':version,
                'current':self.current_version,'released':release.get('released'),'available':newer,
                'compatibility_required':True,'download_bytes':size,'files':[entry],
                'fingerprint':hashlib.sha256(json.dumps(entry,sort_keys=True).encode()).hexdigest()}

    def check(self):
        with self.lock:
            if self.checking:return
            self.checking=True
        errors=[];found={}
        try:
            with ThreadPoolExecutor(max_workers=5) as pool:
                tasks={'software':pool.submit(self._inspect_software)}
                tasks.update({c:pool.submit(self._inspect_models,c) for c in self.sources})
                for component,future in tasks.items():
                    try:
                        item=future.result()
                        if item is not None:found[component]=item
                    except Exception:
                        errors.append(component)
            with self.lock:
                self.catalog.update(found)
                self.state.update(catalog=self.catalog,checked_at=now(),checked_timestamp=time.time(),check_errors=errors)
                self._save()
        finally:
            with self.lock:self.checking=False

    def request_check(self):
        threading.Thread(target=self.check,daemon=True).start()

    def start(self):
        def loop():
            first=True
            while not self.stop_event.is_set():
                if self.state.get('auto_check',True) and (first or time.time()-self.state.get('checked_timestamp',0)>CHECK_INTERVAL):
                    self.check()
                first=False
                self.stop_event.wait(60)
        threading.Thread(target=loop,daemon=True).start()

    def status(self):
        with self.lock:
            items=[]
            for key,entry in self.catalog.items():
                item={k:v for k,v in entry.items() if k!='files'}
                item['changed_files']=len(entry.get('files',[])) if entry.get('available') else 0
                item['failed_check']=key in self.state.get('check_errors',[])
                items.append(item)
            fingerprint=hashlib.sha256(json.dumps([(x['id'],x['fingerprint']) for x in items if x['available']],sort_keys=True).encode()).hexdigest()
            return {'checking':self.checking,'checked_at':self.state.get('checked_at'),
                    'auto_check':self.state.get('auto_check',True),'check_errors':self.state.get('check_errors',[]),
                    'components':items,'available':any(x['available'] for x in items),'fingerprint':fingerprint,
                    'operation':copy.deepcopy(self.state.get('operation')),'rollback_available':bool(self.state.get('last_backup')),
                    'linux_launcher':'Helper 0.2.0. Update this repository with git pull --ff-only; automatic helper updates are not configured.'}

    def _progress(self,**values):
        with self.lock:
            self.state['operation'].update(values)
            self._save()

    def download(self,component):
        with self.lock:
            operation=self.state.get('operation') or {}
            if operation.get('state') in ('downloading','applying'):raise ValueError('An update is already running.')
            plan=copy.deepcopy(self.catalog.get(component))
            if not plan or not plan['available']:raise ValueError('Check for updates before downloading.')
            if component!='software' and not self.licence_valid():raise ValueError('A valid Shapecast licence is required to download model updates.')
            staging=self.directory/'staging'/plan['fingerprint']
            staging.mkdir(parents=True,exist_ok=True)
            if shutil.disk_usage(staging).free<plan['download_bytes']*1.05+64*1024**2:
                raise ValueError('There is not enough free disk space for this update.')
            write_json(staging/'plan.json',plan)
            self.cancel_event.clear()
            self.state['operation']={'component':component,'fingerprint':plan['fingerprint'],'state':'downloading',
                                     'done_bytes':0,'total_bytes':plan['download_bytes'],'message':'Downloading and verifying the update…'}
            self._save()
        threading.Thread(target=self._download_worker,args=(plan,staging),daemon=True).start()

    def _download_worker(self,plan,staging):
        completed=0;verified={}
        try:
            for entry in plan['files']:
                relative=str(safe_relative(entry['relative']));target=staging/'files'/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                if entry['sha256'] in verified:
                    target.unlink(missing_ok=True);os.link(verified[entry['sha256']],target)
                    continue
                if target.is_file() and target.stat().st_size==entry['size'] and digest(target)==entry['sha256']:
                    verified[entry['sha256']]=target;completed+=entry['size'];continue
                partial=target.with_name(target.name+'.part')
                offset=partial.stat().st_size if partial.exists() else 0
                if offset>entry['size']:partial.unlink();offset=0
                if offset<entry['size']:
                    with self.transport.open(entry['url'],offset) as response:
                        if offset and getattr(response,'status',200)!=206:offset=0
                        if offset and not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'):
                            raise ValueError('The server returned an invalid resumed download.')
                        last=0
                        with partial.open('ab' if offset else 'wb') as destination:
                            while block:=response.read(1024**2):
                                if self.cancel_event.is_set():raise InterruptedError()
                                offset+=len(block)
                                if offset>entry['size']:raise ValueError('The update exceeds its declared size.')
                                destination.write(block)
                                if time.monotonic()-last>1:
                                    self._progress(done_bytes=completed+offset,message='Downloading '+Path(relative).name+'…');last=time.monotonic()
                            destination.flush();os.fsync(destination.fileno())
                self._progress(message='Verifying '+Path(relative).name+'…')
                if partial.stat().st_size!=entry['size'] or digest(partial)!=entry['sha256']:
                    partial.unlink(missing_ok=True);raise ValueError('The update failed checksum verification. Download it again.')
                os.replace(partial,target);verified[entry['sha256']]=target;completed+=entry['size']
            self._progress(state='ready',done_bytes=completed,message=('Installer downloaded and verified. A Linux compatibility review is required before installation.' if plan['kind']=='software' else 'Model update downloaded and verified. A private model copy is required before installation.' if plan.get('read_only') else 'Model update downloaded and verified. Apply when your casts have finished.'))
        except InterruptedError:
            self._progress(state='paused',message='Download paused. Download again to resume.')
        except Exception as exc:
            message=str(exc) if isinstance(exc,ValueError) else 'Could not finish the download. Check your connection and try again.'
            self._progress(state='error',message=message)

    def _ready_plan(self):
        operation=self.state.get('operation') or {}
        if operation.get('state')!='ready':raise ValueError('Download and verify the model update first.')
        staging=self.directory/'staging'/operation['fingerprint']
        plan=json.loads((staging/'plan.json').read_text())
        if plan['kind']!='models':raise ValueError('Software installers require a Linux compatibility review before installation.')
        if plan.get('read_only'):raise ValueError('These models are shared read-only. Use a private model copy before applying updates; the working installation will not be changed.')
        if plan.get('compatibility_required'):raise ValueError('This update contains model code changes and needs Linux compatibility review.')
        return plan,staging

    def apply(self):
        with self.lock:
            if not self.licence_valid():raise ValueError('A valid Shapecast licence is required.')
            plan,staging=self._ready_plan()
            self._progress(state='applying',message='Verifying the downloaded models before applying…')
        try:
            self._apply_files(plan,staging)
        except Exception:
            if self.state['operation'].get('state')=='applying':
                self._progress(state='error',message='The staged update could not be verified. Existing models were kept.')
            raise

    def _apply_files(self,plan,staging):
        # Revalidate before any model file is changed; staged files may have
        # been interrupted, damaged, or changed since the download finished.
        for entry in plan['files']:
            path=staging/'files'/str(safe_relative(entry['relative']))
            if path.stat().st_size!=entry['size'] or digest(path)!=entry['sha256']:
                raise ValueError('A staged model failed verification. Download it again.')
        backup=self.directory/'backups'/uuid.uuid4().hex;backup.mkdir(parents=True)
        journal={'state':'applying','installed_before':copy.deepcopy(self.state['installed']),
                 'last_backup_before':self.state.get('last_backup'),'files':[]}
        for entry in plan['files']:
            for destination in self._destinations(plan['id'],entry['relative']):
                record={'destination':str(destination.relative_to(self.root)),'existed':destination.is_file()}
                old=backup/'files'/record['destination'];old.parent.mkdir(parents=True,exist_ok=True)
                if record['existed']:os.link(destination,old)
                journal['files'].append(record)
        write_json(backup/'journal.json',journal)
        self._progress(state='applying',message='Applying the verified model update…')
        try:
            for entry in plan['files']:
                path=staging/'files'/entry['relative']
                for destination in self._destinations(plan['id'],entry['relative']):
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    temporary=destination.with_name(destination.name+'.linux-update')
                    temporary.unlink(missing_ok=True);os.link(path,temporary);os.replace(temporary,destination)
            installed=self.state['installed'].setdefault(plan['id'],{})
            installed.update({e['relative']:[e['size'],e['sha256']] for e in plan['files']})
            self.state['last_backup']=backup.name
            self.state['operation'].update(state='done',message='Model update installed. Your next cast will use it.',backup=backup.name)
            self.catalog[plan['id']].update(available=False,files=[],download_bytes=0)
            self.state['catalog']=self.catalog;self._save()
            journal['state']='committed';write_json(backup/'journal.json',journal)
        except Exception:
            self._restore(backup,journal)
            self.catalog[plan['id']]=plan;self.state['catalog']=self.catalog
            self._progress(state='error',message='The update could not be applied. The previous models were restored.')
            raise

    def _restore(self,backup,journal):
        for entry in journal['files']:
            relative=str(safe_relative(entry['destination']))
            destination=self.root/relative
            if not destination.resolve().is_relative_to(self.root):raise ValueError('Invalid rollback target.')
            if entry['existed']:
                temporary=destination.with_name(destination.name+'.linux-restore')
                temporary.unlink(missing_ok=True);os.link(backup/'files'/relative,temporary);os.replace(temporary,destination)
            else:destination.unlink(missing_ok=True)
        self.state['installed']=journal['installed_before']
        self.state['last_backup']=journal.get('last_backup_before')
        journal['state']='restored';write_json(backup/'journal.json',journal)
        self._save()

    def rollback(self):
        with self.lock:
            name=self.state.get('last_backup')
            if not name:raise ValueError('There is no model update to undo.')
            if (self.state.get('operation') or {}).get('state') in ('downloading','applying'):raise ValueError('Finish or pause the current update first.')
            backup=self.directory/'backups'/name;journal=json.loads((backup/'journal.json').read_text())
            journal['state']='restoring';write_json(backup/'journal.json',journal)
            self._restore(backup,journal)
            self.state['operation']={'state':'done','message':'The previous model files were restored.'}
            self.state['checked_timestamp']=0;self._save()
        self.request_check()

    def _recover(self):
        for path in sorted((self.directory/'backups').glob('*/journal.json')):
            journal=json.loads(path.read_text())
            if journal['state'] not in ('applying','restoring'):continue
            operation=self.state.get('operation') or {}
            if journal['state']=='applying' and operation.get('state')=='done' and operation.get('backup')==path.parent.name:
                journal['state']='committed';write_json(path,journal)
            else:
                self._restore(path.parent,journal)
                self.state['operation']={'state':'error','message':'An interrupted update was rolled back. Your previous models are restored.'}

    def software_file(self):
        operation=self.state.get('operation') or {}
        if operation.get('state')!='ready' or operation.get('component')!='software':
            raise ValueError('Download the software update first.')
        staging=self.directory/'staging'/operation['fingerprint']
        plan=json.loads((staging/'plan.json').read_text());entry=plan['files'][0]
        return staging/'files'/str(safe_relative(entry['relative']))


def attach_update_lifespan(app,manager):
    """Compose with the vendor's lifespan; on_event hooks are not run by it."""
    from contextlib import asynccontextmanager
    original=app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        async with original(application) as state:
            manager.start()
            try:yield state
            finally:
                manager.stop_event.set()
                manager.cancel_event.set()
    app.router.lifespan_context=lifespan


def install_update_routes(app,root,settings,current_version):
    import asyncio
    from fastapi import HTTPException,Request
    from fastapi.responses import FileResponse,JSONResponse
    from shapecast_core import licensing
    manager=UpdateManager(root,current_version,lambda:licensing.load_status(settings).ok)
    app.state.linux_updates=manager
    gate={'applying':False,'mutations':0}

    @app.middleware('http')
    async def update_gate(request,call_next):
        mutation=request.method in ('POST','PUT','PATCH','DELETE') and not request.url.path.startswith('/v1/linux-updates')
        if mutation and gate['applying']:
            return JSONResponse({'detail':'A model update is being applied. Try again when it finishes.'},status_code=409)
        if mutation:gate['mutations']+=1
        try:return await call_next(request)
        finally:
            if mutation:gate['mutations']-=1

    def busy():
        database=Path(settings.data_dir)/'library.db'
        if not database.is_file():return False
        with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as c:
            return bool(c.execute("SELECT 1 FROM jobs WHERE status NOT IN ('complete','failed','cancelled') LIMIT 1").fetchone())

    @app.get('/v1/linux-updates')
    async def update_status():
        return {**manager.status(),'busy':busy() or bool(gate['mutations'])}

    @app.post('/v1/linux-updates/check')
    async def update_check():
        manager.request_check();return manager.status()

    @app.post('/v1/linux-updates/download')
    async def update_download(request:Request):
        body=await request.json()
        try:manager.download(body.get('component'))
        except ValueError as exc:raise HTTPException(409,str(exc))
        return manager.status()

    @app.post('/v1/linux-updates/pause')
    async def update_pause():
        manager.cancel_event.set();return manager.status()

    @app.put('/v1/linux-updates/preferences')
    async def update_preferences(request:Request):
        body=await request.json()
        if type(body.get('auto_check'))!=bool:raise HTTPException(400,'Choose whether to check automatically.')
        manager.state['auto_check']=body['auto_check'];manager._save();return manager.status()

    async def apply_or_restore(action):
        if gate['applying'] or gate['mutations'] or busy():raise HTTPException(409,'Finish or cancel current casts before changing model files.')
        gate['applying']=True
        try:
            await asyncio.to_thread(action)
            return manager.status()
        except ValueError as exc:raise HTTPException(409,str(exc))
        finally:gate['applying']=False

    @app.post('/v1/linux-updates/apply')
    async def update_apply():return await apply_or_restore(manager.apply)

    @app.post('/v1/linux-updates/rollback')
    async def update_rollback():return await apply_or_restore(manager.rollback)

    @app.get('/v1/linux-updates/installer')
    async def downloaded_installer():
        try:path=manager.software_file()
        except ValueError as exc:raise HTTPException(404,str(exc))
        return FileResponse(path,filename=path.name,media_type='application/octet-stream')

    attach_update_lifespan(app,manager)
    return manager
