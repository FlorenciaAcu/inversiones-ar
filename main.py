"""
Backend de inversiones AR
- Local: SQLite en portfolio.db
- Railway: PostgreSQL via DATABASE_URL
- Análisis de mercado: 3 veces al día (9am, 1pm, 6pm Argentina)
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional
import httpx
import asyncio
from datetime import datetime, date
import os
from zoneinfo import ZoneInfo

try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False

# ─── DB: PostgreSQL en Railway, SQLite local ──────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "")

if DATABASE_URL:
    import psycopg2
    import psycopg2.extras

    def get_con():
        return psycopg2.connect(DATABASE_URL)

    def init_db():
        con = get_con()
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS posiciones (
                id            SERIAL PRIMARY KEY,
                nombre        TEXT    NOT NULL,
                ticker        TEXT,
                cat           TEXT,
                tna           TEXT,
                monto         FLOAT,
                cantidad      FLOAT,
                precio_compra FLOAT,
                fecha         TEXT,
                vencimiento   TEXT,
                notas         TEXT,
                creado        TEXT DEFAULT current_date
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cuentas (
                id     SERIAL PRIMARY KEY,
                label  TEXT  NOT NULL,
                amount FLOAT NOT NULL DEFAULT 0,
                orden  INT   NOT NULL DEFAULT 0
            )
        """)
        # sembrar datos iniciales solo si la tabla está vacía
        cur.execute("SELECT COUNT(*) FROM cuentas")
        if cur.fetchone()[0] == 0:
            cur.executemany(
                "INSERT INTO cuentas (label, amount, orden) VALUES (%s, %s, %s)",
                [("Ontop", 2300, 0), ("BBVA", 9400, 1), ("Efectivo", 4500, 2)]
            )
        con.commit(); con.close()

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
            CREATE TABLE IF NOT EXISTS posiciones (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre        TEXT    NOT NULL,
                ticker        TEXT,
                cat           TEXT,
                tna           TEXT,
                monto         REAL,
                cantidad      REAL,
                precio_compra REAL,
                fecha         TEXT,
                vencimiento   TEXT,
                notas         TEXT,
                creado        TEXT DEFAULT (date('now'))
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS cuentas (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                label  TEXT  NOT NULL,
                amount REAL  NOT NULL DEFAULT 0,
                orden  INTEGER NOT NULL DEFAULT 0
            )
        """)
        # sembrar datos iniciales solo si la tabla está vacía
        if con.execute("SELECT COUNT(*) FROM cuentas").fetchone()[0] == 0:
            con.executemany(
                "INSERT INTO cuentas (label, amount, orden) VALUES (?,?,?)",
                [("Ontop", 2300, 0), ("BBVA", 9400, 1), ("Efectivo", 4500, 2)]
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

init_db()

# ─── APP ─────────────────────────────────────────────────────
app = FastAPI(title="Inversiones AR")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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

async def fetch_tasas():
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get("https://api.argentinadatos.com/v1/finanzas/tasas/plazoFijo")
            data = []
            for b in r.json():
                v = b.get("tnaClientes", 0)
                if v and v > 0:
                    tna = round(v * 100, 2) if v < 1 else round(v, 2)
                    data.append({**b, "tnaClientes": tna})
            data.sort(key=lambda x: x["tnaClientes"], reverse=True)
            return {
                "mejor_tna":   data[0]["tnaClientes"] if data else 0,
                "mejor_banco": data[0]["entidad"]     if data else "—",
                "ranking":     data[:8],
            }
    except Exception as e:
        return {"error": str(e), "mejor_tna": 0, "mejor_banco": "—", "ranking": []}

async def fetch_bcra():
    result = {}
    try:
        async with httpx.AsyncClient(timeout=10, verify=False) as c:
            r = await c.get(
                "https://api.bcra.gob.ar/estadisticas/v3.0/principalesvariables",
                headers={"Accept": "application/json"},
            )
            if r.status_code == 200:
                vars_map = {1:"reservas", 7:"tasa_politica", 27:"ipc_mensual",
                            28:"ipc_anual", 29:"ipc_acum", 40:"uva"}
                for v in r.json().get("results", []):
                    key = vars_map.get(v.get("idVariable"))
                    if key:
                        result[key] = {"valor": v.get("valor"), "fecha": v.get("fecha")}
    except:
        pass
    return result

async def fetch_fci():
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r1, r2 = await asyncio.gather(
                c.get("https://api.argentinadatos.com/v1/finanzas/fci/rentaFija/ultimo"),
                c.get("https://api.argentinadatos.com/v1/finanzas/fci/rentaVariable/ultimo"),
            )
            return {
                "renta_fija":     r1.json()[:8] if r1.status_code == 200 else [],
                "renta_variable": r2.json()[:8] if r2.status_code == 200 else [],
            }
    except:
        return {"renta_fija": [], "renta_variable": []}

CEDEAR_TICKERS = {
    "SPY.BA":   "CEDEAR SPY — S&P 500",
    "QQQ.BA":   "CEDEAR QQQ — Nasdaq 100",
    "AAPL.BA":  "CEDEAR AAPL — Apple",
    "MSFT.BA":  "CEDEAR MSFT — Microsoft",
    "NVDA.BA":  "CEDEAR NVDA — NVIDIA",
    "AMZN.BA":  "CEDEAR AMZN — Amazon",
    "GOOGL.BA": "CEDEAR GOOGL — Alphabet",
    "BRK-B.BA": "CEDEAR BRK.B — Berkshire",
    "MELI.BA":  "CEDEAR MELI — MercadoLibre",
    "TSLA.BA":  "CEDEAR TSLA — Tesla",
    "AL30.BA":  "Bono AL30",
    "AL35.BA":  "Bono AL35",
    "GD30.BA":  "Bono GD30",
    "GD35.BA":  "Bono GD35",
    "TX26.BA":  "Bono CER TX26",
    "GGAL.BA":  "Galicia (GGAL)",
    "YPF.BA":   "YPF",
    "BBAR.BA":  "Banco BBVA Argentina",
    "PAMP.BA":  "Pampa Energia",
}

async def fetch_byma_async():
    """Precios BYMA via Yahoo Finance API directamente con httpx (funciona en cloud)."""
    YF_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "es-AR,es;q=0.9",
    }
    result = {}

    async def fetch_one(ticker, nombre):
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
            async with httpx.AsyncClient(timeout=12, headers=YF_HEADERS, follow_redirects=True) as c:
                r = await c.get(url)
                if r.status_code != 200:
                    raise ValueError(f"HTTP {r.status_code}")
                data   = r.json()
                quotes = data["chart"]["result"][0]["indicators"]["quote"][0]
                closes = [x for x in (quotes.get("close") or []) if x is not None]
                if not closes:
                    raise ValueError("sin datos")
                precio = closes[-1]
                prev   = closes[-2] if len(closes) > 1 else precio
                var    = round((precio - prev) / prev * 100, 2) if prev else 0
                return ticker, {"nombre": nombre, "precio": round(precio, 2), "variacion": var, "moneda": "ARS"}
        except Exception as e:
            return ticker, {"nombre": nombre, "precio": None, "variacion": None, "_err": str(e)}

    tasks = [fetch_one(t, n) for t, n in CEDEAR_TICKERS.items()]
    for ticker, data in await asyncio.gather(*tasks):
        result[ticker] = data
    return result

# ─── CACHÉ DE MERCADO (se actualiza 3x/día) ──────────────────
ARG = ZoneInfo("America/Argentina/Buenos_Aires")
_cache = {"data": None, "actualizado": None, "turno": None}

async def _refresh_market():
    """Refresca el caché con datos frescos del mercado."""
    dolar, tasas, bcra, fci = await asyncio.gather(
        fetch_dolar(), fetch_tasas(), fetch_bcra(), fetch_fci()
    )
    byma = await fetch_byma_async()
    ahora = datetime.now(ARG)
    hora  = ahora.hour
    turno = "Análisis de la mañana" if hora < 12 else "Análisis del mediodía" if hora < 17 else "Análisis de la tarde"
    _cache["data"] = {"dolar": dolar, "tasas": tasas, "bcra": bcra, "fci": fci, "byma": byma}
    _cache["actualizado"] = ahora.strftime("%d/%m · %H:%Mhs")
    _cache["turno"] = turno
    print(f"[{_cache['actualizado']}] Mercado actualizado — {turno}")

async def _scheduler():
    """Corre cada minuto y dispara el refresh a las 9, 13 y 18hs Argentina."""
    HORAS = {9, 13, 18}
    ultimo = -1
    while True:
        ahora = datetime.now(ARG)
        if ahora.hour in HORAS and ahora.hour != ultimo:
            ultimo = ahora.hour
            await _refresh_market()
        await asyncio.sleep(60)

@app.on_event("startup")
async def startup():
    # Primer refresh inmediato al arrancar
    await _refresh_market()
    # Lanzar el scheduler en background
    asyncio.create_task(_scheduler())

# ─── ENDPOINTS ────────────────────────────────────────────────
@app.get("/api/market")
async def market():
    # Si por alguna razón el caché está vacío, refrescar ahora
    if not _cache["data"]:
        await _refresh_market()
    return {
        **_cache["data"],
        "timestamp":   datetime.now(ARG).isoformat(),
        "actualizado": _cache["actualizado"],
        "turno":       _cache["turno"],
    }

class Posicion(BaseModel):
    nombre:        str
    ticker:        Optional[str]  = None
    cat:           Optional[str]  = None
    tna:           Optional[str]  = None
    monto:         float
    cantidad:      Optional[float] = None
    precio_compra: Optional[float] = None
    fecha:         Optional[str]  = None
    vencimiento:   Optional[str]  = None
    notas:         Optional[str]  = None

@app.get("/api/portfolio")
def get_portfolio():
    return db_rows("SELECT * FROM posiciones ORDER BY fecha DESC")

@app.post("/api/portfolio")
def add_posicion(p: Posicion):
    if DATABASE_URL:
        sql = """INSERT INTO posiciones
                 (nombre,ticker,cat,tna,monto,cantidad,precio_compra,fecha,vencimiento,notas)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id"""
    else:
        sql = """INSERT INTO posiciones
                 (nombre,ticker,cat,tna,monto,cantidad,precio_compra,fecha,vencimiento,notas)
                 VALUES (?,?,?,?,?,?,?,?,?,?)"""
    pid = db_exec(sql, (p.nombre, p.ticker, p.cat, p.tna, p.monto, p.cantidad,
                        p.precio_compra, p.fecha or date.today().isoformat(),
                        p.vencimiento, p.notas))
    return {"id": pid, **p.dict()}

@app.delete("/api/portfolio/{pid}")
def del_posicion(pid: int):
    if DATABASE_URL:
        db_exec("DELETE FROM posiciones WHERE id=%s", (pid,))
    else:
        db_exec("DELETE FROM posiciones WHERE id=?", (pid,))
    return {"ok": True}

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

@app.get("/api/context")
async def context():
    mkt  = await market()
    port = get_portfolio()
    d    = mkt["dolar"]
    t    = mkt["tasas"]
    bcra = mkt["bcra"]

    lines = [f"DATOS DE MERCADO - {datetime.now().strftime('%d/%m/%Y %H:%M')}", ""]
    lines.append(f"DOLAR: MEP ${d.get('mep',0):,.0f} | Blue ${d.get('blue',0):,.0f} | CCL ${d.get('ccl',0):,.0f}")
    lines.append(f"PLAZO FIJO: {t['mejor_tna']}% TNA en {t['mejor_banco']}")
    if bcra.get("ipc_mensual"):
        lines.append(f"INFLACION: {bcra['ipc_mensual']['valor']}% mensual")
    if bcra.get("uva"):
        lines.append(f"UVA: ${bcra['uva']['valor']}")

    lines.append("\nPRECIOS BYMA:")
    for tk, v in mkt["byma"].items():
        if not tk.startswith("_") and v.get("precio"):
            sign = "+" if (v["variacion"] or 0) >= 0 else ""
            lines.append(f"  {tk}: ${v['precio']:,.0f} ({sign}{v['variacion']}%)")

    total = sum(p["monto"] for p in port)
    tc    = d.get("mep") or 1
    lines.append(f"\nPORTAFOLIO: ${total:,.0f} ARS = USD {total/tc:,.0f} al MEP")
    for p in port:
        line = f"  - {p['nombre']}: ${p['monto']:,.0f}"
        if p.get("vencimiento"): line += f" | vence {p['vencimiento']}"
        if p.get("notas"):       line += f" | {p['notas']}"
        lines.append(line)

    lines += ["", "Contexto: inversora argentina, horizonte 12 meses, objetivo crecer pesos en USD, plataforma PPI.",
              "Que me recomendas hacer?"]
    return {"context": "\n".join(lines)}

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
