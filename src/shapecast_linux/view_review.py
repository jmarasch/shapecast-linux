"""A persistent approval gate between alternate images and mesh generation.

The original image stage still runs through the vendor queue and licence checks.
Only helper state is added to job parameters; commercial files stay unchanged.
"""
import asyncio
import copy
from functools import wraps
from pathlib import Path
import uuid
import secrets
import re
import urllib.request
import urllib.error
import base64
import logging
import hmac
import hashlib
import time
import json

PROXY_PATH = '/linux-view-review-api'
IMAGE_PATH = '/linux-view-review-image'


def image_signature(token, suffix, expires):
    return hmac.new(token.encode(), (suffix+':'+str(expires)).encode(), hashlib.sha256).hexdigest()


def image_urls(server, review):
    expires = int(time.time())+3600
    result = {}
    for view in ['front']+[v['name'] for v in review['views']]:
        suffix = '/'+review['job_id']+'/image/'+view
        signature = image_signature(server.launch_token, suffix, expires)
        result[view] = IMAGE_PATH+suffix+'?expires='+str(expires)+'&signature='+signature+'&revision='+str(review['revision'])
    return result


def proxy_review(handler):
    """Relay only authenticated review requests through the UI's own loopback origin."""
    from urllib.parse import urlsplit, parse_qs
    server = handler.server
    if handler.headers.get('Host') not in {f'127.0.0.1:{server.server_port}', f'localhost:{server.server_port}'}:
        handler.send_error(403); return
    parsed = urlsplit(handler.path)
    direct_image = parsed.path.startswith(IMAGE_PATH)
    suffix = parsed.path.removeprefix(IMAGE_PATH if direct_image else PROXY_PATH)
    identifier = r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}'
    valid_get = suffix == '' or re.fullmatch('/'+identifier+r'/image/(front|left|back|right)', suffix)
    valid_post = re.fullmatch('/'+identifier+r'/(approve|regenerate|continue|cancel)', suffix)
    if direct_image:
        query = parse_qs(parsed.query)
        try: expires = int(query.get('expires', ['0'])[0])
        except ValueError: expires = 0
        signature = query.get('signature', [''])[0]
        if (handler.command != 'GET' or not valid_get or suffix == '' or not re.fullmatch('[0-9a-f]{64}', signature)
                or not int(time.time()) <= expires <= int(time.time())+3600
                or not secrets.compare_digest(signature, image_signature(server.launch_token, suffix, expires))):
            handler.send_error(401); return
    else:
        supplied = handler.headers.get('Authorization', '').removeprefix('Bearer ').strip()
        if not secrets.compare_digest(supplied.encode(), server.launch_token.encode()):
            handler.send_error(401); return
    if (handler.command == 'GET' and not valid_get) or (handler.command == 'POST' and not valid_post):
        handler.send_error(404); return
    port = getattr(server, 'core_port', None)
    if type(port) is not int or not 0 < port < 65536:
        handler.send_error(503); return
    body = None
    if handler.command == 'POST':
        if handler.headers.get('Origin') not in (None, f'http://127.0.0.1:{server.server_port}', f'http://localhost:{server.server_port}'):
            handler.send_error(403); return
        try:
            length = int(handler.headers.get('Content-Length', '0'))
        except ValueError:
            handler.send_error(400); return
        if not 0 < length <= 4096 or handler.headers.get('Transfer-Encoding'):
            handler.send_error(413); return
        body = handler.rfile.read(length)
    # A fixed address, fixed route family and no proxy/redirects prevent arbitrary forwarding.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    target = f'http://127.0.0.1:{port}/v1/linux-view-reviews'+suffix
    req = urllib.request.Request(target, data=body, method=handler.command,
        headers={'Authorization':'Bearer '+server.launch_token, 'Content-Type':'application/json'})
    try:
        try: response = opener.open(req, timeout=20)
        except urllib.error.HTTPError as error: response = error
        with response:
            data = response.read(32*1024**2+1)
            if len(data) > 32*1024**2:
                handler.send_error(502); return
            content_type = response.headers.get('Content-Type', 'application/json')
            if response.status == 200 and suffix == '':
                payload = json.loads(data)
                for review in payload.get('reviews', []): review['images'] = image_urls(server, review)
                data = json.dumps(payload).encode()
            elif response.status == 200 and direct_image:
                payload = json.loads(data)
                if payload.get('content_type') != 'image/png':
                    handler.send_error(502); return
                data = base64.b64decode(payload['data'], validate=True)
                content_type = 'image/png'
            handler.send_response(response.status)
            handler.send_header('Content-Type', content_type)
            handler.send_header('Content-Length', str(len(data)))
            handler.send_header('Cache-Control', 'no-store')
            handler.send_header('X-Content-Type-Options', 'nosniff')
            handler.end_headers()
            handler.wfile.write(data)
    except (BrokenPipeError, ConnectionResetError):
        return  # Navigating away can close an in-flight thumbnail request.
    except (OSError, ValueError, KeyError):
        try:
            handler.send_error(502, 'The local image review service is unavailable.')
        except (BrokenPipeError, ConnectionResetError):
            pass

