#!/usr/bin/env python
"""
Auto Video Editor — API job-oriented.

Fluxo: upload -> processa -> download -> delete.
Sem gerenciador de arquivos, sem histórico. Armazenamento efêmero em tmp/<job_id>/.
"""

import os
import sys
import shutil
import threading
import time
import uuid
import multiprocessing as mp
from queue import Empty
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, request, jsonify, send_file, session, redirect, url_for
from flask_socketio import SocketIO, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import worker as _worker

# macOS usa spawn por padrão; garantimos explicitamente
try:
    mp.set_start_method("spawn")
except RuntimeError:
    pass

# ==================== Config ====================

PROJECT_ROOT = Path(__file__).parent.resolve()
TMP_DIR = PROJECT_ROOT / "tmp"

# Startup: limpa tmp/ de execuções anteriores (jobs em memória foram perdidos)
if TMP_DIR.exists():
    for p in TMP_DIR.iterdir():
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
TMP_DIR.mkdir(exist_ok=True)
CONFIG_FILE = PROJECT_ROOT / "config.json"


VALID_COMPUTE_TYPES = ("int8", "int8_float32", "float32")
VALID_PROVIDERS = ("google", "openrouter")
_config: dict = {}


def _default_model(provider: str) -> str:
    return "google/gemini-2.5-flash" if provider == "openrouter" else "gemini-2.5-flash"


def _current_model() -> str:
    provider = os.environ.get("LLM_PROVIDER", "google")
    models = _config.get("llm_models", {}) or {}
    return models.get(provider, "") or _default_model(provider)


def _apply_model_env():
    os.environ["LLM_MODEL"] = _current_model()


def _load_config():
    import json
    global _config
    if CONFIG_FILE.exists():
        try:
            _config = json.loads(CONFIG_FILE.read_text())
        except Exception as e:
            print(f"[config] erro ao ler: {e}")
            _config = {}

    # Migração do formato antigo (llm_model único) para novo (llm_models por provider)
    if "llm_model" in _config and "llm_models" not in _config:
        legacy_provider = _config.get("llm_provider", "google")
        _config["llm_models"] = {legacy_provider: _config["llm_model"]}
        _config.pop("llm_model", None)

    if _config.get("gemini_api_key"):
        os.environ["GEMINI_API_KEY"] = _config["gemini_api_key"]
    if _config.get("openrouter_api_key"):
        os.environ["OPENROUTER_API_KEY"] = _config["openrouter_api_key"]

    provider = _config.get("llm_provider", "google")
    if provider not in VALID_PROVIDERS:
        provider = "google"
    os.environ["LLM_PROVIDER"] = provider
    _apply_model_env()

    ct = _config.get("whisper_compute_type", "int8")
    if ct not in VALID_COMPUTE_TYPES:
        ct = "int8"
    os.environ["WHISPER_COMPUTE_TYPE"] = ct


def _save_config():
    import json
    CONFIG_FILE.write_text(json.dumps(_config))
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except Exception:
        pass


_load_config()

ALLOWED_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
JOB_TTL_SECONDS = 60 * 60  # 1h
CLEANUP_INTERVAL = 5 * 60  # varre a cada 5min

SECRET_KEY = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32).hex()
ACCESS_PASSWORD = os.environ.get("ACCESS_PASSWORD", "")
ACCESS_PASSWORD_HASH = os.environ.get("ACCESS_PASSWORD_HASH", "")
if ACCESS_PASSWORD and not ACCESS_PASSWORD_HASH:
    ACCESS_PASSWORD_HASH = generate_password_hash(ACCESS_PASSWORD)
AUTH_ENABLED = bool(ACCESS_PASSWORD_HASH)
SESSION_LIFETIME_HOURS = int(os.environ.get("SESSION_LIFETIME_HOURS", 24))

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024 * 1024  # 10GB
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=SESSION_LIFETIME_HOURS)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ==================== Auth ====================

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not AUTH_ENABLED or session.get("authenticated"):
            return f(*args, **kwargs)
        return jsonify({"error": "unauthorized"}), 401
    return wrapper


@app.post("/api/auth/login")
def login():
    pwd = (request.json or {}).get("password", "")
    if AUTH_ENABLED and check_password_hash(ACCESS_PASSWORD_HASH, pwd):
        session.permanent = True
        session["authenticated"] = True
        return jsonify({"ok": True})
    if not AUTH_ENABLED:
        return jsonify({"ok": True, "auth_disabled": True})
    return jsonify({"error": "invalid_password"}), 401


@app.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/auth/status")
def auth_status():
    return jsonify({
        "auth_enabled": AUTH_ENABLED,
        "authenticated": (not AUTH_ENABLED) or bool(session.get("authenticated")),
    })


# ==================== Jobs store ====================
# job_id -> dict(status, options, input_path, output_path, progress, log, created_at, updated_at)
jobs: dict = {}
jobs_lock = threading.Lock()


def _now():
    return time.time()


def _emit(job_id: str, event: str, payload: dict):
    socketio.emit(event, payload, room=job_id)


