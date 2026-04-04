"""Flask dashboard server for Lead Hunter."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file, stream_with_context

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
EXPORTS_DIR = BASE_DIR / "exports"
CHECKPOINT_PATH = DATA_DIR / "checkpoint.json"
LEADS_PATH = DATA_DIR / "latest_qualified_leads.json"
CRM_PATH = DATA_DIR / "crm.json"
LOG_PATH = LOGS_DIR / "lead_hunter.log"

CRM_STATUSES = {
    "novo":        "Não Abordado",
    "enviado":     "Mensagem Enviada",
    "respondeu":   "Respondeu",
    "negociando":  "Negociando",
    "fechado":     "Fechado ✓",
    "descartado":  "Descartado",
}

EXPORT_WHITELIST = {"qualified_leads.csv", "qualified_leads.json", "qualified_leads.html"}

# Vercel serverless environment detection
IS_VERCEL = os.environ.get("VERCEL") == "1"

LEAD_TABLE_FIELDS = {
    "place_id", "status", "status_display", "score", "name", "category",
    "neighborhood", "city", "phone", "instagram_username", "link_type",
    "link_type_label", "followers_count", "engagement_rate", "google_reviews",
    "google_rating", "last_post_days", "key_strengths", "whatsapp_message",
    "whatsapp_followup", "instagram_dm", "subject_email", "approach_angle",
    "collected_at", "maps_url", "website", "is_new", "run_count", "first_seen_at",
}

app = Flask(__name__, template_folder="templates", static_folder="static")

_run_process: subprocess.Popen | None = None
_run_lock = threading.Lock()


# ── CRM helpers ───────────────────────────────────────────────────────────────

def _load_crm() -> dict:
    """Load CRM data from disk. Returns {place_id: crm_entry}."""
    if IS_VERCEL:
        return {}
    try:
        return json.loads(CRM_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_crm(crm: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CRM_PATH.write_text(json.dumps(crm, ensure_ascii=False, indent=2), encoding="utf-8")


def _crm_entry_for(place_id: str, crm: dict) -> dict:
    return crm.get(place_id, {
        "status": "novo",
        "note": "",
        "history": [],
        "contacted_at": None,
        "updated_at": None,
    })


# ── Data helpers ───────────────────────────────────────────────────────────────

def _safe_int(val) -> int | None:
    try:
        return int(val) if val not in (None, "", "—") else None
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> float | None:
    try:
        return float(val) if val not in (None, "", "—") else None
    except (ValueError, TypeError):
        return None


def _sheets_row_to_lead(row: dict) -> dict:
    """Convert a Google Sheets row back to the lead dict format."""
    raw_status = str(row.get("🌡️ Status", ""))
    status = raw_status.replace("🔥", "").replace("✓", "").strip()
    strengths_raw = str(row.get("Pontos Fortes", ""))
    strengths = [s.strip() for s in strengths_raw.split("|") if s.strip()]
    return {
        "place_id": row.get("place_id", ""),
        "status": status,
        "status_display": raw_status,
        "score": _safe_int(row.get("Score")),
        "name": row.get("Nome do Restaurante", ""),
        "category": row.get("Categoria", ""),
        "neighborhood": row.get("Bairro", ""),
        "city": row.get("Cidade", ""),
        "phone": row.get("Telefone", ""),
        "instagram_username": str(row.get("Instagram", "")).lstrip("@"),
        "link_type_label": row.get("Tipo de link atual", ""),
        "followers_count": _safe_int(row.get("Seguidores Instagram")),
        "engagement_rate": _safe_float(row.get("Taxa de Engajamento (%)")),
        "google_reviews": _safe_int(row.get("Avaliações Google")),
        "google_rating": _safe_float(row.get("Rating Google")),
        "last_post_days": _safe_int(row.get("Último post (dias atrás)")),
        "key_strengths": strengths,
        "whatsapp_message": row.get("Mensagem WhatsApp", ""),
        "whatsapp_followup": "",
        "instagram_dm": row.get("Mensagem Instagram DM", ""),
        "collected_at": row.get("Data de coleta", ""),
        "maps_url": "",
        "website": "",
        "is_new": None,
        "run_count": None,
        "first_seen_at": None,
    }


def _read_leads_from_sheets() -> list:
    """Read leads from Google Sheets (used on Vercel)."""
    sys.path.insert(0, str(BASE_DIR))
    from lead_hunter.sheets_exporter import _authorize_gspread
    from lead_hunter import config
    gc = _authorize_gspread()
    sh = gc.open_by_key(config.GOOGLE_SHEETS_ID)
    sheets = [ws for ws in sh.worksheets() if ws.title.startswith("Leads ")]
    if not sheets:
        return []
    ws = sheets[-1]
    rows = ws.get_all_records()
    return [_sheets_row_to_lead(r) for r in rows if str(r.get("🌡️ Status", "")).strip()]


def _read_checkpoint() -> dict:
    if IS_VERCEL:
        return {}
    try:
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _read_leads() -> list:
    if IS_VERCEL:
        try:
            return _read_leads_from_sheets()
        except Exception:
            return []
    try:
        return json.loads(LEADS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _strip_lead(lead: dict) -> dict:
    """Remove heavy nested blobs to keep the JSON payload small."""
    return {k: v for k, v in lead.items() if k in LEAD_TABLE_FIELDS}


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/api/config/targets")
def api_config_targets():
    sys.path.insert(0, str(BASE_DIR))
    from lead_hunter import config as lh_config  # noqa: PLC0415
    return jsonify({
        "cities": lh_config.TARGET_CITIES,
        "categories": lh_config.TARGET_CATEGORIES,
    })


@app.route("/")
def index():
    return render_template("index.html", is_vercel=IS_VERCEL)


@app.route("/api/stats")
def api_stats():
    if IS_VERCEL:
        try:
            leads = _read_leads_from_sheets()
            hot  = sum(1 for l in leads if l.get("status") == "HOT")
            warm = sum(1 for l in leads if l.get("status") == "WARM")
            return jsonify({
                "found": len(leads), "processed": len(leads),
                "qualified": len(leads), "hot": hot, "warm": warm,
                "errors": 0, "apify_calls": 0, "is_running": False,
            })
        except Exception:
            return jsonify({"found": 0, "processed": 0, "qualified": 0,
                            "hot": 0, "warm": 0, "errors": 0, "is_running": False})

    data = _read_checkpoint()
    stats = dict(data.get("stats", {}))
    stats["apify_calls"] = data.get("apify_calls_used", 0)
    with _run_lock:
        stats["is_running"] = _run_process is not None and _run_process.poll() is None
    return jsonify(stats)


@app.route("/api/leads")
def api_leads():
    leads = _read_leads()
    crm = _load_crm()
    status_filter = request.args.get("status", "").upper()
    query = request.args.get("q", "").lower()
    crm_filter = request.args.get("crm", "").lower()

    result = []
    for lead in leads:
        if status_filter and lead.get("status", "") != status_filter:
            continue
        if query:
            searchable = " ".join(filter(None, [
                lead.get("name", ""),
                lead.get("neighborhood", ""),
                lead.get("city", ""),
                lead.get("category", ""),
                lead.get("instagram_username", ""),
            ])).lower()
            if query not in searchable:
                continue
        stripped = _strip_lead(lead)
        # Merge CRM state into every lead
        pid = lead.get("place_id", "")
        crm_entry = _crm_entry_for(pid, crm)
        stripped["crm_status"] = crm_entry.get("status", "novo")
        stripped["crm_note"]   = crm_entry.get("note", "")
        stripped["crm_history"] = crm_entry.get("history", [])
        stripped["contacted_at"] = crm_entry.get("contacted_at")
        if crm_filter and stripped["crm_status"] != crm_filter:
            continue
        result.append(stripped)

    return jsonify(result)


@app.route("/api/crm/<place_id>", methods=["PATCH"])
def api_crm_update(place_id: str):
    if IS_VERCEL:
        return jsonify({"error": "CRM disponível apenas no dashboard local."}), 503
    body = request.get_json(silent=True) or {}
    new_status = body.get("status", "").lower()
    new_note   = body.get("note")
    if new_status and new_status not in CRM_STATUSES:
        return jsonify({"error": f"Status inválido. Opções: {list(CRM_STATUSES.keys())}"}), 400

    crm = _load_crm()
    entry = _crm_entry_for(place_id, crm)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")

    if new_status and new_status != entry.get("status"):
        old_status = entry.get("status", "novo")
        entry["history"].append({
            "at": now,
            "from": old_status,
            "to": new_status,
            "note": new_note or "",
        })
        entry["status"] = new_status
        if new_status == "enviado" and not entry.get("contacted_at"):
            entry["contacted_at"] = now

    if new_note is not None:
        entry["note"] = new_note

    entry["updated_at"] = now
    crm[place_id] = entry
    _save_crm(crm)
    return jsonify({"ok": True, "entry": entry})


@app.route("/api/crm/stats")
def api_crm_stats():
    if IS_VERCEL:
        return jsonify({s: 0 for s in CRM_STATUSES})
    crm = _load_crm()
    counts = {s: 0 for s in CRM_STATUSES}
    for entry in crm.values():
        s = entry.get("status", "novo")
        if s in counts:
            counts[s] += 1
    return jsonify(counts)


@app.route("/api/stream-logs")
def api_stream_logs():
    if IS_VERCEL:
        def static_msg():
            yield "data: [Lead Hunter] Pipeline roda localmente. Acesse o dashboard local para ver logs ao vivo.\n\n"
            while True:
                time.sleep(30)
                yield ": keepalive\n\n"
        return Response(stream_with_context(static_msg()), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    def generate():
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not LOG_PATH.exists():
            LOG_PATH.write_text("", encoding="utf-8")
        with LOG_PATH.open("r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            for line in all_lines[-80:]:
                text = line.rstrip()
                if text:
                    yield f"data: {text}\n\n"
            keepalive_counter = 0
            while True:
                line = f.readline()
                if line:
                    text = line.rstrip()
                    if text:
                        yield f"data: {text}\n\n"
                    keepalive_counter = 0
                else:
                    time.sleep(0.3)
                    keepalive_counter += 1
                    if keepalive_counter >= 50:
                        yield ": keepalive\n\n"
                        keepalive_counter = 0

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.route("/api/run/start", methods=["POST"])
def api_run_start():
    if IS_VERCEL:
        return jsonify({"error": "Pipeline roda localmente. Use o dashboard local para iniciar buscas.", "local_only": True}), 503

    global _run_process
    with _run_lock:
        if _run_process is not None and _run_process.poll() is None:
            return jsonify({"error": "Pipeline já está rodando"}), 409

        body = request.get_json(silent=True) or {}
        cmd = [sys.executable, str(BASE_DIR / "main.py")]

        max_apify = body.get("max_apify_calls")
        if max_apify and int(max_apify) > 0:
            cmd += ["--max-apify-calls", str(int(max_apify))]

        selected_cities = body.get("selected_cities")
        selected_categories = body.get("selected_categories")

        if selected_cities and isinstance(selected_cities, list) and len(selected_cities) > 0:
            cmd += ["--cities", "|".join(str(c) for c in selected_cities)]
        else:
            limit_cities = body.get("limit_cities")
            if limit_cities and int(limit_cities) > 0:
                cmd += ["--limit-cities", str(int(limit_cities))]

        if selected_categories and isinstance(selected_categories, list) and len(selected_categories) > 0:
            cmd += ["--categories", "|".join(str(c) for c in selected_categories)]
        else:
            limit_cats = body.get("limit_categories")
            if limit_cats and int(limit_cats) > 0:
                cmd += ["--limit-categories", str(int(limit_cats))]

        if body.get("skip_sheets"):
            cmd += ["--skip-sheets"]
        if body.get("skip_email"):
            cmd += ["--skip-email"]

        _run_process = subprocess.Popen(
            cmd, cwd=str(BASE_DIR),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    return jsonify({"started": True, "pid": _run_process.pid})


@app.route("/api/run/stop", methods=["POST"])
def api_run_stop():
    if IS_VERCEL:
        return jsonify({"error": "Pipeline roda localmente.", "local_only": True}), 503

    global _run_process
    with _run_lock:
        if _run_process is not None and _run_process.poll() is None:
            _run_process.terminate()
            try:
                _run_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _run_process.kill()
        _run_process = None
    return jsonify({"stopped": True})


@app.route("/api/exports/<filename>")
def api_export(filename: str):
    if filename not in EXPORT_WHITELIST:
        return jsonify({"error": "Arquivo não permitido"}), 403
    if IS_VERCEL:
        return jsonify({"error": "Downloads disponíveis apenas no dashboard local."}), 503
    path = EXPORTS_DIR / filename
    if not path.exists():
        return jsonify({"error": "Arquivo não encontrado. Execute o pipeline primeiro."}), 404
    return send_file(path, as_attachment=True)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("  LEAD HUNTER Dashboard")
    print("  http://127.0.0.1:5000")
    print("=" * 50)
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
