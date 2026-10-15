import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock,patch
from shapecast_linux.compat import install_host_context

class HostContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_touchup_context_gets_spec_parameters_before_timeout_and_spawn(self):
        engine=SimpleNamespace(run_host=AsyncMock(return_value='result'),_stage_timeout=Mock())
        original=engine.run_host
        original._linux_context_compat=False
        stages=SimpleNamespace(engine=engine)
        ctx=SimpleNamespace(job_id='synthetic-job')
        with patch.dict(sys.modules,{'shapecast_core':SimpleNamespace(stages=stages),'shapecast_core.stages':stages}):
            install_host_context()
            result=await engine.run_host(ctx,'texture','python','host',{'params':{'texture_size':2048}})
        adapted=original.call_args.args[0]
        self.assertEqual(adapted.params,{'texture_size':2048})
        self.assertEqual(adapted.job_id,ctx.job_id)
        engine._stage_timeout.assert_called_once_with(adapted,'texture')
        self.assertEqual(result,'result')

    async def test_existing_context_is_preserved_and_invalid_timeout_does_not_spawn(self):
        engine=SimpleNamespace(run_host=AsyncMock(),_stage_timeout=Mock(side_effect=ValueError('bad timeout')))
        original=engine.run_host;original._linux_context_compat=False;ctx=SimpleNamespace(params={})
        stages=SimpleNamespace(engine=engine)
        with patch.dict(sys.modules,{'shapecast_core':SimpleNamespace(stages=stages),'shapecast_core.stages':stages}):
            install_host_context()
            with self.assertRaises(ValueError):await engine.run_host(ctx,'texture','python','host',{'params':{}})
        original.assert_not_called();self.assertIs(engine._stage_timeout.call_args.args[0],ctx)

if __name__=='__main__':unittest.main()
