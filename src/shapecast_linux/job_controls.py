"""Non-destructive queue cleanup and persistent, reversible job visibility."""
import asyncio
from functools import wraps
from pathlib import Path
import json
import re
import secrets
import urllib.error
import urllib.request
import uuid

PROXY_PATH = '/linux-jobs-api'
KEY = '_linux_job_hidden'
TERMINAL = ('complete', 'failed', 'cancelled')
_managers = {}


def is_hidden(job):
    return job.status in TERMINAL and (job.params or {}).get(KEY) is True


def visible_clause(Job):
    from sqlalchemy import and_, not_, func
    return not_(and_(Job.status.in_(TERMINAL), func.coalesce(Job.params[KEY].as_boolean(), False)))


def manager_for_db(db):
    return _managers.get(str(Path(db.bind.url.database).resolve()))


def proxy_jobs(handler):
    """Small fixed-scope relay; the browser never needs cross-origin requests."""
    from urllib.parse import urlsplit
    server = handler.server
    if handler.headers.get('Host') not in {f'127.0.0.1:{server.server_port}', f'localhost:{server.server_port}'}:
        handler.send_error(403); return
    supplied = handler.headers.get('Authorization', '').removeprefix('Bearer ').strip()
    if not secrets.compare_digest(supplied.encode(), server.launch_token.encode()):
        handler.send_error(401); return
    parsed = urlsplit(handler.path)
    suffix = parsed.path.removeprefix(PROXY_PATH)
    identifier = r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}'
    if not ((handler.command == 'GET' and suffix == '' and re.fullmatch(r'(?:offset=\d{1,7}&hidden=[01])?', parsed.query))
            or (handler.command == 'POST' and not parsed.query and
                (suffix == '/clear' or re.fullmatch('/'+identifier+r'/(hide|restore|cancel)', suffix)))):
        handler.send_error(404); return
    port = getattr(server, 'core_port', None)
    if type(port) is not int or not 0 < port < 65536:
        handler.send_error(503); return
    body = None
    if handler.command == 'POST':
        if handler.headers.get('Origin') not in (None, f'http://127.0.0.1:{server.server_port}', f'http://localhost:{server.server_port}'):
            handler.send_error(403); return
        try: length = int(handler.headers.get('Content-Length', '0'))
        except ValueError:
            handler.send_error(400); return
        if not 0 < length <= 65536 or handler.headers.get('Transfer-Encoding'):
            handler.send_error(413); return
        body = handler.rfile.read(length)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl): return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    target = f'http://127.0.0.1:{port}/v1/linux-jobs'+suffix+('?' + parsed.query if parsed.query else '')
    request = urllib.request.Request(target, data=body, method=handler.command,
        headers={'Authorization': 'Bearer '+server.launch_token, 'Content-Type': 'application/json'})
    try:
        try: response = opener.open(request, timeout=20)
        except urllib.error.HTTPError as error: response = error
        with response:
            data = response.read(2*1024**2+1)
            if len(data) > 2*1024**2:
                handler.send_error(502); return
            handler.send_response(response.status)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Content-Length', str(len(data)))
            handler.send_header('Cache-Control', 'no-store')
            handler.send_header('X-Content-Type-Options', 'nosniff')
            handler.end_headers(); handler.wfile.write(data)
    except (BrokenPipeError, ConnectionResetError): pass
    except OSError:
        try: handler.send_error(502, 'The local job service is unavailable.')
        except (BrokenPipeError, ConnectionResetError): pass


class JobManager:
    def __init__(self, app):
        self.app = app
        # Admission and clearing share this lock so a waiting job cannot start halfway through a clear.
        self.lock = asyncio.Lock()

    async def action(self, action, body, job_id=None):
        from shapecast_core import jobs_service as jobs, queue_service as queue
        from shapecast_core.models import Job
        if not isinstance(body, dict): raise ValueError('Invalid job request.')
        ids = None
        if action == 'clear':
            raw = body.get('job_ids')
            if not isinstance(raw, list) or not raw or len(raw) > 1000:
                raise ValueError('Refresh the queue before clearing it.')
            ids = list(dict.fromkeys(uuid.UUID(value) for value in raw if isinstance(value, str)))
            if len(ids) != len(raw): raise ValueError('Invalid queue snapshot.')
        elif action not in ('hide', 'restore', 'cancel'):
            raise ValueError('Unknown job action.')
        changed, skipped = 0, 0
        async with self.lock, self.app.state.sessionmaker() as db:
            for identifier in ids or [job_id]:
                job = await db.get(Job, identifier)
                if job is None:
                    if ids: skipped += 1; continue
                    raise ValueError('This job is no longer available.')
                if action in ('clear', 'cancel'):
                    if job.status != 'queued':
                        if ids: skipped += 1; continue
                        raise ValueError('This job has started. Use its cast controls to stop it.')
                    await jobs.cancel_job(db, self.app.state.bus, job)
                    # No host is stopped: only waiting jobs can reach this branch.
                    changed += 1
                else:
                    if action == 'hide' and job.status not in TERMINAL:
                        raise ValueError('Finish or cancel this job before hiding it.')
                    params = dict(job.params or {})
                    if action == 'hide': params[KEY] = True
                    else: params.pop(KEY, None)
                    job.params = params
                    changed += 1
            if action in ('clear', 'cancel'):
                await queue.compact(db)
            await db.commit()
        return {'changed': changed, 'skipped': skipped}