KEY = '_linux_view_review'
REGEN = '_linux_view_regeneration'
VIEWS = ('left', 'back', 'right')
_managers = {}


class ReviewConflict(ValueError):
    pass


def review_state(job):
    value = (job.params or {}).get(KEY)
    return copy.deepcopy(value) if isinstance(value, dict) and value.get('schema') == 1 else None


def checked_state(job, revision):
    state = review_state(job)
    if (not state or job.status != 'awaiting_selection' or state['phase'] != 'pending'
            or type(revision) is not int or revision != state['revision']):
        raise ReviewConflict('These views changed. Refresh the review before continuing.')
    return state


def accept_view(state, view):
    if view not in state['views']:
        raise ReviewConflict('This view is not part of the review.')
    state['views'][view]['accepted'] = True
    state['revision'] += 1
    return state


def approved_keys(state):
    if not state['views'] or not all(v['accepted'] for v in state['views'].values()):
        raise ReviewConflict('Approve every alternate view before building the geometry.')
    return {name: item['key'] for name, item in state['views'].items()}


def save_state(job, state):
    job.params = {**(job.params or {}), KEY: state}


def manager_for(settings):
    return _managers.get(str(Path(settings.data_dir).resolve()))


class ReviewManager:
    def __init__(self, app):
        self.app = app
        self.lock = asyncio.Lock()

    async def gate(self, db, bus, job, ref_key, view_keys):
        from shapecast_core import jobs_service as jobs, statuses as st
        if not view_keys:
            return False
        if any(name not in VIEWS for name in view_keys):
            raise ReviewConflict('This version uses an unsupported alternate-view layout.')
        state = review_state(job)
        if state and state['phase'] == 'approved' and state['front_key'] == ref_key:
            if approved_keys(state) == view_keys:
                return False
        state = {'schema': 1, 'phase': 'pending', 'revision': (state or {}).get('revision', 0)+1,
                 'front_key': ref_key, 'error': None, 'active': None,
                 'views': {name: {'key': key, 'accepted': False, 'generation': 0}
                           for name, key in view_keys.items()}}
        save_state(job, state)
        await jobs.transition(db, bus, job, st.AWAITING_SELECTION, stage=st.STAGE_IMAGE,
                              message='Review and approve the alternate views before building geometry.', commit=False)
        return True

    async def complete_regeneration(self, runner, db, job, files, error=None):
        from shapecast_core import jobs_service as jobs, statuses as st
        state = review_state(job)
        active = state['active']
        output = next((f for f in files if f.storage_key == active['key'] and f.file_kind == st.F_REF_VIEW), None)
        if output is not None and runner.storage.exists(output.storage_key):
            previous = state['views'][active['view']]
            state['views'][active['view']] = {'key': output.storage_key, 'accepted': False,
                                             'generation': previous['generation']+1}
            state['error'] = None
            message = 'Replacement view ready. Review it before continuing.'
        else:
            state['error'] = 'The view could not be regenerated. Your previous image was kept. You can try again.'
            message = state['error']
        state.update(phase='pending', active=None, revision=state['revision']+1)
        save_state(job, state)
        await jobs.transition(db, runner.bus, job, st.AWAITING_SELECTION, stage=st.STAGE_IMAGE,
                              message=message, commit=False)

    async def recover(self, runner):
        """A crash between a completed work item and its review must not fail the cast."""
        from sqlalchemy import select
        from shapecast_core import jobs_service as jobs, statuses as st
        from shapecast_core.models import Job, WorkItem
        async with runner.sessionmaker() as db:
            for job in (await db.scalars(select(Job).where(Job.status == st.GENERATING_IMAGE))).all():
                state = review_state(job)
                if not state or state['phase'] != 'regenerating':
                    continue
                unfinished = await db.scalar(select(WorkItem).where(WorkItem.job_id == job.id,
                    WorkItem.stage == st.STAGE_IMAGE, WorkItem.state.in_([st.W_PENDING, st.W_RUNNING])))
                if unfinished is None:
                    await self.complete_regeneration(runner, db, job, [])
            await db.commit()

    def snapshot(self, job):
        state = review_state(job)
        if not state or state['phase'] not in ('pending', 'regenerating'):
            return None
        if job.status not in ('awaiting_selection', 'generating_image'):
            return None
        return {'job_id': str(job.id), 'title': (job.params or {}).get('name') or job.prompt_raw,
                'revision': state['revision'], 'phase': state['phase'], 'error': state['error'],
                'regenerating_view': (state.get('active') or {}).get('view'),
                'views': [{'name': name, 'accepted': item['accepted'], 'generation': item['generation']}
                          for name, item in state['views'].items()]}

    async def action(self, job_id, action, revision, view=None):
        from sqlalchemy import select
        from shapecast_core import jobs_service as jobs, statuses as st
        from shapecast_core.models import Job, WorkItem
        from shapecast_core.storage import work_key
        state_app = self.app.state
        async with self.lock, state_app.sessionmaker() as db:
            job = await db.get(Job, job_id)
            if job is None:
                raise ReviewConflict('This cast is no longer available.')
            if action == 'cancel':
                state = review_state(job)
                if not state or not self.snapshot(job) or type(revision) is not int or revision != state['revision']:
                    raise ReviewConflict('These views changed. Refresh the review before continuing.')
            else:
                state = checked_state(job, revision)
            if action == 'approve':
                accept_view(state, view)
                save_state(job, state)
            elif action == 'regenerate':
                if view not in state['views']:
                    raise ReviewConflict('This view is not part of the review.')
                # New output and seed prevent the host's file cache from reusing a rejected image.
                seed = jobs.new_seed()
                while seed == state.get('last_seed', (job.params or {}).get('seed')):
                    seed = jobs.new_seed()
                active = {'view': view, 'key': work_key(job.id, 'view-review/'+uuid.uuid4().hex+'/'+view+'.png'), 'seed': seed}
                state['views'][view]['accepted'] = False
                state.update(phase='regenerating', active=active, error=None, last_seed=seed, revision=state['revision']+1)
                save_state(job, state)
                await jobs.create_work_item(db, job.id, st.STAGE_IMAGE,
                    {'mode': 'views', 'kind': job.kind, 'pose': (job.params or {}).get('pose'), 'seed': seed,
                     'view_keys': {state['front_key']: {view: active['key']}}, REGEN: True})
                await jobs.transition(db, state_app.bus, job, st.GENERATING_IMAGE, stage=st.STAGE_IMAGE,
                                      message='Regenerating the '+view+' view; accepted views are kept.', commit=False)
            elif action == 'continue':
                keys = approved_keys(state)
                for key in [state['front_key'], *keys.values()]:
                    if not state_app.storage.exists(key):
                        raise ReviewConflict('A reference image is missing. Regenerate it before continuing.')
                unfinished = await db.scalar(select(WorkItem).where(WorkItem.job_id == job.id,
                                                WorkItem.state.in_([st.W_PENDING, st.W_RUNNING])))
                if unfinished is not None:
                    raise ReviewConflict('This cast already has work queued.')
                state.update(phase='approved', revision=state['revision']+1)
                save_state(job, state)
                # This is the original vendor dispatch path, with the exact approved images.
                await jobs._dispatch_shape(db, state_app.bus, state_app.settings, job, state['front_key'], view_keys=keys)
            elif action == 'cancel':
                await jobs.cancel_job(db, state_app.bus, job)
                state_app.runner.cancel_job(job.id)
            else:
                raise ReviewConflict('Unknown review action.')
            await db.commit()
            return self.snapshot(job) or {'job_id': str(job.id), 'phase': action+'d'}


