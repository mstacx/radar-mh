// Radar MH: interfaz sobre datos reales generados por radar_convocatorias.py (data/radar.json, data/fondos.json).
"use strict";

const HOY = new Date(); HOY.setHours(0, 0, 0, 0);
const DIA = 86400000;
const AREAS = ["Educación", "Nutrición", "Salud"];
const AVISO_FONDO_DIAS = 90;
const PISO = 15; // por debajo de este score, el filtro considera el ítem ruido (no se destaca en el Resumen)
let RADAR = null, FONDOS = [];
const filtros = {
  convocatorias: { area: "Todas las áreas", nivel: "Cualquier afinidad", fuente: "", texto: "", orden: "score", favs: false, vigentes: true },
  senales: { area: "Todas las áreas", nivel: "Cualquier afinidad", fuente: "", texto: "", orden: "score", favs: false, vigentes: true },
};
let vistaActual = "resumen";
let visibles = [];

// ---------- almacenamiento local (puede no estar disponible) ----------
function leerSet(k) { try { return new Set(JSON.parse(localStorage.getItem(k) || "[]")); } catch { return new Set(); } }
function guardarSet(k, s) { try { localStorage.setItem(k, JSON.stringify([...s])); } catch { /* sin almacenamiento */ } }
const favs = leerSet("radarmh-favs"), descartados = leerSet("radarmh-descartados");

// ---------- utilidades ----------
const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
const fecha = (iso) => (iso ? new Date(iso + "T00:00:00") : null);
const fmt = (d) => d.toLocaleDateString("es-PE", { day: "2-digit", month: "short", year: "numeric" });
const dias = (iso) => Math.round((fecha(iso) - HOY) / DIA);
const urlSegura = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");
const vigente = (it) => !it.deadline || dias(it.deadline) >= 0;
const esNuevo = (it) => it.primera_vez && dias(it.primera_vez) >= -7;
function toast(msg) { const t = el("div", "toast", msg); document.body.append(t); setTimeout(() => t.remove(), 2200); }

function badgeNivel(it) {
  const b = el("span", "b b-" + it.nivel.toLowerCase(), `${it.score} · ${it.nivel}`);
  const d = it.detalle || {};
  b.title = `Área ${d.Area ?? 0} · Geografía ${d.Geo ?? 0} · Población ${d.Contexto ?? 0} · Elegibilidad ${d.Elegibilidad ?? 0} · Exclusiones ${d.Negativa ?? 0}\n` +
    `Palabras detectadas: ${(it.palabras || []).map((p) => p.trim()).join(", ") || "ninguna"}`;
  return b;
}
function chipDeadline(it) {
  if (!it.deadline) return null;
  const n = dias(it.deadline);
  if (n < 0) return el("span", "dl-cerrada", `Cerró el ${fmt(fecha(it.deadline))}`);
  if (n <= 30) return el("span", "dl-pronto", n === 0 ? "Cierra hoy" : `Cierra en ${n} día${n === 1 ? "" : "s"}`);
  return el("span", "dl-ok", `Cierra el ${fmt(fecha(it.deadline))}`);
}

// ---------- carga ----------
async function cargar() {
  try {
    const [r, f] = await Promise.all([fetch("data/radar.json", { cache: "no-store" }), fetch("data/fondos.json", { cache: "no-store" })]);
    if (!r.ok) throw new Error("radar.json " + r.status);
    RADAR = await r.json();
    FONDOS = f.ok ? await f.json() : [];
  } catch (e) {
    document.getElementById("estado").textContent = "No se pudieron cargar los datos. Ejecuta radar_convocatorias.py --web y sirve esta carpeta por HTTP.";
    console.error(e);
    return;
  }
  const ok = RADAR.fuentes.filter((s) => s.ok).length;
  const gen = new Date(RADAR.generado);
  const est = document.getElementById("estado");
  est.textContent = "";
  est.append("Datos reales · actualizado ", el("b", null, gen.toLocaleString("es-PE", { dateStyle: "medium", timeStyle: "short" })),
    ` · ${ok}/${RADAR.fuentes.length} fuentes OK · ${RADAR.items.length} ítems`);
  document.getElementById("n-conv").textContent = RADAR.items.filter((i) => i.clase === "Convocatoria" && vigente(i)).length;
  document.getElementById("n-sen").textContent = RADAR.items.filter((i) => i.clase === "Señal").length;
  construirFiltros("convocatorias");
  construirFiltros("senales");
  pintarResumen();
  pintarFondos();
  pintarMetodo();
  mostrar(location.hash.slice(1) || "resumen");
}

