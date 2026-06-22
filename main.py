"""
Backend de inversiones AR
- Local: SQLite en portfolio.db
- Railway: PostgreSQL via DATABASE_URL
- Análisis de mercado: 3 veces al día (9am, 1pm, 6pm Argentina)
"""
from fastapi import FastAPI, HTTPException, Request, Form, Cookie
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from typing import Optional
import httpx
import asyncio
import hashlib, hmac as _hmac
from datetime import datetime, date
import os
from zoneinfo import ZoneInfo

# ─── DB: PostgreSQL en Railway, SQLite local ──────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "")
# Railway entrega postgres:// pero psycopg2 necesita postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL:
    import psycopg2
    import psycopg2.extras

    def get_con():
        return psycopg2.connect(DATABASE_URL)

    def init_db():
        print("[DB] Conectando a PostgreSQL...")
        con = get_con()
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cuentas (
                id     SERIAL PRIMARY KEY,
                label  TEXT  NOT NULL,
                amount FLOAT NOT NULL DEFAULT 0,
                orden  INT   NOT NULL DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS plan_mensual (
                id           SERIAL PRIMARY KEY,
                mes          TEXT  NOT NULL,
                monto        FLOAT NOT NULL DEFAULT 190000,
                instrumento  TEXT  NOT NULL,
                plataforma   TEXT  NOT NULL,
                tasa_mensual FLOAT NOT NULL DEFAULT 0.03
            )
        """)
        # seed cuentas
        cur.execute("SELECT COUNT(*) FROM cuentas")
        if cur.fetchone()[0] == 0:
            cur.executemany(
                "INSERT INTO cuentas (label, amount, orden) VALUES (%s,%s,%s)",
                [("Ontop", 2300, 0), ("BBVA", 9400, 1), ("Efectivo", 4500, 2)]
            )
            print("[DB] Seed cuentas OK")
        # seed plan 12 meses
        cur.execute("SELECT COUNT(*) FROM plan_mensual")
        if cur.fetchone()[0] == 0:
            from datetime import date
            hoy = date.today()
            propuesta = [
                ("Fondo Conservador MP", "Mercado Pago", 0.030),
                ("Empresas Argentinas MP", "Mercado Pago", 0.035),
                ("Lecap PPI",             "PPI",          0.035),
                ("Fondo Conservador MP",  "Mercado Pago", 0.030),
                ("Boncap PPI",            "PPI",          0.037),
                ("Empresas Argentinas MP","Mercado Pago", 0.035),
                ("Lecap PPI",             "PPI",          0.035),
                ("Fondo Conservador MP",  "Mercado Pago", 0.030),
                ("Boncap PPI",            "PPI",          0.037),
                ("Empresas Argentinas MP","Mercado Pago", 0.035),
                ("Lecap PPI",             "PPI",          0.035),
                ("Fondo Conservador MP",  "Mercado Pago", 0.030),
            ]
            for i, (inst, plat, tasa) in enumerate(propuesta):
                m = hoy.month + i
                y = hoy.year + (m - 1) // 12
                m = ((m - 1) % 12) + 1
                cur.execute(
                    "INSERT INTO plan_mensual (mes, monto, instrumento, plataforma, tasa_mensual) VALUES (%s,%s,%s,%s,%s)",
                    (f"{y}-{m:02d}", 190000, inst, plat, tasa)
                )
            print("[DB] Seed plan_mensual OK")
        con.commit(); con.close()
        print("[DB] init_db OK")

    def db_rows(sql, params=()):
        con = get_con()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        rows = cur.fetchall()
        con.close()
        return [dict(r) for r in rows]

    def db_exec(sql, params=()):
        con = get_con()
        cur = con.cursor()
        cur.execute(sql, params)
        con.commit()
        lid = cur.fetchone()[0] if cur.description else None
        con.close()
        return lid

else:
    import sqlite3
    BASE = os.path.dirname(os.path.abspath(__file__))
    DB   = os.path.join(BASE, "portfolio.db")

    def init_db():
        con = sqlite3.connect(DB)
        con.execute("""
            CREATE TABLE IF NOT EXISTS cuentas (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                label  TEXT  NOT NULL,
                amount REAL  NOT NULL DEFAULT 0,
                orden  INTEGER NOT NULL DEFAULT 0
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS plan_mensual (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                mes          TEXT  NOT NULL,
                monto        REAL  NOT NULL DEFAULT 190000,
                instrumento  TEXT  NOT NULL,
                plataforma   TEXT  NOT NULL,
                tasa_mensual REAL  NOT NULL DEFAULT 0.03
            )
        """)
        if con.execute("SELECT COUNT(*) FROM cuentas").fetchone()[0] == 0:
            con.executemany(
                "INSERT INTO cuentas (label, amount, orden) VALUES (?,?,?)",
                [("Ontop", 2300, 0), ("BBVA", 9400, 1), ("Efectivo", 4500, 2)]
            )
        if con.execute("SELECT COUNT(*) FROM plan_mensual").fetchone()[0] == 0:
            from datetime import date
            hoy = date.today()
            propuesta = [
                ("Fondo Conservador MP", "Mercado Pago", 0.030),
                ("Empresas Argentinas MP","Mercado Pago", 0.035),
                ("Lecap PPI",            "PPI",          0.035),
                ("Fondo Conservador MP", "Mercado Pago", 0.030),
                ("Boncap PPI",           "PPI",          0.037),
                ("Empresas Argentinas MP","Mercado Pago",0.035),
                ("Lecap PPI",            "PPI",          0.035),
                ("Fondo Conservador MP", "Mercado Pago", 0.030),
                ("Boncap PPI",           "PPI",          0.037),
                ("Empresas Argentinas MP","Mercado Pago",0.035),
                ("Lecap PPI",            "PPI",          0.035),
                ("Fondo Conservador MP", "Mercado Pago", 0.030),
            ]
            for i, (inst, plat, tasa) in enumerate(propuesta):
                m = hoy.month + i
                y = hoy.year + (m - 1) // 12
                m = ((m - 1) % 12) + 1
                con.execute(
                    "INSERT INTO plan_mensual (mes, monto, instrumento, plataforma, tasa_mensual) VALUES (?,?,?,?,?)",
                    (f"{y}-{m:02d}", 190000, inst, plat, tasa)
                )
        con.commit(); con.close()

    def db_rows(sql, params=()):
        con = sqlite3.connect(DB)
        con.row_factory = sqlite3.Row
        rows = con.execute(sql, params).fetchall()
        con.close()
        return [dict(r) for r in rows]

    def db_exec(sql, params=()):
        con = sqlite3.connect(DB)
        cur = con.execute(sql, params)
        con.commit()
        lid = cur.lastrowid
        con.close()
        return lid

try:
    init_db()
except Exception as e:
    print(f"[DB] ERROR en init_db: {e}")
    import traceback; traceback.print_exc()

# ─── AUTH ────────────────────────────────────────────────────
_GTG_PASSWORD = os.environ.get("GTG_PASSWORD", "changeme")
_GTG_SECRET   = os.environ.get("GTG_SECRET",   "gtg-secret-2024")
# Token de sesión: HMAC(secret, password) — cambia si alguno cambia
SESSION_TOKEN = _hmac.new(
    _GTG_SECRET.encode(), _GTG_PASSWORD.encode(), hashlib.sha256
).hexdigest()

if _GTG_PASSWORD == "changeme":
    print("[AUTH] ⚠ Usando contraseña por defecto. Seteá GTG_PASSWORD en las variables de entorno.")

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Rutas públicas: login y archivos estáticos
        if path.startswith("/login") or path.startswith("/static") or path == "/favicon.ico":
            return await call_next(request)
        # Verificar cookie de sesión
        token = request.cookies.get("gtg_session", "")
        if not _hmac.compare_digest(token, SESSION_TOKEN):
            if path.startswith("/api"):
                return JSONResponse({"error": "no autorizado"}, status_code=401)
            return RedirectResponse("/login")
        return await call_next(request)

# ─── APP ─────────────────────────────────────────────────────
app = FastAPI(title="Good Things Go")
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir archivos estáticos (CSS, JS)
_static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# ─── FETCH MERCADO ────────────────────────────────────────────
async def fetch_dolar():
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get("https://dolarapi.com/v1/dolares")
            m = {d["casa"]: d for d in r.json()}
            return {
                "mep":     m.get("bolsa",           {}).get("venta", 0),
                "blue":    m.get("blue",             {}).get("venta", 0),
                "ccl":     m.get("contadoconliqui",  {}).get("venta", 0),
                "oficial": m.get("oficial",          {}).get("venta", 0),
                "cripto":  m.get("cripto",           {}).get("venta", 0),
                "compras": {k: v.get("compra", 0) for k, v in m.items()},
            }
    except Exception as e:
        return {"error": str(e), "mep": 0, "blue": 0, "ccl": 0, "oficial": 0}

# ─── CACHÉ DEL DÓLAR (TTL 30 min) ─────────────────────────────
ARG = ZoneInfo("America/Argentina/Buenos_Aires")
_cache = {"dolar": None, "ts": None}
_CACHE_TTL = 30 * 60  # segundos

async def get_dolar_cached():
    """Devuelve el dólar cacheado; lo refresca si pasaron más de 30 min."""
    ahora = datetime.now(ARG)
    if _cache["dolar"] and _cache["ts"] and (ahora - _cache["ts"]).total_seconds() < _CACHE_TTL:
        return _cache["dolar"]
    dolar = await fetch_dolar()
    if not dolar.get("error"):
        _cache["dolar"] = dolar
        _cache["ts"] = ahora
    return _cache["dolar"] or dolar

# ─── ENDPOINTS ────────────────────────────────────────────────
@app.get("/api/market")
async def market():
    return {
        "dolar":     await get_dolar_cached(),
        "timestamp": datetime.now(ARG).isoformat(),
    }

class Cuenta(BaseModel):
    label:  str
    amount: float
    orden:  Optional[int] = 0

@app.get("/api/cuentas")
def get_cuentas():
    return db_rows("SELECT * FROM cuentas ORDER BY orden, id")

@app.post("/api/cuentas")
def add_cuenta(c: Cuenta):
    if DATABASE_URL:
        cid = db_exec(
            "INSERT INTO cuentas (label, amount, orden) VALUES (%s,%s,%s) RETURNING id",
            (c.label, c.amount, c.orden)
        )
    else:
        cid = db_exec(
            "INSERT INTO cuentas (label, amount, orden) VALUES (?,?,?)",
            (c.label, c.amount, c.orden)
        )
    return {"id": cid, **c.dict()}

@app.put("/api/cuentas/{cid}")
def update_cuenta(cid: int, c: Cuenta):
    if DATABASE_URL:
        db_exec("UPDATE cuentas SET label=%s, amount=%s WHERE id=%s", (c.label, c.amount, cid))
    else:
        db_exec("UPDATE cuentas SET label=?, amount=? WHERE id=?", (c.label, c.amount, cid))
    return {"id": cid, **c.dict()}

@app.delete("/api/cuentas/{cid}")
def del_cuenta(cid: int):
    if DATABASE_URL:
        db_exec("DELETE FROM cuentas WHERE id=%s", (cid,))
    else:
        db_exec("DELETE FROM cuentas WHERE id=?", (cid,))
    return {"ok": True}

class PlanMes(BaseModel):
    mes:          Optional[str] = None
    monto:        float
    instrumento:  str
    plataforma:   str
    tasa_mensual: float

@app.get("/api/plan")
def get_plan():
    return db_rows("SELECT * FROM plan_mensual ORDER BY mes")

@app.put("/api/plan/{pid}")
def update_plan(pid: int, p: PlanMes):
    if DATABASE_URL:
        db_exec(
            "UPDATE plan_mensual SET monto=%s, instrumento=%s, plataforma=%s, tasa_mensual=%s WHERE id=%s",
            (p.monto, p.instrumento, p.plataforma, p.tasa_mensual, pid)
        )
    else:
        db_exec(
            "UPDATE plan_mensual SET monto=?, instrumento=?, plataforma=?, tasa_mensual=? WHERE id=?",
            (p.monto, p.instrumento, p.plataforma, p.tasa_mensual, pid)
        )
    return {"id": pid, **p.dict()}

@app.post("/api/plan")
def add_plan_mes(p: PlanMes):
    if DATABASE_URL:
        pid = db_exec(
            "INSERT INTO plan_mensual (mes, monto, instrumento, plataforma, tasa_mensual) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (p.mes if hasattr(p,'mes') else '', p.monto, p.instrumento, p.plataforma, p.tasa_mensual)
        )
    else:
        pid = db_exec(
            "INSERT INTO plan_mensual (mes, monto, instrumento, plataforma, tasa_mensual) VALUES (?,?,?,?,?)",
            (p.mes if hasattr(p,'mes') else '', p.monto, p.instrumento, p.plataforma, p.tasa_mensual)
        )
    return {"id": pid, **p.dict()}

@app.delete("/api/plan/{pid}")
def delete_plan_mes(pid: int):
    if DATABASE_URL:
        db_exec("DELETE FROM plan_mensual WHERE id=%s", (pid,))
    else:
        db_exec("DELETE FROM plan_mensual WHERE id=?", (pid,))
    return {"ok": True}

@app.get("/api/debug")
def debug():
    try:
        c = db_rows("SELECT COUNT(*) as n FROM cuentas")[0]["n"]
        p = db_rows("SELECT COUNT(*) as n FROM plan_mensual")[0]["n"]
        return {"ok": True, "cuentas": c, "plan_mensual": p,
                "db": "postgresql" if DATABASE_URL else "sqlite"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ─── LOGIN / LOGOUT ───────────────────────────────────────────
@app.get("/login")
def login_page():
    base = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(base, "login.html")
    return FileResponse(p) if os.path.exists(p) else HTMLResponse("<h2>login.html no encontrado</h2>", 404)

@app.post("/login")
def do_login(password: str = Form(...)):
    if _hmac.compare_digest(password, _GTG_PASSWORD):
        resp = RedirectResponse("/", status_code=302)
        resp.set_cookie(
            "gtg_session", SESSION_TOKEN,
            httponly=True, samesite="lax",
            max_age=60 * 60 * 24 * 30   # 30 días
        )
        return resp
    return RedirectResponse("/login?err=1", status_code=302)

@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("gtg_session")
    return resp

# ─── SERVE HTML ───────────────────────────────────────────────
@app.get("/")
def serve_html():
    # buscar inversiones.html junto al main.py o un nivel arriba
    for path in [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "inversiones.html"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "inversiones.html"),
    ]:
        if os.path.exists(os.path.abspath(path)):
            return FileResponse(os.path.abspath(path))
    return HTMLResponse("<h2>inversiones.html no encontrado</h2>", status_code=404)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"Backend en http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