def _update(job_id: str, **fields):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        job.update(fields)
        job["updated_at"] = _now()
    _emit(job_id, "job_update", _public(job))


def _log(job_id: str, line: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        job["log"].append(line)
        job["updated_at"] = _now()
    print(f"[job {job_id[:8]}] {line}")
    _emit(job_id, "job_log", {"line": line})


def _public(job: dict) -> dict:
    return {
        "id": job["id"],
        "status": job["status"],
        "progress": job.get("progress", 0),
        "progress_text": job.get("progress_text", ""),
        "options": job.get("options", {}),
        "has_output": bool(job.get("output_path") and os.path.exists(job["output_path"])),
        "error": job.get("error"),
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
    }


# ==================== Pipeline ====================

def _snapshot_env() -> dict:
    """Pega snapshot das envs relevantes pra passar ao processo filho."""
    keys = ("GEMINI_API_KEY", "OPENROUTER_API_KEY", "LLM_PROVIDER",
            "LLM_MODEL", "WHISPER_COMPUTE_TYPE")
    return {k: os.environ.get(k) for k in keys if os.environ.get(k)}


def _spawn_worker(job_id: str):
    with jobs_lock:
        job = jobs[job_id]
        options = dict(job["options"])
        input_path = job["input_path"]
        job_dir = job["dir"]

    q = mp.Queue()
    env = _snapshot_env()
    p = mp.Process(
        target=_worker.run_job,
        args=(job_id, job_dir, input_path, options, env, q),
        daemon=False,
    )
    p.start()

    with jobs_lock:
        jobs[job_id]["_process"] = p
        jobs[job_id]["_queue"] = q

    threading.Thread(target=_listen_worker, args=(job_id,), daemon=True).start()


def _listen_worker(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return
    q = job["_queue"]
    p = job["_process"]

    while True:
        try:
            msg = q.get(timeout=1.0)
        except Empty:
            # Sem mensagem. Se processo morreu sem "final", tratamos como cancelled
            if not p.is_alive():
                with jobs_lock:
                    j = jobs.get(job_id)
                    if j and j["status"] not in ("done", "error", "cancelled"):
                        j["status"] = "cancelled"
                        j["progress_text"] = "Cancelado"
                        j["updated_at"] = _now()
                        _emit(job_id, "job_update", _public(j))
                        _emit(job_id, "job_log", {"line": "⛔ Processo encerrado."})
                        shutil.rmtree(j["dir"], ignore_errors=True)
                return
            continue

        t = msg.get("type")
        if t == "log":
            _log(job_id, msg.get("line", ""))
        elif t == "update":
            fields = {k: v for k, v in msg.items() if k != "type"}
            _update(job_id, **fields)
        elif t == "final":
            # Cleanup do processo
            p.join(timeout=2)
            with jobs_lock:
                j = jobs.get(job_id)
                if j:
                    j.pop("_process", None)
                    j.pop("_queue", None)
            return


# ==================== Endpoints ====================

@app.post("/api/jobs")
@login_required
def create_job():
    if "video" not in request.files:
        return jsonify({"error": "video file required"}), 400
    f = request.files["video"]
    ext = os.path.splitext(f.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({"error": f"extension {ext} not allowed"}), 400

    job_id = uuid.uuid4().hex
    job_dir = TMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    safe_name = secure_filename(f.filename) or f"input{ext}"
    input_path = str(job_dir / safe_name)
    f.save(input_path)

    # Opções via form
    def b(name, default=False):
        v = request.form.get(name)
        if v is None:
            return default
        return v.lower() in ("1", "true", "yes", "on")

    options = {
        "remove_silence": b("remove_silence", True),
        "silence_method": request.form.get("silence_method", "speech"),
        "remove_fillers": b("remove_fillers", False),
        "captions": b("captions", True),
        "model": request.form.get("model", "small"),
        "language": request.form.get("language", "pt"),
    }

    if options["remove_fillers"]:
        from llm import is_configured as _llm_ok
        if not _llm_ok():
            shutil.rmtree(job_dir, ignore_errors=True)
            return jsonify({
                "error": "LLM não configurado. Vá em Configurações e salve uma API Key (Google ou OpenRouter)."
            }), 400

    job = {
        "id": job_id,
        "dir": str(job_dir),
        "input_path": input_path,
        "output_path": None,
        "status": "queued",
        "progress": 0,
        "progress_text": "Na fila",
        "options": options,
        "log": [],
        "error": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    with jobs_lock:
        jobs[job_id] = job

    _spawn_worker(job_id)
    return jsonify(_public(job)), 201


@app.get("/api/jobs/<job_id>")
@login_required
def get_job(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    return jsonify({**_public(job), "log": job["log"][-200:]})


@app.get("/api/jobs/<job_id>/download")
@login_required
def download_job(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or not job.get("output_path") or not os.path.exists(job["output_path"]):
        return jsonify({"error": "output not ready"}), 404
    orig = os.path.basename(job["input_path"])
    base, _ = os.path.splitext(orig)
    return send_file(
        job["output_path"],
        as_attachment=True,
        download_name=f"{base}_edited.mp4",
    )


@app.post("/api/jobs/<job_id>/cancel")
@login_required
def cancel_job(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({"error": "not found"}), 404
        if job["status"] in ("done", "error", "cancelled"):
            return jsonify({"error": f"job já está em {job['status']}"}), 409
        job["status"] = "cancelling"
        job["progress_text"] = "Cancelando..."
        job["updated_at"] = _now()
        p = job.get("_process")
    _emit(job_id, "job_update", _public(job))
    _log(job_id, "⛔ Cancelando (forçado)...")

    # Força término do processo filho
    if p and p.is_alive():
        try:
            p.terminate()
            p.join(timeout=3)
            if p.is_alive():
                p.kill()
                p.join(timeout=2)
        except Exception as e:
            print(f"[cancel] erro ao terminar processo: {e}")

    with jobs_lock:
        j = jobs.get(job_id)
        if j:
            j["status"] = "cancelled"
            j["progress_text"] = "Cancelado"
            j["updated_at"] = _now()
            j.pop("_process", None)
            j.pop("_queue", None)
        shutil.rmtree(job["dir"], ignore_errors=True)

    _emit(job_id, "job_update", _public(j) if j else {"id": job_id, "status": "cancelled"})
    return jsonify({"ok": True})


@app.delete("/api/jobs/<job_id>")
@login_required
def delete_job(job_id):
    with jobs_lock:
        job = jobs.pop(job_id, None)
    if not job:
        return jsonify({"error": "not found"}), 404
    shutil.rmtree(job["dir"], ignore_errors=True)
    return jsonify({"ok": True})


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "jobs_count": len(jobs)})


def _mask(v: str) -> str:
    return (v[:4] + "…" + v[-4:]) if len(v) >= 8 else ""


@app.get("/api/settings")
@login_required
def get_settings():
    gkey = os.environ.get("GEMINI_API_KEY", "")
    okey = os.environ.get("OPENROUTER_API_KEY", "")
    provider = os.environ.get("LLM_PROVIDER", "google")
    return jsonify({
        "llm_provider": provider,
        "valid_providers": list(VALID_PROVIDERS),
        "llm_model": _current_model(),
        "llm_models": _config.get("llm_models", {}),
        "has_gemini_key": bool(gkey),
        "gemini_key_preview": _mask(gkey),
        "has_openrouter_key": bool(okey),
        "openrouter_key_preview": _mask(okey),
        "whisper_compute_type": os.environ.get("WHISPER_COMPUTE_TYPE", "int8"),
        "valid_compute_types": list(VALID_COMPUTE_TYPES),
    })


@app.post("/api/settings")
@login_required
def update_settings():
    data = request.json or {}

    if "llm_provider" in data:
        p = (data.get("llm_provider") or "google").strip()
        if p not in VALID_PROVIDERS:
            return jsonify({"error": f"provider inválido. Use: {VALID_PROVIDERS}"}), 400
        _config["llm_provider"] = p
        os.environ["LLM_PROVIDER"] = p

    if "llm_model" in data:
        m = (data.get("llm_model") or "").strip()
        if m:
            current_provider = os.environ.get("LLM_PROVIDER", "google")
            models = _config.setdefault("llm_models", {})
            models[current_provider] = m

    # Sempre re-aplica o env LLM_MODEL com base no provider atual
    _apply_model_env()

    for key_name, env_name in (("gemini_api_key", "GEMINI_API_KEY"),
                                ("openrouter_api_key", "OPENROUTER_API_KEY")):
        if key_name in data:
            v = (data.get(key_name) or "").strip()
            if v:
                _config[key_name] = v
                os.environ[env_name] = v
            else:
                _config.pop(key_name, None)
                os.environ.pop(env_name, None)

    if "whisper_compute_type" in data:
        ct = (data.get("whisper_compute_type") or "int8").strip()
        if ct not in VALID_COMPUTE_TYPES:
            return jsonify({"error": f"compute_type inválido. Use: {VALID_COMPUTE_TYPES}"}), 400
        _config["whisper_compute_type"] = ct
        os.environ["WHISPER_COMPUTE_TYPE"] = ct

    _save_config()
    return get_settings()


@socketio.on("subscribe")
def on_subscribe(data):
    job_id = (data or {}).get("job_id")
    if job_id:
        join_room(job_id)


# ==================== TTL worker ====================

def _cleanup_loop():
    while True:
        time.sleep(CLEANUP_INTERVAL)
        now = _now()
        stale = []
        with jobs_lock:
            for jid, job in list(jobs.items()):
                if now - job["updated_at"] > JOB_TTL_SECONDS:
                    stale.append(jid)
                    jobs.pop(jid, None)
        for jid in stale:
            shutil.rmtree(TMP_DIR / jid, ignore_errors=True)
            print(f"[cleanup] job {jid[:8]} removido (TTL)")


threading.Thread(target=_cleanup_loop, daemon=True).start()


# ==================== Main ====================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3001))
    print(f"🚀 API em http://localhost:{port}")
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)
