const SERIES_COLORS = [
  "var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)",
  "var(--series-5)", "var(--series-6)", "var(--series-7)", "var(--series-8)",
];

const fmt = (n) => "$" + Number(n).toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function currentMonth() {
  return new Date().toISOString().slice(0, 7);
}

let selectedMonth = currentMonth();
const categoryColorMap = {};

function colorForCategory(cat) {
  if (!(cat in categoryColorMap)) {
    const idx = Object.keys(categoryColorMap).length;
    categoryColorMap[cat] = idx < SERIES_COLORS.length ? SERIES_COLORS[idx] : "var(--series-other)";
  }
  return categoryColorMap[cat];
}

// ---------- tabs ----------
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("is-active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("is-active"));
    btn.classList.add("is-active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("is-active");
    if (btn.dataset.tab === "gastos") loadGastos();
    if (btn.dataset.tab === "cuentas") loadCuentas();
    if (btn.dataset.tab === "resumen") loadResumen();
  });
});

// ---------- resumen ----------
const mesInput = document.getElementById("mes-input");
mesInput.value = selectedMonth;
mesInput.addEventListener("change", () => {
  selectedMonth = mesInput.value;
  loadResumen();
});
document.getElementById("mes-prev").addEventListener("click", () => shiftMonth(-1));
document.getElementById("mes-next").addEventListener("click", () => shiftMonth(1));

function shiftMonth(delta) {
  const [y, m] = selectedMonth.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  selectedMonth = d.toISOString().slice(0, 7);
  mesInput.value = selectedMonth;
  loadResumen();
}

async function loadResumen() {
  const res = await fetch(`/api/resumen?mes=${selectedMonth}`);
  const data = await res.json();

  document.getElementById("stat-cuentas").textContent = fmt(data.total_cuentas_fijas);
  document.getElementById("stat-gastado").textContent = fmt(data.total_gastado);

  const breakdown = document.getElementById("categoria-breakdown");
  breakdown.innerHTML = "";
  const entries = Object.entries(data.por_categoria);
  if (entries.length === 0) {
    breakdown.innerHTML = '<p class="empty-hint">Todavía no cargaste gastos este mes.</p>';
  } else {
    const max = Math.max(...entries.map(([, v]) => v));
    entries.forEach(([cat, monto]) => {
      const row = document.createElement("div");
      row.className = "breakdown-row";
      const pct = max > 0 ? Math.round((monto / max) * 100) : 0;
      row.innerHTML = `
        <span class="cat-label">${cat}</span>
        <span class="breakdown-track"><span class="breakdown-fill" style="width:${pct}%;background:${colorForCategory(cat)}"></span></span>
        <span class="cat-amount">${fmt(monto)}</span>
      `;
      breakdown.appendChild(row);
    });
  }

  const cuentasList = document.getElementById("resumen-cuentas");
  cuentasList.innerHTML = "";
  if (data.cuentas_fijas.length === 0) {
    cuentasList.innerHTML = '<li class="empty-hint" style="border:none;background:none;">No tenés cuentas fijas cargadas.</li>';
  } else {
    data.cuentas_fijas.forEach((c) => {
      const li = document.createElement("li");
      li.innerHTML = `
        <div class="item-main">
          <span class="item-title">${c.nombre}</span>
          <span class="item-sub">${c.categoria} · vence el día ${c.dia_vencimiento}</span>
        </div>
        <span class="item-amount">${fmt(c.monto)}</span>
      `;
      cuentasList.appendChild(li);
    });
  }
}

// ---------- gastos ----------
const formGasto = document.getElementById("form-gasto");
formGasto.querySelector('input[name="fecha"]').value = todayISO();

formGasto.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(formGasto);
  const body = {
    fecha: fd.get("fecha"),
    categoria: fd.get("categoria"),
    monto: parseFloat(fd.get("monto")),
    descripcion: fd.get("descripcion"),
  };
  const res = await fetch("/api/gastos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.ok) {
    formGasto.reset();
    formGasto.querySelector('input[name="fecha"]').value = todayISO();
    loadGastos();
  }
});

async function loadGastos() {
  document.getElementById("gastos-mes-label").textContent = selectedMonth;
  const res = await fetch(`/api/gastos?mes=${selectedMonth}`);
  const gastos = await res.json();
  const list = document.getElementById("gastos-list");
  list.innerHTML = "";
  if (gastos.length === 0) {
    list.innerHTML = '<li class="empty-hint" style="border:none;background:none;">No hay gastos cargados este mes.</li>';
    return;
  }
  gastos.forEach((g) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="item-main">
        <span class="item-title">${g.categoria}${g.descripcion ? " · " + g.descripcion : ""}</span>
        <span class="item-sub">${g.fecha}</span>
      </div>
      <span class="item-amount">${fmt(g.monto)}</span>
      <div class="item-actions"><button data-id="${g.id}">Borrar</button></div>
    `;
    li.querySelector("button").addEventListener("click", async () => {
      await fetch(`/api/gastos/${g.id}`, { method: "DELETE" });
      loadGastos();
    });
    list.appendChild(li);
  });
}

// ---------- cuentas ----------
const formCuenta = document.getElementById("form-cuenta");
formCuenta.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(formCuenta);
  const body = {
    nombre: fd.get("nombre"),
    categoria: fd.get("categoria"),
    monto: parseFloat(fd.get("monto")),
    dia_vencimiento: parseInt(fd.get("dia_vencimiento"), 10),
  };
  const res = await fetch("/api/cuentas", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.ok) {
    formCuenta.reset();
    formCuenta.querySelector('input[name="dia_vencimiento"]').value = 1;
    loadCuentas();
  }
});

async function loadCuentas() {
  const res = await fetch("/api/cuentas");
  const cuentas = await res.json();
  const list = document.getElementById("cuentas-list");
  list.innerHTML = "";
  if (cuentas.length === 0) {
    list.innerHTML = '<li class="empty-hint" style="border:none;background:none;">No tenés cuentas fijas cargadas.</li>';
    return;
  }
  cuentas.forEach((c) => {
    const li = document.createElement("li");
    if (!c.activa) li.classList.add("is-inactiva");
    li.innerHTML = `
      <div class="item-main">
        <span class="item-title">${c.nombre}</span>
        <span class="item-sub">${c.categoria} · vence el día ${c.dia_vencimiento}${c.activa ? "" : " · inactiva"}</span>
      </div>
      <span class="item-amount">${fmt(c.monto)}</span>
      <div class="item-actions">
        <button data-action="toggle">${c.activa ? "Desactivar" : "Activar"}</button>
        <button data-action="delete">Borrar</button>
      </div>
    `;
    li.querySelector('[data-action="toggle"]').addEventListener("click", async () => {
      await fetch(`/api/cuentas/${c.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ activa: !c.activa }),
      });
      loadCuentas();
    });
    li.querySelector('[data-action="delete"]').addEventListener("click", async () => {
      await fetch(`/api/cuentas/${c.id}`, { method: "DELETE" });
      loadCuentas();
    });
    list.appendChild(li);
  });
}

// ---------- init ----------
loadResumen();