// ---------- navegación ----------
function mostrar(vista) {
  if (!document.getElementById("v-" + vista)) vista = "resumen";
  vistaActual = vista;
  document.querySelectorAll(".vista").forEach((s) => { s.hidden = s.id !== "v-" + vista; });
  document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.vista === vista)));
  if (vista === "convocatorias" || vista === "senales") pintarLista(vista);
  if (location.hash.slice(1) !== vista) history.replaceState(null, "", "#" + vista);
}
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => mostrar(b.dataset.vista)));

// ---------- resumen ----------
function fondosConFecha() {
  return FONDOS.map((f) => {
    if (!f.mes_apertura) return { ...f, apertura: null, dias: null };
    let y = HOY.getFullYear();
    if (f.mes_apertura < HOY.getMonth() + 1) y += 1;
    const ap = new Date(y, f.mes_apertura - 1, 1);
    return { ...f, apertura: ap, dias: Math.round((ap - HOY) / DIA) };
  });
}
function itemLista(it, meta) {
  const li = el("li");
  const a = el("a", null, it.titulo); a.href = urlSegura(it.url); a.target = "_blank"; a.rel = "noopener noreferrer";
  li.append(a, " ", badgeNivel(it));
  li.append(el("span", "meta", meta));
  return li;
}
function pintarResumen() {
  const conv = RADAR.items.filter((i) => i.clase === "Convocatoria" && vigente(i));
  const utiles = conv.filter((i) => i.score >= PISO);
  const am = conv.filter((i) => i.nivel !== "Baja");
  const pronto = utiles.filter((i) => i.deadline && dias(i.deadline) <= 30);
  const nuevos = RADAR.items.filter(esNuevo);
  const fondosPrep = fondosConFecha().filter((f) => f.dias != null && f.dias <= AVISO_FONDO_DIAS);
  const kpis = [
    [conv.length, "convocatorias vigentes leídas"], [conv.length - utiles.length, `descartadas por el filtro (score < ${PISO})`],
    [am.length, "con afinidad alta o media"], [pronto.length, "relevantes que cierran en ≤ 30 días"],
    [nuevos.length, "ítems nuevos en 7 días"],
    [RADAR.items.filter((i) => i.clase === "Señal" && i.nivel !== "Baja").length, "señales relevantes"],
    [fondosPrep.length, "fondos recurrentes para preparar"],
  ];
  const cont = document.getElementById("kpis"); cont.textContent = "";
  kpis.forEach(([n, l]) => { const k = el("div", "kpi"); k.append(el("div", "num", String(n)), el("div", "lbl", l)); cont.append(k); });

  const top = document.getElementById("top-conv"); top.textContent = "";
  [...utiles].sort((a, b) => b.score - a.score).slice(0, 6).forEach((it) =>
    top.append(itemLista(it, `${it.entidad || it.fuente}${it.deadline ? " · cierra " + fmt(fecha(it.deadline)) : ""}`)));
  if (!am.length) top.after(el("p", "vacio", "Hoy ninguna convocatoria vigente llega a afinidad media: el filtro está descartando ruido. Revisa las Señales y los Fondos recurrentes."));

  const ci = document.getElementById("cierran"); ci.textContent = "";
  const prox = utiles.filter((i) => i.deadline).sort((a, b) => a.deadline.localeCompare(b.deadline)).slice(0, 6);
  prox.forEach((it) => ci.append(itemLista(it, `Cierra ${fmt(fecha(it.deadline))} (en ${dias(it.deadline)} días) · ${it.fuente}`)));
  if (!prox.length) ci.append(el("li", "vacio", `Ninguna convocatoria con score ≥ ${PISO} tiene fecha de cierre conocida.`));

  const fp = document.getElementById("fondos-pronto"); fp.textContent = "";
  fondosConFecha().sort((a, b) => (a.dias ?? 9999) - (b.dias ?? 9999)).slice(0, 5).forEach((f) => {
    const li = el("li");
    const a = el("a", null, `${f.fondo} — ${f.entidad}`); a.href = urlSegura(f.url); a.target = "_blank"; a.rel = "noopener noreferrer";
    li.append(a, el("span", "meta", f.dias == null ? "Ventanilla continua o fecha por verificar" :
      `Apertura estimada: ${fmt(f.apertura)} (en ${f.dias} días)${f.dias <= AVISO_FONDO_DIAS ? " · preparar ahora" : ""}`));
    fp.append(li);
  });
}