def install_hooks():
    from shapecast_core import jobs_service as jobs, statuses as st
    from shapecast_core import runner as runner_module
    from shapecast_core.runner import StageRunner
    from shapecast_core.stages.engine import EngineImageStage
    from shapecast_core.stages.base import StageResult, Cancelled
    if getattr(StageRunner._queue_shape, '_linux_view_review', False):
        return
    original_queue = StageRunner._queue_shape
    original_dispatch = jobs._dispatch_shape
    original_after = StageRunner._after_image
    original_advance = StageRunner._advance
    original_image = EngineImageStage.run
    original_recover = StageRunner.recover
    original_views = jobs.variant_view_keys
    original_fail = runner_module.fail_job

    @wraps(original_queue)
    async def queue(runner, db, job, ref_key, view_keys=None):
        manager = manager_for(runner.settings)
        if manager and await manager.gate(db, runner.bus, job, ref_key, view_keys):
            return
        return await original_queue(runner, db, job, ref_key, view_keys=view_keys)

    @wraps(original_dispatch)
    async def dispatch(db, bus, settings, job, ref_key, view_keys=None):
        manager = manager_for(settings)
        if manager and await manager.gate(db, bus, job, ref_key, view_keys):
            return
        return await original_dispatch(db, bus, settings, job, ref_key, view_keys=view_keys)

    @wraps(original_after)
    async def after(runner, db, job, files):
        manager, state = manager_for(runner.settings), review_state(job)
        if manager and state and state['phase'] == 'regenerating':
            async with manager.lock:
                return await manager.complete_regeneration(runner, db, job, files)
        return await original_after(runner, db, job, files)

    @wraps(original_image)
    async def image(stage, ctx):
        if not ctx.params.get(REGEN):
            return await original_image(stage, ctx)
        try:
            return await original_image(stage, ctx)
        except Cancelled:
            raise
        except Exception:
            # A rejected view can fail without destroying the whole cast or its other references.
            logging.getLogger('shapecast.linux.view_review').warning(
                'Alternate-view regeneration failed; keeping the previous image.', exc_info=True)
            return StageResult(outputs=[], metrics={REGEN: 'failed'})

    @wraps(original_advance)
    async def advance(runner, job_id, stage, result):
        manager = manager_for(runner.settings)
        if manager and stage == st.STAGE_IMAGE and result.metrics.get(REGEN) == 'failed':
            from shapecast_core.models import Job
            async with manager.lock, runner.sessionmaker() as db:
                job = await db.get(Job, job_id)
                state = review_state(job) if job else None
                if state and state['phase'] == 'regenerating' and job.status not in st.TERMINAL:
                    await manager.complete_regeneration(runner, db, job, [])
                    await db.commit()
            return
        return await original_advance(runner, job_id, stage, result)

    @wraps(original_recover)
    async def recover(runner):
        manager = manager_for(runner.settings)
        if manager:
            await manager.recover(runner)
        return await original_recover(runner)

    @wraps(original_views)
    async def views(db, job, variant_key):
        state = review_state(job)
        if state and state['front_key'] == variant_key:
            return {name: item['key'] for name, item in state['views'].items()}
        return await original_views(db, job, variant_key)

    @wraps(original_fail)
    async def fail(db, bus, job, stage, error):
        state = review_state(job)
        if stage == st.STAGE_IMAGE and state and state['phase'] == 'regenerating':
            # Includes the runner's outer timeout, which can cancel the image host itself.
            database = str(Path(db.bind.url.database).resolve())
            manager = next((m for m in _managers.values()
                            if str(Path(m.app.state.settings.db_path).resolve()) == database), None)
            if manager:
                await manager.complete_regeneration(manager.app.state.runner, db, job, [])
                await db.commit()
                return
        return await original_fail(db, bus, job, stage, error)

    queue._linux_view_review = True
    StageRunner._queue_shape = queue
    jobs._dispatch_shape = dispatch
    StageRunner._after_image = after
    StageRunner._advance = advance
    StageRunner.recover = recover
    EngineImageStage.run = image
    jobs.variant_view_keys = views
    runner_module.fail_job = fail


