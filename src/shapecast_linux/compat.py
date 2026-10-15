"""Process-local tool compatibility; vendor core files stay unchanged."""
from functools import wraps
import os
from pathlib import Path


class ContextWithParameters:
    def __init__(self,original,params):
        self._original=original
        self.params=params
    def __getattr__(self,name):return getattr(self._original,name)


def install_host_context():
    from shapecast_core.stages import engine
    if getattr(engine.run_host,'_linux_context_compat',False):return
    original=engine.run_host
    @wraps(original)
    async def run_host(ctx,stage,python,host,spec):
        if not hasattr(ctx,'params'):ctx=ContextWithParameters(ctx,spec.get('params',{}))
        engine._stage_timeout(ctx,stage)
        return await original(ctx,stage,python,host,spec)
    run_host._linux_context_compat=True
    engine.run_host=run_host


def install(root):
    install_host_context()
    from shapecast_core.stages import blender
    if getattr(blender.run_blender,'_linux_topology_compat',False):return
    binary=Path(root)/'components/instant-meshes/Instant Meshes'
    original=blender.run_blender
    @wraps(original)
    async def run_blender(exe,script,argv,timeout,cancelled=lambda:False):
        args=list(argv)
        if Path(script).name=='retopo_rebake.py':
            if not binary.is_file() or not os.access(binary,os.X_OK):raise RuntimeError('Install the native topology component before rebuilding topology.')
            try:index=args.index('--im')+1
            except ValueError:raise RuntimeError('The topology invocation has no remesher argument.')
            if Path(args[index]).name=='Instant Meshes.exe':args[index]=str(binary)
        return await original(exe,script,args,timeout,cancelled)
    run_blender._linux_topology_compat=True
    blender.run_blender=run_blender