// ---------- filtros y listas ----------
function construirFiltros(vista) {
  const st = filtros[vista];
  const box = document.querySelector(`.filtros[data-para="${vista}"]`);
  box.textContent = "";
  const grupoChips = (opciones, clave) => {
    const g = el("div", "chips");
    opciones.forEach((o) => {
      const b = el("button", "chip", o); b.type = "button";
      b.setAttribute("aria-pressed", String(st[clave] === o));
      b.addEventListener("click", () => { st[clave] = o; construirFiltros(vista); pintarLista(vista); });
      g.append(b);
    });
    return g;
  };
  box.append(grupoChips(["Todas las áreas", ...AREAS], "area"), grupoChips(["Cualquier afinidad", "Alta y media"], "nivel"));
  const q = el("input"); q.type = "search"; q.placeholder = "Buscar (ej.: anemia, UNICEF, Perú)"; q.value = st.texto;
  q.setAttribute("aria-label", "Buscar");
  q.addEventListener("input", () => { st.texto = q.value; pintarLista(vista); });
  const fuentes = [...new Set(RADAR.items.filter((i) => claseDe(vista) === i.clase).map((i) => i.fuente))].sort();
  const sel = el("select"); sel.setAttribute("aria-label", "Fuente");
  [["", "Todas las fuentes"], ...fuentes.map((f) => [f, f])].forEach(([v, t]) => { const o = el("option", null, t); o.value = v; sel.append(o); });
  sel.value = st.fuente; sel.addEventListener("change", () => { st.fuente = sel.value; pintarLista(vista); });
  const ord = el("select"); ord.setAttribute("aria-label", "Orden");
  [["score", "Ordenar por afinidad"], ["deadline", "Ordenar por cierre"], ["reciente", "Más recientes primero"]].forEach(([v, t]) => { const o = el("option", null, t); o.value = v; ord.append(o); });
  ord.value = st.orden; ord.addEventListener("change", () => { st.orden = ord.value; pintarLista(vista); });
  const chk = (txt, clave) => { const l = el("label"); const c = el("input"); c.type = "checkbox"; c.checked = st[clave];
    c.addEventListener("change", () => { st[clave] = c.checked; pintarLista(vista); }); l.append(c, txt); return l; };
  box.append(q, sel, ord, chk("Solo favoritas", "favs"));
  if (vista === "convocatorias") box.append(chk("Solo vigentes", "vigentes"));
  box.append(el("span", "contador"));
}
const claseDe = (vista) => (vista === "convocatorias" ? "Convocatoria" : "Señal");

