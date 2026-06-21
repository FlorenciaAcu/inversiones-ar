'use strict';

const API = (window.location.protocol === 'file:' || window.location.origin === 'null')
  ? 'http://localhost:8000'
  : window.location.origin;

/* ══════════════════════════════
   NAVEGACIÓN POR PESTAÑAS
══════════════════════════════ */
function go(t) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => {
    b.classList.remove('active');
    if (b.getAttribute('onclick').includes("'" + t + "'")) b.classList.add('active');
  });
  document.getElementById('tab-' + t).classList.add('active');
}

function switchPlano(tipo, btn) {
  document.querySelectorAll('.plano-wrap').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.plano-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('plano-' + tipo).classList.add('active');
  btn.classList.add('active');
}


/* ══════════════════════════════
   UTILIDADES
══════════════════════════════ */
function fmt(n) {
  return Math.round(n).toLocaleString('es-AR');
}


/* ══════════════════════════════
   AHORROS — Cuentas
══════════════════════════════ */
const GOAL = 40000;
let accounts = [];

async function loadAccounts() {
  const status = document.getElementById('cuentas-status');
  try {
    const r = await fetch(API + '/api/cuentas');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    accounts = await r.json();
    if (status) status.innerHTML = '';
  } catch (e) {
    if (status) status.innerHTML =
      `<div class="ds-error-banner">⚠ No se pudieron cargar las cuentas. ${e.message}</div>`;
    accounts = [];
  }
  renderAccounts();
}

async function saveAccount(acc) {
  try {
    if (acc.id) {
      await fetch(API + '/api/cuentas/' + acc.id, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: acc.label, amount: acc.amount, orden: acc.orden || 0 })
      });
    } else {
      const r = await fetch(API + '/api/cuentas', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: acc.label, amount: acc.amount, orden: acc.orden || 0 })
      });
      acc.id = (await r.json()).id;
    }
  } catch (e) { /* silent — UI ya refleja el cambio */ }
}

async function deleteAccount(id) {
  try {
    await fetch(API + '/api/cuentas/' + id, { method: 'DELETE' });
  } catch (e) {}
}

function renderAccounts() {
  const c = document.getElementById('rows');
  c.innerHTML = '';
  accounts.forEach((acc, i) => {
    const row = document.createElement('div');
    row.className = 'row';
    row.innerHTML = `
      <input class="label-inp" value="${acc.label || ''}" placeholder="Nombre de la cuenta"
        onchange="accounts[${i}].label=this.value; saveAccount(accounts[${i}])">
      <div class="sep"></div>
      <div class="plan-monto-wrap">
        <span class="plan-monto-sym">USD</span>
        <input class="plan-monto-inp" type="number" inputmode="decimal"
          value="${acc.amount > 0 ? acc.amount : ''}" placeholder="0"
          onchange="accounts[${i}].amount=parseFloat(this.value)||0; saveAccount(accounts[${i}]); updateGoal()">
      </div>
      <button class="ds-del" aria-label="Eliminar"
        onclick="deleteAccount(accounts[${i}].id); accounts.splice(${i},1); renderAccounts()">✕</button>`;
    c.appendChild(row);
  });
  updateGoal();
}

function updateGoal() {
  const total = accounts.reduce((s, a) => s + (parseFloat(a.amount) || 0), 0);
  const pct   = Math.min((total / GOAL) * 100, 100);
  const rem   = GOAL - total;

  document.getElementById('total').textContent =
    total.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  document.getElementById('track').style.width = pct.toFixed(1) + '%';

  document.getElementById('pct').innerHTML =
    Math.floor(pct) + '<sup>%</sup>';

  document.getElementById('meta-current').textContent =
    'USD ' + total.toLocaleString('es-AR', { maximumFractionDigits: 0 });

  const msg = document.getElementById('meta-message');
  if (total >= GOAL) {
    msg.textContent = '✦ Lo lograste. La vida que construiste es real. ✦';
  } else {
    const rf = rem.toLocaleString('es-AR', { maximumFractionDigits: 0 });
    const msgs = [
      `USD ${rf} más por generar. Ya estás en camino.`,
      `Cada mes más cerca. USD ${rf} más por construir.`,
      `USD ${rf} más hacia tu libertad financiera. Lo estás haciendo.`,
      `USD ${rf} más para producir. Cada mes que trabajás, más cerca.`,
    ];
    msg.textContent = msgs[Math.floor(pct / 25) % msgs.length];
  }
}


