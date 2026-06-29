import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlmodel import Session

from database import init_db, get_session, get_config, set_config
from config import decrypt
from event_logger import read_logs, list_log_dates, log_event
from xiaomi_client import xiaomi_client
from scheduler import scheduler_loop
from voice_poller import voice_poller_loop
from ws_manager import ws_manager
from api import children, schedule, points, stats

APP_VERSION = "1.0.0"

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# 保留应用自身的 INFO 日志
logging.getLogger("main").setLevel(logging.INFO)
logging.getLogger("scheduler").setLevel(logging.INFO)
logging.getLogger("voice_poller").setLevel(logging.INFO)
logging.getLogger("xiaomi_client").setLevel(logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Init DB
    init_db()

    # Load Xiaomi credentials and start background tasks
    from database import engine
    with Session(engine) as session:
        device_id = get_config(session, "mi_device_id") or ""
        logged_in = await xiaomi_client.load_from_db(session)

    if logged_in and device_id:
        logger.info("Starting scheduler and voice poller for device %s", device_id)
        asyncio.create_task(scheduler_loop(device_id))
        asyncio.create_task(voice_poller_loop(device_id))
    else:
        logger.warning("Xiaomi not configured — scheduler/poller not started. Go to Settings.")

    yield
    await xiaomi_client.close()


app = FastAPI(title="暑假课表系统", lifespan=lifespan)

# Routers
app.include_router(children.router)
app.include_router(schedule.router)
app.include_router(points.router)
app.include_router(stats.router)


# ---------- Xiaomi config endpoints ----------

class XiaomiConfig(BaseModel):
    account: str
    password: str
    device_id: str


@app.post("/api/config/xiaomi")
async def save_xiaomi_config(body: XiaomiConfig, session: Session = Depends(get_session)):
    await xiaomi_client.save_to_db(session, body.account, body.password)
    set_config(session, "mi_device_id", body.device_id)
    # force_reauth=True: clear cached token so the password is actually validated
    # against Xiaomi servers, preventing a stale token from making a wrong password
    # appear successful.
    ok = await xiaomi_client.login(body.account, body.password, force_reauth=True)
    if ok:
        # Restart background tasks with new config
        asyncio.create_task(scheduler_loop(body.device_id))
        asyncio.create_task(voice_poller_loop(body.device_id))
    return {"ok": ok}


@app.post("/api/config/xiaomi/test")
async def test_xiaomi(session: Session = Depends(get_session)):
    device_id = get_config(session, "mi_device_id") or ""
    result = await xiaomi_client.test_connection(device_id)
    return result


@app.get("/api/config/xiaomi/status")
async def xiaomi_status(session: Session = Depends(get_session)):
    """Return whether Xiaomi is configured and connected."""
    device_id = get_config(session, "mi_device_id") or ""
    account = get_config(session, "mi_account") or ""
    configured = bool(device_id and account)
    logged_in = xiaomi_client._mina is not None
    return {"configured": configured, "connected": logged_in, "account": account, "device_id": device_id}


@app.get("/api/config/xiaomi")
async def get_xiaomi_config(session: Session = Depends(get_session)):
    """Return saved Xiaomi config for form pre-fill (password omitted for security)."""
    account_enc = get_config(session, "mi_account")
    account = decrypt(account_enc) if account_enc else ""
    return {"account": account, "device_id": get_config(session, "mi_device_id") or ""}


# ---------- Event Logs ----------

@app.get("/api/logs/dates")
async def get_log_dates():
    """Return list of dates that have log files."""
    return {"dates": list_log_dates()}


@app.get("/api/logs")
async def get_logs(date: str | None = None):
    """Return log lines for a given date (default today)."""
    lines = read_logs(date)
    return {"date": date, "lines": lines}


# ---------- WebSocket ----------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keep alive
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ---------- Static frontend ----------

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)


class NoCacheStaticFiles(StaticFiles):
    """StaticFiles that never returns 304 — browser always gets fresh content."""
    def file_response(self, full_path, stat_result, scope, status_code=200):
        # Skip is_not_modified check entirely — always return 200 with no-cache headers
        from starlette.responses import FileResponse as FR
        response = FR(full_path, status_code=status_code, stat_result=stat_result)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        if "etag" in response.headers:
            del response.headers["etag"]
        if "last-modified" in response.headers:
            del response.headers["last-modified"]
        return response


app.mount("/static", NoCacheStaticFiles(directory=STATIC_DIR), name="static")


import time as _time

@app.get("/")
def index():
    # Inject timestamp version into JS references to completely bust browser cache
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    ver = str(int(_time.time()))
    import re
    html = re.sub(r'src="(/static/.+?\.js)"', f'src="\\1?v={ver}"', html)
    html = html.replace("<!--APP_VERSION-->", f"v{APP_VERSION}")
    resp = Response(content=html, media_type="text/html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    return resp


if __name__ == "__main__":
    import uvicorn
    import socket
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "127.0.0.1"
    print(f"\n{'='*44}")
    print(f"  暑假课表系统已启动")
    print(f"  本机访问：  http://localhost:8080")
    print(f"  局域网访问：http://{local_ip}:8080")
    print(f"  按 Ctrl+C 停止服务")
    print(f"{'='*44}\n")
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False, log_level="warning")
