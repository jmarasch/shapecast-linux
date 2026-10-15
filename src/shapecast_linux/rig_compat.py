"""Local inference-only SDPA adaptation for the installed UniRig point encoder.

Keep the vendor's source/checkpoints intact. The projection, padding, point
ordering, scale and dtype stay unchanged. RPE, upcasts, training and upstream
Flash Attention continue through the original method.
"""
import inspect
import textwrap
from pathlib import Path

import os
PACK=Path(os.environ['SHAPECAST_LINUX_RIG_PACK'])


def install():
    import sys
    sys.path.insert(0,str(PACK))
    from src.model.pointcept.models.PTv3Object import SerializedAttention
    if getattr(SerializedAttention.forward,'_linux_sdpa',False):
        return
    original=SerializedAttention.forward
    source=textwrap.dedent(inspect.getsource(original))
    start=source.index('        # attn\n')
    end=source.index('\n    else:\n        feat = flash_attn.',start)
    replacement='''        feat = torch.nn.functional.scaled_dot_product_attention(
            q, k, v, dropout_p=0.0, scale=self.scale
        ).transpose(1, 2).reshape(-1, C)'''
    source=source[:start]+replacement+source[end:]
    source=source.replace('def forward(self, point):\n','''def forward(self, point):
    if (self.training or self.enable_flash or self.enable_rpe
            or self.upcast_attention or self.upcast_softmax):
        return _original_forward(self, point)
''',1)
    namespace=dict(original.__globals__)
    namespace['_original_forward']=original
    exec(compile(source,__file__+' (adapted forward)','exec'),namespace)
    optimized=namespace['forward']
    optimized._linux_sdpa=True
    optimized._original_forward=original
    SerializedAttention.forward=optimized