def install_hooks():
    from sqlalchemy import select
    from shapecast_core import queue_service as queue
    from shapecast_core.models import Job
    if getattr(queue.start_next, '_linux_job_controls', False): return
    original_start, original_recent = queue.start_next, queue.recent

    @wraps(original_start)
    async def start(db, bus, settings):
        manager = manager_for_db(db)
        if manager:
            async with manager.lock: return await original_start(db, bus, settings)
        return await original_start(db, bus, settings)

    @wraps(original_recent)
    async def recent(db, limit=25):
        if not manager_for_db(db): return await original_recent(db, limit)
        return list((await db.scalars(select(Job).where(Job.status.in_(TERMINAL), visible_clause(Job))
            .order_by(Job.finished_at.desc(), Job.created_at.desc()).limit(limit))).all())

    start._linux_job_controls = True
    queue.start_next, queue.recent = start, recent


def install_job_controls(app):
    if getattr(app.state, "linux_job_controls", None): return app.state.linux_job_controls
    from fastapi import Depends, HTTPException, Query, Request
    from sqlalchemy import select, func, not_
    from shapecast_core.models import Job
    from shapecast_core.api.deps import get_db
    from shapecast_core.api.routers import jobs as jobs_router
    install_hooks()
    manager = JobManager(app)
    _managers[str(Path(app.state.settings.db_path).resolve())] = manager
    app.state.linux_job_controls = manager
    # Register before included routers: newer FastAPI versions include them lazily.
    # Preserve the vendor's response model/dependency and filter before pagination.
    original = next(route for route in jobs_router.router.routes
                    if getattr(route, 'path', None) == '/v1/jobs' and 'GET' in route.methods)

    @app.get('/v1/jobs', response_model=original.response_model, include_in_schema=False)
    async def listed(status: str | None = Query(None), limit: int = Query(50),
                     offset: int = Query(0), db=Depends(get_db)):
        query = select(Job).where(visible_clause(Job)).order_by(Job.created_at.desc())
        if status: query = query.where(Job.status == status)
        return (await db.scalars(query.limit(limit).offset(offset))).all()
    app.routes.insert(0, app.routes.pop())

    @app.get('/v1/linux-jobs')
    async def listing(offset: int = 0, hidden: int = 0):
        if not 0 <= offset <= 1000000 or hidden not in (0, 1):
            raise HTTPException(400, 'Invalid job list.')
        async with app.state.sessionmaker() as db:
            visibility = visible_clause(Job)
            where = not_(visibility) if hidden else visibility
            rows = (await db.scalars(select(Job).where(where).order_by(Job.created_at.desc(), Job.id).limit(50).offset(offset))).all()
            total = await db.scalar(select(func.count()).select_from(Job).where(where))
            queued = (await db.scalars(select(Job.id).where(Job.status == 'queued').order_by(Job.created_at))).all()
            return {'jobs': [{'id': str(job.id), 'title': ((job.params or {}).get('name') or job.prompt_raw or 'Untitled cast')[:300],
                'status': job.status, 'hidden': is_hidden(job), 'created_at': job.created_at.isoformat(),
                'can_hide': job.status in TERMINAL} for job in rows],
                'total': total, 'offset': offset, 'queued_ids': [str(identifier) for identifier in queued]}

    async def perform(action, request, job_id=None):
        try:
            return await manager.action(action, await request.json(), job_id)
        except (ValueError, TypeError, AttributeError, json.JSONDecodeError) as error:
            raise HTTPException(409, str(error)) from None

    @app.post('/v1/linux-jobs/clear')
    async def clear(request: Request): return await perform('clear', request)

    @app.post('/v1/linux-jobs/{job_id}/{action}')
    async def action(job_id: uuid.UUID, action: str, request: Request):
        return await perform(action, request, job_id)
    return manager