def install_view_review(app):
    from fastapi import Request, HTTPException
    from fastapi.responses import JSONResponse
    from sqlalchemy import select
    from shapecast_core.api.deps import require_generation_ready
    from shapecast_core.models import Job
    install_hooks()
    manager = ReviewManager(app)
    _managers[str(Path(app.state.settings.data_dir).resolve())] = manager
    app.state.linux_view_review = manager

    @app.middleware('http')
    async def protect_paused_reference(request, call_next):
        # The vendor's original selection/revision controls must not skip our approval gate.
        parts = request.url.path.strip('/').split('/')
        if request.method == 'POST' and len(parts) == 4 and parts[:2] == ['v1', 'jobs'] and parts[3] in ('select-variant', 'revise'):
            supplied = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
            if not secrets.compare_digest(supplied, app.state.token):
                return await call_next(request)
            try:
                job_id = uuid.UUID(parts[2])
            except ValueError:
                return await call_next(request)
            async with app.state.sessionmaker() as db:
                job = await db.get(Job, job_id)
                if job and manager.snapshot(job):
                    return JSONResponse({'detail': 'Review the alternate views before continuing.'}, status_code=409)
        return await call_next(request)

    @app.get('/v1/linux-view-reviews')
    async def pending():
        async with app.state.sessionmaker() as db:
            rows = (await db.scalars(select(Job).where(Job.status.in_(['awaiting_selection', 'generating_image']))
                                     .order_by(Job.created_at))).all()
            return {'reviews': [item for job in rows if (item := manager.snapshot(job))]}

    @app.get('/v1/linux-view-reviews/{job_id}/image/{view}')
    async def image(job_id: uuid.UUID, view: str):
        async with app.state.sessionmaker() as db:
            job = await db.get(Job, job_id)
            state = review_state(job) if job else None
            if not state or not manager.snapshot(job) or (view != 'front' and view not in state['views']):
                raise HTTPException(404, 'This review image is not available.')
            key = state['front_key'] if view == 'front' else state['views'][view]['key']
            path = app.state.storage.path(key).resolve()
            if not any(path.is_relative_to(Path(root).resolve()) for root in (app.state.settings.work_dir, app.state.settings.library_dir)):
                raise HTTPException(404, 'This review image is not available.')
            if not path.is_file() or path.stat().st_size > 20*1024**2:
                raise HTTPException(404, 'This review image is not available.')
            # JSON avoids embedded-browser binary-transfer failures; the original image is unchanged.
            return JSONResponse({'content_type':'image/png', 'data':base64.b64encode(path.read_bytes()).decode('ascii')},
                                headers={'Cache-Control':'no-store'})

    @app.post('/v1/linux-view-reviews/{job_id}/{action}')
    async def action(job_id: uuid.UUID, action: str, request: Request):
        if action in ('regenerate', 'continue'):
            require_generation_ready(request)
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ReviewConflict('Invalid review request.')
            return await manager.action(job_id, action, body.get('revision'), body.get('view'))
        except (ReviewConflict, ValueError) as error:
            raise HTTPException(409, str(error)) from None
    return manager
