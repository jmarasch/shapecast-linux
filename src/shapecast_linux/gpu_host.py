"""Run the original GPU host with local Linux memory compatibility."""
import json
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(os.environ['SHAPECAST_LINUX_ROOT'])
# Diffusers copies custom pipeline modules at load time. Keep generated code
# writable without granting writes to the shared, read-only model weights.
module_cache = ROOT/'cache/huggingface-modules'
module_cache.mkdir(parents=True, exist_ok=True)
os.environ['HF_MODULES_CACHE'] = str(module_cache)
host = Path(sys.argv[1]).resolve()
sys.argv = sys.argv[1:]
sys.path.insert(0, str(host.parent))
if host.name == 'shapecast_gpu.py':
    print('[linux] Native Quality compatibility wrapper active.', flush=True)
    spec_index = sys.argv.index('--spec')+1
    sys.argv[spec_index] = str(Path(sys.argv[spec_index]).resolve())
    spec = json.loads(Path(sys.argv[spec_index]).read_text())
    models = Path(spec['models_dir'])
    for key, value in {'HY3DGEN_MODELS':models/'hy3dgen', 'HF_HOME':models/'hf',
                       'U2NET_HOME':models/'u2net'}.items():
        os.environ.setdefault(key, str(value))
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
    os.chdir(spec['engine_root'])
    sys.path.insert(0, str(Path(spec['repo_root'])/'server'))
    import hunyuan_stages as stages
    original = stages._enable_shape_offload

    def shape_offload(pipe):
        original(pipe)
        # Whole-model offload cannot fit a busy 8 GB desktop. Keep the
        # original conditioner/VAE chain and page the DiT one block at a time.
        if stages.available_vram_gb() < 7.0:
            from accelerate import cpu_offload
            from accelerate.hooks import remove_hook_from_module
            conditioner_hook, model_hook = pipe._all_hooks[:2]
            remove_hook_from_module(pipe.model, recurse=True)
            cpu_offload(pipe.model, execution_device=stages.torch.device('cuda:0'),
                        preload_module_classes=['HunYuanDiTBlock'])
            pipe.model.register_forward_pre_hook(lambda *_: conditioner_hook.offload())
            # The VAE's existing chain still asks this handle to release the
            # DiT. Its per-block hooks have already released those weights.
            model_hook.offload = lambda: None
            print('[linux] Shape uses block CPU offload; original weights unchanged.', flush=True)

    stages._enable_shape_offload = shape_offload
    original_paint = stages._enable_paint_low_vram

    def paint_offload(paint):
        original_paint(paint)
        if stages.available_vram_gb() < 7.0:
            pipeline = paint.models['multiview_model'].pipeline
            # The custom pipeline reads these small, fixed conditioning
            # tensors outside forward(). Keep their values as resident buffers
            # so Accelerate does not replace them with empty meta tensors.
            for module in pipeline.unet.modules():
                for name, parameter in list(module.named_parameters(recurse=False)):
                    if name.startswith('learned_text_clip_'):
                        del module._parameters[name]
                        module.register_buffer(name, parameter.detach())
            pipeline.enable_sequential_cpu_offload()
            print('[linux] Paint uses sequential CPU offload; original weights unchanged.', flush=True)

    stages._enable_paint_low_vram = paint_offload

runpy.run_path(str(host), run_name='__main__')
