"""Licence-gated, verified downloads/imports of the vendor's native-use pack files."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import urllib.parse
import urllib.request

from .common import private_json, profile, read_install, relative_path, sha256
from .updates import BASE, FAST_WEIGHTS, validated_files


def selected_files(name, manifest):
    files=validated_files(manifest,name)
    if name=='engine2':
        chosen={p:v for p,v in files.items() if p in {'models/'+f for f in FAST_WEIGHTS}}
        if len(chosen)!=len(FAST_WEIGHTS):raise ValueError('The vendor Fast pack layout changed; update the helper.')
        return chosen
    if name=='models':return {p:v for p,v in files.items() if p.startswith('models/') and '/.cache/' not in p}
    if name=='rig':
        return {p:v for p,v in files.items() if p.startswith(('rig-pack/','hf-cache/')) and not p.startswith(('rig-pack/logs/','rig-pack/lightning_logs/','rig-pack/tmp_shapecast/')) and not p.endswith(('.exe','.dll','.pyd','.pyc','.so'))}
    if name=='engine':
        return {p:v for p,v in files.items() if p.startswith('engine/') and not p.endswith(('.exe','.dll','.pyd','.pyc','.so')) and '/__pycache__/' not in p and not p.endswith(('/temp.glb','/mr_combined.png'))}
    raise ValueError('Unknown model pack.')


def require_licence(root):
    from .identity import configure_machine_identity
    configure_machine_identity(root)
    from shapecast_core.config import Settings
    from shapecast_core import licensing
    settings=Settings.load()
    if settings.data_dir.resolve()!=(profile(root,'native')/'data').resolve():raise ValueError('Use the native profile for model setup.')
    if not licensing.load_status(settings).ok:
        raise ValueError('Activate your own vendor-issued licence in Linux setup before downloading or importing model packs.')


def fetch_json(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'shapecast-desktop'}),timeout=60) as response:
        data=response.read(24*1024**2+1)
    if len(data)>24*1024**2:raise ValueError('Model manifest exceeds the supported size.')
    return json.loads(data)


def transfer(url, target, size, digest):
    """Resume partial data, then verify before replacing any installed file."""
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    if target.is_file() and target.stat().st_size==size and sha256(target)==digest:return
    partial=target.with_name(target.name+'.part')
    for attempt in range(5):
        try:
            offset=partial.stat().st_size if partial.exists() else 0
            if offset>size:partial.unlink();offset=0
            if offset<size:
                headers={'User-Agent':'shapecast-desktop'}
                if offset:headers['Range']=f'bytes={offset}-'
                with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=60) as response:
                    if offset and response.status!=206:offset=0
                    if offset and not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'):
                        raise ValueError('Unexpected model resume response.')
                    with partial.open('ab' if offset else 'wb') as stream:
                        while block:=response.read(1024**2):
                            offset+=len(block)
                            if offset>size:raise ValueError('Model exceeds its declared size.')
                            stream.write(block)
            if partial.stat().st_size!=size or sha256(partial)!=digest:
                partial.unlink(missing_ok=True);raise ValueError('Model size or SHA256 mismatch.')
            os.replace(partial,target);return
        except Exception:
            if attempt==4:raise
            time.sleep(min(attempt+1,5))


def destination(root,name,relative):
    relative=relative_path(relative)
    if name=='engine2':target=root/'models/fast'/relative.name
    else:target=profile(root,'native')/'data/packs'/name/relative
    if not target.resolve().is_relative_to(root.resolve()) or target.is_symlink():raise ValueError('Model target leaves this installation.')
    return target


def install_models(args):
    root,_=read_install(args.install_root);require_licence(root)
    from .session_control import existing_url,matching_servers
    if matching_servers(root,'native') or existing_url(profile(root,'native')):
        raise ValueError('Close the native session before importing or downloading packs; use its update panel for model updates during normal operation.')
    names=args.packs.split(',')
    if any(n not in ('models','engine','engine2','rig') for n in names):raise ValueError('Packs: models,engine,engine2,rig (comma-separated).')
    store=args.source.expanduser().resolve() if args.source else None
    for name in names:
        source=store/name if store and (store/name/'pack.json').is_file() else store
        manifest=json.loads((source/'pack.json').read_text()) if source else fetch_json(BASE+'/v1/'+name+'/pack.json')
        chosen=selected_files(name,manifest)
        print(f'{name}: checking {len(chosen)} native-use files…',flush=True)
        # Group equal blobs/snapshots so HF cache duplicates need one transfer.
        groups={}
        for relative,(size,digest) in chosen.items():groups.setdefault((size,digest),[]).append(relative)
        needed=sum(size for (size,sha),rels in groups.items() if not any(destination(root,name,p).is_file() and destination(root,name,p).stat().st_size==size and sha256(destination(root,name,p))==sha for p in rels))
        if shutil.disk_usage(root).free<needed*1.05:raise ValueError(f'Not enough free space for {name}: about {needed/2**30:.1f} GiB additional data required.')
        def one(item):
            (size,digest),paths=item
            first=next((destination(root,name,p) for p in paths if destination(root,name,p).is_file() and destination(root,name,p).stat().st_size==size and sha256(destination(root,name,p))==digest),None)
            if first is None:
                first=destination(root,name,paths[0])
                if source:
                    supplied=source/relative_path(paths[0])
                    if not supplied.is_file() or supplied.stat().st_size!=size or sha256(supplied)!=digest:raise ValueError('Imported model failed verification: '+paths[0])
                    first.parent.mkdir(parents=True,exist_ok=True);temporary=first.with_name(first.name+'.part');shutil.copyfile(supplied,temporary);os.replace(temporary,first)
                else:transfer(BASE+'/v1/'+name+'/'+urllib.parse.quote(paths[0],safe='/'),first,size,digest)
            for relative in paths:
                target=destination(root,name,relative)
                if target==first or target.is_file() and target.stat().st_size==size and sha256(target)==digest:continue
                target.parent.mkdir(parents=True,exist_ok=True);temporary=target.with_name(target.name+'.part');temporary.unlink(missing_ok=True)
                try:os.link(first,temporary)
                except OSError:shutil.copyfile(first,temporary)
                os.replace(temporary,target)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures=[pool.submit(one,item) for item in groups.items()]
            for index,f in enumerate(concurrent.futures.as_completed(futures),1):
                f.result()
                if index%20==0 or index==len(futures):print(f'{name}: {index}/{len(futures)} unique files verified',flush=True)
        pack=profile(root,'native')/'data/packs'/name
        private_json(pack/'pack.json',manifest)
        private_json(pack/'linux-selection.json',{'schema':1,'selection_only':True,'files':list(chosen),'version':manifest.get('version')})
    print('Selected native files verified. Windows executables and Python environments were not installed.',flush=True)


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--install-root',type=Path,required=True)
    parser.add_argument('--packs',default='models,engine')
    parser.add_argument('--source',type=Path)
    try:install_models(parser.parse_args())
    except (ValueError,OSError) as error:parser.exit(1,str(error)+'\n')

if __name__=='__main__':main()