/* ══════════════════════════════
   TIPS / SABIDURÍA
══════════════════════════════ */
const TIPS = [
  "La abundancia no se mide por cuánto gastás, sino por cuánto construís. Un ingreso mayor es una oportunidad de crecer, no de expandir gastos.",
  "El dinero fluye hacia quienes lo cuidan. Guardar no es privarte — es enviarte un regalo al futuro.",
  "Cuando sube tu ingreso, primero aumenta tu ahorro. Lo que no ves en tu cuenta corriente, no lo gastás.",
  "Elegí gastar en experiencias que enriquecen tu vida, no en cosas que mantienen una imagen. La libertad financiera es la mayor señal de abundancia.",
  "Visualizate ya en USD 40.000. Sentilo real. Esa emoción es lo que te mantiene alineada con el objetivo.",
  "La gratitud por lo que ya tenés abre espacio para recibir más. ¿Qué tres cosas de tu situación financiera actual te generan paz?",
  "No gastes para impresionar a personas que no están pensando en vos. Gastá para construir la vida que te imaginás.",
  "Automatizá el ahorro antes de ver el dinero disponible. Lo que no pasa por tu cuenta corriente, no existe como tentación.",
  "Los pequeños montos importan: USD 200 mensuales extra son USD 2.400 por año. Los hábitos chicos construyen fortunas grandes.",
  "Vivís desde la abundancia cuando gastás con intención, no por impulso. La diferencia está en la pregunta: ¿esto me suma de verdad?",
  "El lifestyle creep es silencioso: sube un plan, sube una suscripción, sube un hábito. Revisá tus gastos fijos cada tres meses con ojos frescos.",
];

let tipIdx = Math.floor(Math.random() * TIPS.length);

function nextTip() {
  tipIdx = (tipIdx + 1) % TIPS.length;
  document.getElementById('tip-text').textContent = TIPS[tipIdx];
}


/* ══════════════════════════════
   PLAN MENSUAL
══════════════════════════════ */
const MESES_NOM = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];

const INSTRUMENTOS = [
  { label: 'Fondo Conservador MP',   plat: 'Mercado Pago', tasa: 0.030 },
  { label: 'Empresas Argentinas MP', plat: 'Mercado Pago', tasa: 0.035 },
  { label: 'Lecap PPI',              plat: 'PPI',          tasa: 0.035 },
  { label: 'Boncap PPI',             plat: 'PPI',          tasa: 0.037 },
  { label: 'Otro',                   plat: '',             tasa: 0.030 },
];

const FEEDBACK = {
  'Fondo Conservador MP':   '✓ Liquidez inmediata, tasa ~3%/mes. Ideal para plata que puede necesitarse pronto.',
  'Empresas Argentinas MP': '✓ Más rendimiento que el conservador, algo más de riesgo. Buen complemento.',
  'Lecap PPI':              '✓ Tasa fija garantizada ~3.5%/mes. Sin volatilidad si llegás al vencimiento.',
  'Boncap PPI':             '✓ Tasa fija ~3.7%/mes, mayor plazo. Ideal si no necesitás tocarlo.',
  'Otro':                   '— Instrumento personalizado. Revisá la tasa antes de confirmar.',
};

let planData = [];

async function loadPlan() {
  try {
    const r = await fetch(API + '/api/plan');
    planData = await r.json();
  } catch (e) {
    planData = [];
  }
  renderPlan();
}

async function savePlanMes(id, monto, instrumento, plataforma, tasa_mensual) {
  try {
    await fetch(API + '/api/plan/' + id, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ monto, instrumento, plataforma, tasa_mensual })
    });
    const el = document.getElementById('saved-' + id);
    if (el) {
      el.classList.remove('visible');
      void el.offsetWidth; /* reflow para reiniciar animación */
      el.classList.add('visible');
    }
  } catch (e) {}
}

function cambiarInstrumento(id, i, value) {
  const [inst, plat, tasa] = value.split('|');
  planData[i].instrumento  = inst;
  planData[i].plataforma   = plat;
  planData[i].tasa_mensual = parseFloat(tasa);
  savePlanMes(id, planData[i].monto, inst, plat, parseFloat(tasa));
  const fb = document.getElementById('fb-' + id);
  if (fb) fb.textContent = FEEDBACK[inst] || '';
}

function cambiarMonto(id, i, value) {
  const monto = parseFloat(value) || 0;
  planData[i].monto = monto;
  savePlanMes(id, monto, planData[i].instrumento, planData[i].plataforma, planData[i].tasa_mensual);
}

async function agregarFila(mesKey) {
  const inst = INSTRUMENTOS[0];
  try {
    const r = await fetch(API + '/api/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mes: mesKey, monto: 190000,
        instrumento: inst.label, plataforma: inst.plat, tasa_mensual: inst.tasa
      })
    });
    const data = await r.json();
    planData.push({
      id: data.id, mes: mesKey, monto: 190000,
      instrumento: inst.label, plataforma: inst.plat, tasa_mensual: inst.tasa
    });
  } catch (e) {}
  renderPlan();
}