function filtrar(vista) {
  const st = filtros[vista];
  const q = st.texto.trim().toLowerCase();
  let r = RADAR.items.filter((i) => i.clase === claseDe(vista) && !descartados.has(i.url));
  if (st.area !== "Todas las áreas") r = r.filter((i) => (i.areas || []).includes(st.area));
  if (st.nivel === "Alta y media") r = r.filter((i) => i.nivel !== "Baja");
  if (st.fuente) r = r.filter((i) => i.fuente === st.fuente);
  if (st.favs) r = r.filter((i) => favs.has(i.url));
  if (vista === "convocatorias" && st.vigentes) r = r.filter(vigente);
  if (q) r = r.filter((i) => `${i.titulo} ${i.resumen} ${i.entidad || ""} ${i.fuente}`.toLowerCase().includes(q));
  const cmp = {
    score: (a, b) => b.score - a.score || (a.deadline || "9").localeCompare(b.deadline || "9"),
    deadline: (a, b) => (a.deadline || "9999").localeCompare(b.deadline || "9999") || b.score - a.score,
    reciente: (a, b) => (b.publicado || "").localeCompare(a.publicado || ""),
  }[st.orden];
  return r.sort(cmp);
}

function pintarLista(vista) {
  const lista = filtrar(vista);
  visibles = lista;
  const cont = document.getElementById("lista-" + vista);
  cont.textContent = "";
  const n = document.querySelector(`.filtros[data-para="${vista}"] .contador`);
  if (n) n.textContent = `${lista.length} resultado${lista.length === 1 ? "" : "s"}` + (descartados.size ? ` · ${descartados.size} descartado(s) oculto(s)` : "");
  if (!lista.length) { cont.append(el("p", "vacio", "No hay resultados con estos filtros.")); return; }
  const tpl = document.getElementById("tpl-tarjeta");
  const frag = document.createDocumentFragment();
  lista.slice(0, 300).forEach((it) => {
    const c = tpl.content.firstElementChild.cloneNode(true);
    if (it.score < PISO) c.classList.add("tenue");
    c.querySelector(".fuente").textContent = it.entidad ? `${it.entidad} · ${it.fuente}` : it.fuente;
    const bd = c.querySelector(".badges");
    if (esNuevo(it)) bd.append(el("span", "b b-nuevo", "Nuevo"));
    bd.append(badgeNivel(it));
    const a = c.querySelector("h3 a"); a.textContent = it.titulo; a.href = urlSegura(it.url);
    c.querySelector(".resumen").textContent = it.resumen || "";
    const meta = c.querySelector(".t-meta");
    const dl = chipDeadline(it); if (dl) meta.append(dl);
    (it.areas || []).forEach((ar) => meta.append(el("span", "tag", ar)));
    if (it.publicado) meta.append(el("span", "tag", "Publicado " + fmt(fecha(it.publicado))));
    const bf = c.querySelector(".fav");
    const pintarFav = () => { const on = favs.has(it.url); bf.setAttribute("aria-pressed", String(on)); bf.textContent = on ? "★ Favorita" : "☆ Favorita"; c.classList.toggle("es-fav", on); };
    pintarFav();
    bf.addEventListener("click", () => { favs.has(it.url) ? favs.delete(it.url) : favs.add(it.url); guardarSet("radarmh-favs", favs); pintarFav(); });
    c.querySelector(".copiar").addEventListener("click", () => copiarParaHub(it));
    c.querySelector(".descartar").addEventListener("click", () => { descartados.add(it.url); guardarSet("radarmh-descartados", descartados); pintarLista(vista); toast("Descartada en este navegador"); });
    frag.append(c);
  });
  cont.append(frag);
}

