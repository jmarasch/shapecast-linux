"""Build and configure independent native inference environments."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import zipfile

from .common import LOCK, REPO, core_environment, private_json, profile, read_install, relative_path, sha256
from .installer import component, download, extract_tar, run

RUNTIME_NAMES=('quality','image','rig','tools','fast','topology')


def patch_engine(engine):
    """Apply small guarded adaptations to a private engine copy, never vendor core."""
    path=engine/'hy3dpaint/utils/multiview_utils.py'
    source=path.read_text()
    if '# Linux native initial placement' not in source:
        old='        self.pipeline = pipeline.to(self.device)'
        if old not in source:raise ValueError('Quality loader changed; the helper needs a compatibility update.')
        source=source.replace(old,'''        # Linux native initial placement: install offload before GPU allocation.
        load_device = self.device
        if self.device == "cuda" and torch.cuda.mem_get_info()[0] < 13 * 1024**3:
            load_device = "cpu"
        self.pipeline = pipeline.to(load_device)''',1)
        source=source.replace('self.dino_v2 = self.dino_v2.to(self.device)','self.dino_v2 = self.dino_v2.to(load_device)')
        old='        kwargs = dict(generator=torch.Generator(device=self.pipeline.device).manual_seed(0))'
        if old not in source:raise ValueError('Quality generator changed; the helper needs an update.')
        source=source.replace(old,'''        generator_device = self.pipeline.device
        if generator_device.type == "meta":
            generator_device = torch.device("cpu")
        kwargs = dict(generator=torch.Generator(device=generator_device).manual_seed(0))''',1)
        path.write_text(source)
    path=engine/'hy3dpaint/hunyuanpaintpbr/pipeline.py';source=path.read_text()
    if 'images_vae.to(device=self.vae.device, dtype=self.unet.dtype)' in source:
        source=source.replace('images_vae.to(device=self.vae.device, dtype=self.unet.dtype)','images_vae.to(device=self._execution_device, dtype=self.unet.dtype)');path.write_text(source)
    elif 'images_vae.to(device=self._execution_device, dtype=self.unet.dtype)' not in source:
        raise ValueError('Quality VAE transfer changed; review is needed.')


def prepare_engine(root):
    source=profile(root,'native')/'data/packs/engine/engine';engine=root/'engines/quality'
    if not (source/'hy3dpaint/custom_rasterizer/setup.py').is_file():raise ValueError('Download/import the engine pack first: models --packs engine,models')
    stamp=root/'engines/quality-source.json'
    manifest=source.parent/'pack.json'
    fingerprint=sha256(manifest)
    previous=json.loads(stamp.read_text()) if stamp.is_file() else {}
    if engine.exists() and previous.get('manifest_sha256')!=fingerprint:
        raise ValueError('The private engine copy differs from its recorded source pack. Keep a backup, remove engines/quality and its runtime-ready marker, then rebuild Quality. Existing files were preserved.')
    if not engine.exists():
        engine.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(source,engine,ignore=shutil.ignore_patterns('__pycache__','*.pyd','*.dll','*.so','temp.glb','mr_combined.png'))
        private_json(stamp,{'schema':1,'manifest_sha256':fingerprint})
    patch_engine(engine)
    return engine


def install_python_runtime(root,name,cache,wheelhouse=None):
    venv=root/'runtimes'/name
    venv.parent.mkdir(parents=True,exist_ok=True)
    if not (venv/'bin/python').is_file():run([root/'venv/bin/python','-m','venv',venv],timeout=60)
    cmd=[venv/'bin/python','-m','pip','install','--disable-pip-version-check','--cache-dir',cache/'pip',
         '--no-deps','-r',REPO/'requirements'/f'{name}.txt']
    if wheelhouse:cmd+=['--no-index','--find-links',wheelhouse]
    else:cmd+=['--extra-index-url','https://download.pytorch.org/whl/cu128','--find-links','https://data.pyg.org/whl/torch-2.11.0+cu128.html']
    print('Installing pinned '+name+' dependencies (this can take several minutes)…',flush=True)
    run(cmd,timeout=3600,live=True)
    return venv


def cuda_compiler(root,cache,python):
    cuda=root/'build/cuda'
    if (cuda/'bin/nvcc').is_file() and (cuda/'lib64/libcudart.so').is_file():return cuda
    for spec in LOCK['cuda_compiler']:
        archive=download({'url':spec['source'],'sha256':spec['sha256']},cache)
        with zipfile.ZipFile(archive) as z:
            members=[n for n in z.namelist() if n.startswith('pkg-') and n.endswith('.tar.zst')]
            if len(members)!=1:raise ValueError('Unsupported CUDA compiler package.')
            with tempfile.TemporaryDirectory(dir=root) as tmp:
                compressed=Path(tmp)/'package.tar.zst';compressed.write_bytes(z.read(members[0]))
                tar=Path(tmp)/'package.tar'
                run([python,'-c','import sys,zstandard,shutil; z=zstandard.ZstdDecompressor(); f=open(sys.argv[1],"rb"); o=open(sys.argv[2],"wb"); shutil.copyfileobj(z.stream_reader(f),o); o.close(); f.close()',compressed,tar],timeout=180)
                extract_tar(tar,cuda)
    for name,dest in [('include','targets/x86_64-linux/include'),('lib64','targets/x86_64-linux/lib')]:
        if not (cuda/name).exists():(cuda/name).symlink_to(dest,target_is_directory=True)
    return cuda


def compiler_environment(root,venv,args):
    cxx=args.cxx or next((shutil.which(name) for name in ('g++-13','g++-14','g++') if shutil.which(name)),None)
    if not cxx:raise ValueError('Install a C++ compiler (g++-13 recommended) before building Quality.')
    version=run([cxx,'-dumpfullversion'],timeout=15).strip()
    if int(version.split('.')[0])>14:raise ValueError('CUDA 12.8 needs GCC 14 or older. Install g++-13 and pass --cxx /usr/bin/g++-13.')
    cc=str(cxx).replace('g++','gcc')
    cache=args.cache_dir.expanduser().resolve() if args.cache_dir else root/'cache'
    cuda=args.cuda_home.expanduser().resolve() if args.cuda_home else cuda_compiler(root,cache,venv/'bin/python')
    if not args.cuda_home:
        system_math=run([cxx,'-E','-x','c++','-'],input='#include <cmath>\n',timeout=30)
        patch_cuda_headers(cuda,system_math)
    arch=run([venv/'bin/python','-c','import torch; assert torch.cuda.is_available(), "NVIDIA CUDA is unavailable"; a,b=torch.cuda.get_device_capability(); print(f"{a}.{b}")'],timeout=30).strip().splitlines()[-1]
    env=core_environment(root,'native')
    env.update(CC=str(cc),CXX=str(cxx),CUDA_HOME=str(cuda),MAX_JOBS=str(args.jobs),TORCH_CUDA_ARCH_LIST=arch)
    headers=venv/'lib/python3.11/site-packages/nvidia'
    env['CPATH']=os.pathsep.join(str(p) for p in headers.glob('*/include'))
    return env


def patch_cuda_headers(cuda,system_math):
    """Match new glibc declarations in our private CUDA 12.8 compiler only."""
    names=('rsqrt','rsqrtf','sinpi','sinpif','cospi','cospif')
    needed=[name for name in names if re.search(r'\b'+name+r'\s*\([^;{}]*\)\s*noexcept\s*\(\s*true\s*\)',system_math)]
    if not needed:return
    path=cuda/'include/crt/math_functions.h';source=path.read_text();updated=source
    for name in needed:
        pattern=r'(extern __DEVICE_FUNCTIONS_DECL__ __device_builtin__ (?:double|float)\s+'+name+r'\((?:double|float) x\))(?: noexcept\(true\))?;'
        updated,count=re.subn(pattern,r'\1 noexcept(true);',updated)
        if count!=1:raise ValueError('Private CUDA math declarations changed; compatibility review is needed.')
    if updated!=source:
        backup=path.with_suffix('.h.original')
        if not backup.exists():backup.write_text(source)
        path.write_text(updated)
        private_json(cuda/'linux-header-compatibility.json',{'schema':1,'declarations':needed,'reason':'Match host glibc noexcept declarations'})


def build_quality(root,venv,args):
    engine=prepare_engine(root);env=compiler_environment(root,venv,args)
    print('Building native CUDA rasterizer for this GPU…',flush=True)
    run([venv/'bin/python','-m','pip','install','--disable-pip-version-check','--no-build-isolation','--no-deps',engine/'hy3dpaint/custom_rasterizer'],env=env,timeout=1800,live=True)
    renderer=engine/'hy3dpaint/DifferentiableRenderer'
    build=root/'build/inpaint';build.mkdir(parents=True,exist_ok=True)
    script=build/'setup.py'
    script.write_text('from setuptools import setup\nfrom pybind11.setup_helpers import Pybind11Extension,build_ext\n'+
        'setup(name="shapecast-linux-inpaint",version="0.1",ext_modules=[Pybind11Extension("mesh_inpaint_processor",['+repr(str(renderer/'mesh_inpaint_processor.cpp'))+'],cxx_std=17)],cmdclass={"build_ext":build_ext})\n')
    run([venv/'bin/python',script,'build_ext','--build-lib',renderer],env=env,cwd=build,timeout=600,live=True)
    # Keep Python startup flags from the commercial core; -E ignores PYTHONPATH.
    wrapper=(REPO/'scripts/gpu-python.sh').read_text().replace('@PYTHON@',shlex.quote(str(venv/'bin/python'))).replace('@HOST@',shlex.quote(str(REPO/'src/shapecast_linux/gpu_host.py')))
    entry=root/'engines/quality-python';entry.write_text(wrapper);entry.chmod(0o700)


def build_rig(root,venv):
    source=profile(root,'native')/'data/packs/rig/rig-pack';dest=root/'engines/rig'
    if not (source/'run.py').is_file():raise ValueError('Download/import the rig pack before installing the rig runtime.')
    if not dest.exists():dest.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(source,dest)
    cache=venv/'hf-cache'
    if not cache.exists():cache.symlink_to(source.parent/'hf-cache',target_is_directory=True)
    site=venv/'lib/python3.11/site-packages/sitecustomize.py'
    site.write_text('import os,sys\nfrom pathlib import Path\n'+
        'if Path(sys.argv[0]).name == "run.py" and os.environ.get("SHAPECAST_RIG_DENSE_ATTENTION") != "1":\n'+
        '    sys.path.insert(0,'+repr(str(REPO/'src'))+')\n    from shapecast_linux.rig_compat import install\n    install()\n')


def install_topology(root,cache):
    target=root/'components/instant-meshes/Instant Meshes'
    if not target.is_file():
        archive=download(LOCK['instant_meshes'],cache)
        with zipfile.ZipFile(archive) as z:
            matches=[n for n in z.namelist() if Path(n).name=='Instant Meshes']
            if len(matches)!=1:raise ValueError('Unexpected official Instant Meshes archive.')
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(matches[0]));target.chmod(0o700)
    result=subprocess.run([target,'--help'],text=True,capture_output=True,timeout=30)
    help_text=result.stdout+result.stderr
    # The pinned official Linux build returns 255 for its help display.
    if result.returncode not in (0,255) or '--faces' not in help_text or 'Instant Meshes' not in help_text:
        raise ValueError('Native Instant Meshes did not start: '+help_text[-1500:])
    return target


def configure(root):
    """Restore native paths after pack imports while preserving the chosen engine."""
    path=profile(root,'native')/'data/settings.json';data=json.loads(path.read_text())
    def ready(name):return (root/'runtimes'/name/'linux-runtime-ready.json').is_file()
    changes={'fake_stages':False,'allow_preview_generation':False}
    packs=profile(root,'native')/'data/packs'
    if (packs/'models/models').is_dir():changes['models_dir']=str(packs/'models/models')
    if ready('image'):changes['image_host_exe']=str(root/'runtimes/image/bin/python')
    if ready('rig'):changes.update(rig_host_exe=str(root/'runtimes/rig/bin/python'),rig_pack_root=str(root/'engines/rig'))
    if (root/'components/cuda/trellis-cli').is_file():changes.update(engine2_exe=str(root/'components/cuda/trellis-cli'),engine2_models_dir=str(root/'models/fast'))
    quality=ready('quality') and (root/'engines/quality-python').is_file()
    selected=data.get('mesh_engine','engine1' if quality else 'engine2')
    if quality and selected=='engine2' and not (root/'components/cuda/trellis-cli').is_file():selected='engine1'
    changes['mesh_engine']=selected
    # Keep the capable host when Fast is selected too: switching the mesh engine
    # in the original UI must not lose Quality's memory/device adaptations.
    if quality:changes.update(gpu_host_exe=str(root/'engines/quality-python'),engine_root=str(root/'engines/quality'))
    elif ready('tools'):changes.update(gpu_host_exe=str(root/'runtimes/tools/bin/python'),engine_root=str(root/'engines/quality'))
    data.update(changes)
    # Windows runtime paths must never replace the native hosts silently.
    for key in ['gpu_host_exe','image_host_exe','rig_host_exe','engine2_exe']:
        if str(data.get(key,'')).lower().endswith('.exe'):data[key]=None
    if json.loads(path.read_text())!=data:private_json(path,data)
    return {'quality_available':quality,'rigging_available':ready('rig'),'sharpening_available':ready('quality') or ready('tools'),'selected_mesh_engine':data['mesh_engine']}


def install_runtimes(args):
    root,config=read_install(args.install_root)
    from .session_control import existing_url,matching_servers
    if matching_servers(root,'native') or existing_url(profile(root,'native')):raise ValueError('Close the native session before changing its inference runtimes.')
    names=RUNTIME_NAMES if args.components=='all' else tuple(args.components.split(','))
    if any(n not in RUNTIME_NAMES for n in names):raise ValueError('Unknown runtime component.')
    cache=args.cache_dir.expanduser().resolve() if args.cache_dir else root/'cache'
    first_quality=not (root/'runtimes/quality/linux-runtime-ready.json').is_file()
    for name in names:
        print('Preparing '+name+'…',flush=True)
        if name=='fast':
            executable=root/'components/cuda/trellis-cli'
            if not executable.is_file():executable=component('cuda',root,cache)
            config['cuda']=str(executable);private_json(root/'install.json',config);continue
        if name=='topology':install_topology(root,cache);continue
        if name in ('quality','tools'):prepare_engine(root)
        if name=='rig' and not (profile(root,'native')/'data/packs/rig/rig-pack/run.py').is_file():raise ValueError('Download/import the rig pack first.')
        venv=root/'runtimes'/name
        marker=venv/'linux-runtime-ready.json'
        requirements_hash=sha256(REPO/'requirements'/f'{name}.txt')
        if marker.exists() and json.loads(marker.read_text()).get('requirements_sha256')==requirements_hash:
            print(name+' already configured; keeping it.');continue
        venv=install_python_runtime(root,name,cache,args.wheelhouse)
        if name=='quality':build_quality(root,venv,args)
        if name=='rig':build_rig(root,venv)
        # Import real native dependencies before reporting a component as installed.
        probes={'quality':'import torch,diffusers,custom_rasterizer; assert torch.cuda.is_available()',
                'image':'import torch,diffusers,transformers; assert torch.cuda.is_available()',
                'rig':'import torch,torch_cluster,torch_scatter,spconv; assert torch.cuda.is_available()',
                'tools':'import torch; assert torch.cuda.is_available()'}
        run([venv/'bin/python','-c',probes[name]],env=core_environment(root,'native'),timeout=120)
        private_json(marker,{'schema':1,'installed':True,'component':name,'requirements_sha256':requirements_hash})
    if args.engine or first_quality and 'quality' in names:
        path=profile(root,'native')/'data/settings.json';data=json.loads(path.read_text());data['mesh_engine']='engine2' if args.engine=='fast' else 'engine1';private_json(path,data)
    configure(root)
    print('Native paths configured. Launch the native profile; model and licence checks remain enforced.',flush=True)