async function eliminarFila(id, mesKey) {
  try {
    await fetch(API + '/api/plan/' + id, { method: 'DELETE' });
    planData = planData.filter(p => p.id !== id);
  } catch (e) {}
  renderPlan();
}

function mesLabel(mesStr) {
  const [y, m] = mesStr.split('-');
  return `${MESES_NOM[parseInt(m) - 1]} ${y}`;
}

function hoyMes() {
  const h = new Date();
  return `${h.getFullYear()}-${String(h.getMonth() + 1).padStart(2, '0')}`;
}

function renderPlan() {
  if (!planData.length) {
    document.getElementById('plan-meses').innerHTML = '<p class="nota-legal">Cargando plan...</p>';
    return;
  }

  const hoy = hoyMes();

  /* agrupar filas por mes */
  const meses = {};
  planData.forEach((row, i) => {
    if (!meses[row.mes]) meses[row.mes] = [];
    meses[row.mes].push({ ...row, _i: i });
  });

  let tbody = '';

  Object.keys(meses).sort().forEach((mesKey, mesIdx) => {
    const filas    = meses[mesKey];
    const esActual = mesKey === hoy;
    const act      = esActual ? ' activo-row' : '';

    filas.forEach((row, idx) => {
      const i             = row._i;
      const isFirst       = idx === 0;
      const firstCls      = isFirst ? ' mes-row--first' : '';
      const puedeEliminar = filas.length > 1;
      const fb            = FEEDBACK[row.instrumento] || '';

      const opciones = INSTRUMENTOS.map(o =>
        `<option value="${o.label}|${o.plat}|${o.tasa}"
          ${row.instrumento === o.label ? 'selected' : ''}>${o.label}</option>`
      ).join('');

      /* ── Fila de instrumento ── */
      tbody += `
        <tr class="mes-row${firstCls}${act}">
          <td class="mes-cell">
            ${isFirst ? `
              <div class="mes-nombre${esActual ? ' mes-nombre--activo' : ''}">${mesLabel(mesKey)}</div>
              ${esActual ? '<div class="mes-tag">este mes</div>' : ''}
            ` : ''}
          </td>
          <td>
            <div class="ds-select-wrap">
              <select class="ds-select"
                onchange="cambiarInstrumento(${row.id}, ${i}, this.value)">
                ${opciones}
              </select>
            </div>
          </td>
          <td>
            <div class="monto-add-wrap">
              <div class="plan-monto-wrap">
                <span class="plan-monto-sym">$</span>
                <input type="number" inputmode="numeric"
                  value="${Math.round(row.monto)}" placeholder="190000"
                  class="plan-monto-inp"
                  onchange="cambiarMonto(${row.id}, ${i}, this.value)"
                  onblur="cambiarMonto(${row.id}, ${i}, this.value)">
              </div>
              ${isFirst
                ? `<button class="btn-add-inst" title="Agregar instrumento"
                     onclick="agregarFila('${mesKey}')">+</button>`
                : '<div style="width:26px"></div>'}
            </div>
          </td>
          <td>
            ${puedeEliminar
              ? `<button class="ds-del" aria-label="Eliminar"
                   onclick="eliminarFila(${row.id}, '${mesKey}')">✕</button>`
              : ''}
          </td>
        </tr>`;

      /* ── Fila de feedback + guardado ── */
      tbody += `
        <tr class="feedback-row${act}">
          <td></td>
          <td colspan="3">
            ${fb ? `<div id="fb-${row.id}" class="plan-feedback">${fb}</div>` : ''}
            <div id="saved-${row.id}" class="plan-saved">✓ guardado</div>
          </td>
        </tr>`;
    });

  });

  const totalAportado = planData.reduce((s, m) => s + parseFloat(m.monto), 0) + 190000;

  document.getElementById('plan-meses').innerHTML = `
    <div class="plan-table-wrap">
      <table class="plan-table">
        <thead>
          <tr>
            <th class="col-mes">Mes</th>
            <th>Instrumento</th>
            <th class="col-monto">Monto</th>
            <th class="col-del"></th>
          </tr>
        </thead>
        <tbody>${tbody}</tbody>
      </table>
    </div>`;

  document.getElementById('plan-resumen').innerHTML = `
    <div class="resumen-card">
      <div class="resumen-lbl">Total proyectado en 12 meses</div>
      <div class="resumen-val">$${fmt(totalAportado)}</div>
      <div class="resumen-sub">Suma de todos los aportes planificados</div>
    </div>`;
}


/* ══════════════════════════════
   INIT
══════════════════════════════ */
document.getElementById('tip-text').textContent = TIPS[tipIdx];
loadAccounts();
loadPlan();