// ---------- integración con el Hub ----------
function filaHub(it) {
  // Mismo orden que las primeras columnas (azules) de la tabla tbl_Radar del Hub: se pega en la columna A.
  const id = "RAD-W" + HOY.toISOString().slice(2, 10).replace(/-/g, "") + "-" + Math.random().toString(36).slice(2, 6);
  const limpio = (s) => String(s || "").replace(/[\t\r\n]+/g, " ").trim();
  return [id, HOY.toISOString().slice(0, 10), it.fuente, it.titulo, it.url, it.resumen, it.publicado || "", it.deadline || ""].map(limpio).join("\t");
}
async function copiarParaHub(it) {
  try { await navigator.clipboard.writeText(filaHub(it)); toast("Fila copiada: pégala en la columna A de la hoja Radar del Hub"); }
  catch { prompt("Copia esta fila y pégala en la hoja Radar del Hub:", filaHub(it)); }
}

// ---------- fondos ----------
function pintarFondos() {
  const cont = document.getElementById("lista-fondos"); cont.textContent = "";
  fondosConFecha().sort((a, b) => (a.dias ?? 9999) - (b.dias ?? 9999)).forEach((f) => {
    const c = el("article", "tarjeta");
    const cab = el("div", "t-cab");
    cab.append(el("span", "fuente", `${f.tipo} · ${f.programa}`));
    const estado = f.dias == null ? el("span", "b b-baja", "Ventanilla / verificar")
      : f.dias <= AVISO_FONDO_DIAS ? el("span", "b b-alta", "Preparar ahora") : el("span", "b b-baja", "Más adelante");
    cab.append(estado);
    const h = el("h3"); const a = el("a", null, f.fondo); a.href = urlSegura(f.url); a.target = "_blank"; a.rel = "noopener noreferrer"; h.append(a);
    const meta = el("div", "t-meta");
    meta.append(el("span", "tag", f.entidad));
    if (f.monto) meta.append(el("span", "tag", f.monto));
    meta.append(el("span", f.dias != null && f.dias <= AVISO_FONDO_DIAS ? "dl-pronto" : "dl-ok",
      f.apertura ? `Apertura estimada ${fmt(f.apertura)} (en ${f.dias} días)` : "Sin mes fijo"));
    c.append(cab, h, el("p", "resumen", f.requisitos || ""), meta,
      el("p", "nota", `Última convocatoria conocida: ${f.ultima_convocatoria || "—"} · Verificación: ${f.verificacion}`));
    cont.append(c);
  });
}

// ---------- método ----------
function pintarMetodo() {
  const t = document.getElementById("tabla-fuentes"); t.textContent = "";
  const th = el("thead"); const tr = el("tr");
  ["Fuente", "Tipo", "Estado", "Ítems hoy"].forEach((h) => tr.append(el("th", null, h))); th.append(tr); t.append(th);
  const tb = el("tbody");
  RADAR.fuentes.forEach((s) => {
    const r = el("tr");
    r.append(el("td", null, s.fuente), el("td", null, s.tipo), el("td", s.ok ? "ok" : "err", s.ok ? "OK" : "Error"),
      el("td", null, s.ok ? String(s.items) : (s.error || "").slice(0, 60)));
    tb.append(r);
  });
  t.append(tb);
}

// ---------- exportar ----------
document.getElementById("exportar").addEventListener("click", () => {
  const datos = (vistaActual === "convocatorias" || vistaActual === "senales") ? visibles : RADAR.items;
  const cols = ["titulo", "entidad", "fuente", "clase", "score", "nivel", "areas", "deadline", "publicado", "url"];
  const esc = (v) => `"${String(Array.isArray(v) ? v.join(" / ") : v ?? "").replace(/"/g, '""')}"`;
  const csv = "﻿" + [cols.join(","), ...datos.map((i) => cols.map((c) => esc(i[c])).join(","))].join("\r\n");
  const a = el("a"); a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = `radar_mh_${HOY.toISOString().slice(0, 10)}.csv`; a.click(); URL.revokeObjectURL(a.href);
});

window.addEventListener("hashchange", () => mostrar(location.hash.slice(1)));
cargar();
