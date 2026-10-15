"""Process-local Linux topology adaptation; vendor core files stay unchanged."""
from functools import wraps
import os
from pathlib import Path


def install(root):
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
