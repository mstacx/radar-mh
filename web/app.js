// Radar MH · interfaz sobre datos reales (data/radar.json y data/fondos.json, generados por radar_convocatorias.py).
// Tres clases separadas: Convocatorias (solo fuentes oficiales), Pistas por verificar (agregadores) y Señales (noticias).
"use strict";

const HOY = new Date(); HOY.setHours(0, 0, 0, 0);
const DIA = 86400000;
const AVISO_DIAS = 90;
const PISO_SENAL = 20;
const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"];
const COMP = { tematica: ["Temática", 30], geografia: ["Geografía", 20], elegibilidad: ["Elegibilidad", 25], institucional: ["Institucional", 15], financiera: ["Financiera", 10] };
const TIPO_CLASE = { "Inversión social empresarial": "tipo-inv", "Filantropía y cooperación": "tipo-fil", "Política pública": "tipo-pol",
  "Pista de financiamiento": "tipo-pista", "Tendencia y contexto": "tipo-ten" };
let R = null, FONDOS = [], vista = "resumen", visibles = [];
const st = {
  conv: { estado: "Todas", noElegibles: false, orden: "afinidad", texto: "", favs: false },
  sen: { tipo: "Todos", area: "Todas", relevantes: true, texto: "", favs: false, orden: "relevancia" },
};

// ---------- almacenamiento local (puede no estar disponible) ----------
const leerSet = (k) => { try { return new Set(JSON.parse(localStorage.getItem(k) || "[]")); } catch { return new Set(); } };
const guardarSet = (k, s) => { try { localStorage.setItem(k, JSON.stringify([...s])); } catch { /* sin almacenamiento */ } };
const favs = leerSet("radarmh-favs"), descartados = leerSet("radarmh-descartados");
let verDescartados = false;

// ---------- utilidades ----------
const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
const fecha = (iso) => (iso ? new Date(iso + "T00:00:00") : null);
const fmt = (d) => d.toLocaleDateString("es-PE", { day: "2-digit", month: "short", year: "numeric" });
const dias = (iso) => Math.round((fecha(iso) - HOY) / DIA);
const urlSegura = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");
const enlace = (txt, url, cls) => { const a = el("a", cls, txt); a.href = urlSegura(url); a.target = "_blank"; a.rel = "noopener noreferrer"; return a; };
const clave = (x) => x.url || x.fuente || x.id;
const elegible = (c) => c.componentes.elegibilidad.puntos > 0;
const esNuevo = (it) => it.primera_vez && dias(it.primera_vez) >= -7;
function toast(msg) { document.querySelectorAll(".toast").forEach((t) => t.remove()); const t = el("div", "toast", msg); t.setAttribute("role", "status"); document.body.append(t); setTimeout(() => t.remove(), 2400); }
const claseEstado = (e) => (e.startsWith("Abierta") ? "e-abierta" : e === "Próxima" ? "e-proxima" : e === "Cerrada" ? "e-cerrada" : "e-sin");
const chipEstado = (e) => el("span", "estado-chip " + claseEstado(e), e);

function textoPlazo(c) {
  if (c.estado === "Cerrada" && c.deadline) return [`Cerró el ${fmt(fecha(c.deadline))}`, ""];
  if (c.deadline) { const n = dias(c.deadline); return [n === 0 ? "Cierra hoy" : `Cierra en ${n} día${n === 1 ? "" : "s"}`, n <= 21 ? "urgente" : ""]; }
  if (c.apertura) { const n = dias(c.apertura); return [n > 0 ? `Abre en ${n} días (${fmt(fecha(c.apertura))})` : `Abrió el ${fmt(fecha(c.apertura))}`, ""]; }
  if (c.estado.includes("ventanilla")) return ["Sin fecha límite (ventanilla)", ""];
  return ["Fecha no publicada", ""];
}
function anillo(valor, nivel) {
  const a = el("div", "anillo " + nivel.toLowerCase()); a.style.setProperty("--p", valor);
  const s = el("span"); s.append(String(valor), el("small", null, "afinidad")); a.append(s);
  a.setAttribute("aria-label", `Afinidad con MH: ${valor} de 100 (${nivel})`); a.setAttribute("role", "img");
  return a;
}
function dato(k, v, cls) { const d = el("div", "dato"); d.append(el("span", "k", k)); const s = el("span", "v " + (cls || ""), v); d.append(s); return d; }

// ---------- acciones comunes ----------
function botonesAccion(item, tipo, refrescar) {
  const box = el("div", "acciones");
  if (tipo === "conv") box.append(enlace("Ver convocatoria oficial ↗", item.fuente, "btn btn-pri"));
  else box.append(enlace(tipo === "pista" ? "Verificar en la fuente ↗" : "Leer nota ↗", item.url, "btn btn-sec"));
  const k = clave(item);
  const bf = el("button", "btn fav"); bf.type = "button";
  const pintar = () => { const on = favs.has(k); bf.setAttribute("aria-pressed", String(on)); bf.textContent = on ? "★ Guardada" : "☆ Guardar"; box.closest(".tarjeta")?.classList.toggle("es-fav", on); };
  bf.addEventListener("click", () => { favs.has(k) ? favs.delete(k) : favs.add(k); guardarSet("radarmh-favs", favs); pintar(); toast(favs.has(k) ? "Guardada en este navegador" : "Quitada de guardadas"); });
  const bc = el("button", "btn"); bc.type = "button"; bc.textContent = "Copiar para el Hub"; bc.title = "Copia una fila para pegar en la columna A de la hoja Radar del CRM";
  bc.addEventListener("click", () => copiarParaHub(item, tipo, bc));
  const bd = el("button", "btn-txt"); bd.type = "button";
  const descartada = descartados.has(k);
  bd.textContent = descartada ? "Restaurar" : "Descartar";
  bd.addEventListener("click", () => { descartada ? descartados.delete(k) : descartados.add(k); guardarSet("radarmh-descartados", descartados); toast(descartada ? "Restaurada" : "Descartada en este navegador"); refrescar(); });
  box.append(bf, bc, bd);
  setTimeout(pintar);
  return box;
}
function filaHub(item, tipo) {
  const id = "RAD-W" + HOY.toISOString().slice(2, 10).replace(/-/g, "") + "-" + Math.random().toString(36).slice(2, 6);
  const limpio = (s) => String(s ?? "").replace(/[\t\r\n]+/g, " ").trim();
  if (tipo === "conv") {
    const res = `Afinidad MH ${item.afinidad}/100 · ${item.estado} · ${item.monto}${item.moneda ? " " + item.moneda : ""} · ${item.elegibilidad}`;
    return [id, HOY.toISOString().slice(0, 10), item.organizacion, item.nombre, item.fuente, res, item.apertura || "", item.deadline || ""].map(limpio).join("\t");
  }
  return [id, HOY.toISOString().slice(0, 10), item.fuente, item.titulo, item.url, `${item.tipo_senal}: ${item.por_que}`, item.publicado || "", item.deadline || ""].map(limpio).join("\t");
}
async function copiarParaHub(item, tipo, boton) {
  const fila = filaHub(item, tipo);
  try { await navigator.clipboard.writeText(fila); } catch { window.prompt("Copia esta fila y pégala en la hoja Radar del CRM:", fila); return; }
  boton.textContent = "Copiado ✓"; boton.classList.add("hecho");
  toast("Fila copiada: pégala en la columna A de la hoja Radar del CRM");
  setTimeout(() => { boton.textContent = "Copiar para el Hub"; boton.classList.remove("hecho"); }, 2200);
}

// ---------- carga ----------
async function cargar() {
  try {
    const [r, f] = await Promise.all([fetch("data/radar.json", { cache: "no-store" }), fetch("data/fondos.json", { cache: "no-store" })]);
    if (!r.ok) throw new Error("radar.json " + r.status);
    R = await r.json(); FONDOS = f.ok ? await f.json() : [];
  } catch (e) {
    document.getElementById("estado").textContent = "No se pudieron cargar los datos.";
    console.error(e); return;
  }
  R.convocatorias = R.convocatorias || []; R.senales = R.senales || []; R.pistas = R.pistas || [];
  const ok = R.fuentes.filter((s) => s.ok).length;
  const est = document.getElementById("estado"); est.textContent = "";
  est.append("Datos reales · actualizado ", el("b", null, new Date(R.generado).toLocaleString("es-PE", { dateStyle: "medium", timeStyle: "short" })),
    ` · ${ok}/${R.fuentes.length} fuentes OK`);
  document.getElementById("n-conv").textContent = R.convocatorias.filter(elegible).length;
  document.getElementById("n-sen").textContent = R.senales.filter((s) => s.score >= PISO_SENAL).length;
  pintarResumen(); pintarFiltrosConv(); pintarFiltrosSen(); pintarCalendario(); pintarMetodo();
  document.querySelectorAll("[data-ir]").forEach((b) => b.addEventListener("click", () => mostrar(b.dataset.ir)));
  mostrar(location.hash.slice(1) || "resumen");
}

function mostrar(v) {
  if (!document.getElementById("v-" + v)) v = "resumen";
  vista = v;
  document.querySelectorAll(".vista").forEach((s) => { s.hidden = s.id !== "v-" + v; });
  document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.vista === v)));
  if (v === "convocatorias") pintarConv();
  if (v === "senales") pintarSen();
  if (location.hash.slice(1) !== v) history.replaceState(null, "", "#" + v);
}
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => { mostrar(b.dataset.vista); window.scrollTo({ top: 0 }); }));
window.addEventListener("hashchange", () => mostrar(location.hash.slice(1)));

// ---------- resumen ----------
function fondosConFecha() {
  return FONDOS.map((f) => {
    if (!f.mes_apertura) return { ...f, apertura: null, dias: null };
    let y = HOY.getFullYear(); if (f.mes_apertura < HOY.getMonth() + 1) y += 1;
    const ap = new Date(y, f.mes_apertura - 1, 1);
    return { ...f, apertura: ap, dias: Math.round((ap - HOY) / DIA) };
  });
}
function filaCompacta(c) {
  const a = enlace("", c.fuente, "fila");
  a.append(anillo(c.afinidad, c.nivel));
  const d = el("div"); d.append(el("div", "t", c.nombre));
  const m = el("div", "m"); m.append(chipEstado(c.estado), c.organizacion, " · ", textoPlazo(c)[0]); d.append(m);
  a.append(d); return a;
}
function pintarResumen() {
  const eleg = R.convocatorias.filter(elegible);
  const abiertas = eleg.filter((c) => c.estado.startsWith("Abierta"));
  const proximas = eleg.filter((c) => c.estado === "Próxima" && c.apertura && dias(c.apertura) <= AVISO_DIAS);
  const cerradas = eleg.filter((c) => c.estado === "Cerrada");
  const senRel = R.senales.filter((s) => s.score >= PISO_SENAL);
  const kp = [[abiertas.length, "convocatorias elegibles abiertas", ""], [proximas.length, `abren en ≤ ${AVISO_DIAS} días`, "k-tur"],
    [cerradas.length, "cerraron hace poco: preparar la próxima", "k-nar"], [R.convocatorias.length - eleg.length, "convocatorias no elegibles para MH (filtradas)", ""],
    [senRel.length, "señales relevantes", "k-tur"], [R.pistas.length, "pistas por verificar", "k-mag"]];
  const box = document.getElementById("kpis"); box.textContent = "";
  kp.forEach(([n, l, c]) => { const k = el("div", "kpi " + c); k.append(el("div", "num", String(n)), el("div", "lbl", l)); box.append(k); });

  const acc = document.getElementById("accion"); acc.textContent = "";
  acc.append(el("h3", null, "Qué hacer ahora"));
  const ol = el("ol", "pasos");
  const pasos = [];
  abiertas.forEach((c) => pasos.push([`Evaluar ${c.organizacion}: ${c.nombre}`, `${c.estado} · afinidad ${c.afinidad}. ${c.notas || ""}`, c.fuente]));
  proximas.forEach((c) => pasos.push([`Preparar ${c.organizacion}`, `${textoPlazo(c)[0]} · afinidad ${c.afinidad}. Arma desde ya la propuesta y la evidencia de resultados.`, c.fuente]));
  eleg.filter((c) => c.estado === "Sin confirmar").forEach((c) => pasos.push([`Confirmar ventanilla: ${c.organizacion}`, `${c.nombre} · afinidad ${c.afinidad}. ${c.notas || ""}`, c.fuente]));
  cerradas.forEach((c) => pasos.push([`Agendar la próxima edición: ${c.organizacion}`, `${textoPlazo(c)[0]} · afinidad ${c.afinidad}. ${c.notas || ""}`, c.fuente]));
  pasos.slice(0, 6).forEach(([t, m, url], i) => {
    const li = el("li"); li.append(el("span", "num-paso", String(i + 1)));
    const d = el("div"); const b = enlace(t, url); b.style.fontWeight = "700"; d.append(b, el("span", "meta", m)); li.append(d); ol.append(li);
  });
  if (!pasos.length) ol.append(el("li", "vacio", "Sin acciones pendientes con las fuentes oficiales de hoy."));
  acc.append(ol);

  const top = document.getElementById("top-conv"); top.textContent = "";
  [...eleg].sort((a, b) => b.afinidad - a.afinidad).slice(0, 5).forEach((c) => top.append(filaCompacta(c)));
  const ts = document.getElementById("top-sen"); ts.textContent = "";
  // Destacadas = señales accionables (no "tendencia y contexto", salvo que ocurran en Áncash)
  const PRIORIDAD = { "Pista de financiamiento": 0, "Inversión social empresarial": 1, "Filantropía y cooperación": 2, "Política pública": 3, "Tendencia y contexto": 4 };
  const accionables = R.senales.filter((s) => s.score >= PISO_SENAL && (s.tipo_senal !== "Tendencia y contexto" || s.en_ancash)
    && (s.tipo_senal !== "Pista de financiamiento" || s.en_ancash || ((s.detalle || {}).Geo || 0) >= 18));
  [...accionables].sort((a, b) => (b.en_ancash - a.en_ancash) || (PRIORIDAD[a.tipo_senal] - PRIORIDAD[b.tipo_senal]) || (b.score - a.score)).slice(0, 5).forEach((s) => {
    const a = enlace("", s.url, "fila");
    a.append(el("span", "tipo-chip " + (TIPO_CLASE[s.tipo_senal] || "tipo-ten"), s.tipo_senal));
    const d = el("div"); d.append(el("div", "t", s.titulo)); d.append(el("div", "m", `${s.entidad || s.fuente} · ${s.siguiente_paso}`)); a.append(d);
    a.style.gridTemplateColumns = "1fr"; ts.append(a);
  });
  if (!senRel.length) ts.append(el("p", "vacio", "Sin señales relevantes hoy."));
}

// ---------- convocatorias ----------
function grupoChips(opciones, actual, onSel, conteo) {
  const g = el("div", "chips"); g.setAttribute("role", "group");
  opciones.forEach((o) => {
    const b = el("button", "chip", o); b.type = "button"; b.setAttribute("aria-pressed", String(actual === o));
    if (conteo) b.append(el("span", "c", ` ${conteo(o)}`));
    b.addEventListener("click", () => onSel(o)); g.append(b);
  });
  return g;
}
function interruptor(txt, valor, onCambio) {
  const l = el("label", "interruptor"); const c = el("input"); c.type = "checkbox"; c.checked = valor;
  c.addEventListener("change", () => onCambio(c.checked)); l.append(c, txt); return l;
}
function buscador(valor, onInput, ph) { const q = el("input"); q.type = "search"; q.placeholder = ph; q.value = valor; q.setAttribute("aria-label", "Buscar"); q.addEventListener("input", () => onInput(q.value)); return q; }
function selector(opts, valor, onCambio, aria) { const s = el("select"); s.setAttribute("aria-label", aria); opts.forEach(([v, t]) => { const o = el("option", null, t); o.value = v; s.append(o); }); s.value = valor; s.addEventListener("change", () => onCambio(s.value)); return s; }

const ESTADOS = ["Todas", "Abiertas", "Próximas", "Sin confirmar", "Cerradas"];
const coincideEstado = (c, f) => f === "Todas" || (f === "Abiertas" && c.estado.startsWith("Abierta")) || (f === "Próximas" && c.estado === "Próxima")
  || (f === "Sin confirmar" && c.estado === "Sin confirmar") || (f === "Cerradas" && c.estado === "Cerrada");
function pintarFiltrosConv() {
  const s = st.conv, box = document.getElementById("f-conv"); box.textContent = "";
  const base = R.convocatorias.filter((c) => s.noElegibles || elegible(c));
  box.append(grupoChips(ESTADOS, s.estado, (o) => { s.estado = o; pintarFiltrosConv(); pintarConv(); }, (o) => base.filter((c) => coincideEstado(c, o)).length));
  box.append(buscador(s.texto, (v) => { s.texto = v; pintarConv(); }, "Buscar organización o tema"));
  box.append(selector([["afinidad", "Ordenar por afinidad"], ["plazo", "Ordenar por fecha"]], s.orden, (v) => { s.orden = v; pintarConv(); }, "Orden"));
  box.append(interruptor(`Mostrar no elegibles para MH (${R.convocatorias.length - R.convocatorias.filter(elegible).length})`, s.noElegibles, (v) => { s.noElegibles = v; pintarFiltrosConv(); pintarConv(); }));
  box.append(interruptor("Solo guardadas", s.favs, (v) => { s.favs = v; pintarConv(); }));
  box.append(interruptor("Ver descartadas", verDescartados, (v) => { verDescartados = v; pintarConv(); pintarSen(); }));
  box.append(el("span", "contador"));
}
function tarjetaConv(c) {
  const t = el("article", "tarjeta conv" + (elegible(c) ? "" : " no-elegible"));
  const cab = el("div", "t-cab"); cab.append(anillo(c.afinidad, c.nivel));
  const h = el("div"); h.append(el("div", "t-org", c.organizacion));
  const h3 = el("h3"); h3.append(enlace(c.nombre, c.fuente)); h.append(h3); cab.append(h);
  t.append(cab);
  const [plazo, urg] = textoPlazo(c);
  const datos = el("div", "datos");
  const d1 = el("div", "dato"); d1.append(el("span", "k", "Estado"), chipEstado(c.estado)); datos.append(d1);
  datos.append(dato(c.estado === "Próxima" ? "Apertura" : "Plazo", plazo, urg), dato("Monto", c.monto === "No especificado" ? "No especificado" : `${c.monto} ${c.moneda}`.trim()), dato("País", c.pais));
  t.append(datos);
  if (!elegible(c)) t.append(el("div", "alerta-no-eleg", "MH no puede postular: " + c.componentes.elegibilidad.razon));
  const pe = el("p", "elegib"); pe.append(el("b", null, "Quién puede postular: "), c.elegibilidad); t.append(pe);
  if (c.notas) t.append(el("p", "nota-fuente", c.notas));
  const det = el("details", "detalle"); det.append(el("summary", null, "Por qué esta afinidad y evidencia"));
  Object.entries(COMP).forEach(([k, [nom, max]]) => {
    const v = c.componentes[k]; const fila = el("div", "comp");
    const barra = el("div", "barra"); const i = el("i"); i.style.width = (100 * v.puntos / max) + "%"; barra.append(i);
    fila.append(el("span", null, nom), barra, el("span", null, `${v.puntos}/${max}`), el("span", "razon", v.razon)); det.append(fila);
  });
  if (c.evidencia) det.append(el("p", "evidencia", `«${c.evidencia}»`));
  det.append(el("p", "evidencia", `${c.origen} · verificado el ${fmt(fecha(c.verificado_el))} · ${c.fuente_nombre}`));
  t.append(det);
  t.append(botonesAccion(c, "conv", () => { pintarConv(); }));
  return t;
}
function pintarConv() {
  if (!R) return;
  const s = st.conv, q = s.texto.trim().toLowerCase();
  let lista = R.convocatorias.filter((c) => (s.noElegibles || elegible(c)) && coincideEstado(c, s.estado)
    && (verDescartados || !descartados.has(clave(c))) && (!s.favs || favs.has(clave(c)))
    && (!q || `${c.nombre} ${c.organizacion} ${c.tematica.join(" ")} ${c.pais}`.toLowerCase().includes(q)));
  const plazoKey = (c) => c.deadline || c.apertura || "9999";
  lista.sort(s.orden === "plazo" ? (a, b) => plazoKey(a).localeCompare(plazoKey(b)) : (a, b) => (elegible(b) - elegible(a)) || (b.afinidad - a.afinidad));
  visibles = lista.map((c) => ({ tipo: "Convocatoria", titulo: c.nombre, entidad: c.organizacion, estado: c.estado, afinidad: c.afinidad, deadline: c.deadline, apertura: c.apertura, monto: `${c.monto} ${c.moneda}`.trim(), url: c.fuente }));
  const box = document.getElementById("lista-conv"); box.textContent = "";
  document.querySelector("#f-conv .contador").textContent = `${lista.length} convocatoria${lista.length === 1 ? "" : "s"}` + (descartados.size && !verDescartados ? ` · descartadas ocultas` : "");
  if (!lista.length) box.append(el("p", "vacio", "No hay convocatorias con estos filtros."));
  lista.forEach((c) => box.append(tarjetaConv(c)));
  pintarPistas();
}
function pintarPistas() {
  const lista = R.pistas.filter((p) => verDescartados || !descartados.has(clave(p)));
  document.getElementById("n-pistas").textContent = lista.length;
  const box = document.getElementById("lista-pistas"); box.textContent = "";
  lista.slice(0, 60).forEach((p) => {
    const f = el("div", "pista");
    const d = el("div"); d.append(el("div", "t", p.titulo));
    d.append(el("div", "m", `${p.fuente}${p.deadline ? " · cierre indicado " + fmt(fecha(p.deadline)) : ""} · relevancia temática ${p.score}/100`));
    f.append(d, enlace("Verificar ↗", p.url, "btn btn-sec")); box.append(f);
  });
  if (!lista.length) box.append(el("p", "vacio", "Sin pistas pendientes."));
}

// ---------- señales ----------
const TIPOS = ["Todos", "Inversión social empresarial", "Filantropía y cooperación", "Política pública", "Pista de financiamiento", "Tendencia y contexto"];
const AREAS = ["Todas", "Educación", "Nutrición", "Salud", "Desarrollo rural"];
function pintarFiltrosSen() {
  const s = st.sen, box = document.getElementById("f-sen"); box.textContent = "";
  const base = R.senales.filter((x) => !s.relevantes || x.score >= PISO_SENAL);
  box.append(grupoChips(TIPOS, s.tipo, (o) => { s.tipo = o; pintarFiltrosSen(); pintarSen(); }, (o) => o === "Todos" ? base.length : base.filter((x) => x.tipo_senal === o).length));
  box.append(grupoChips(AREAS, s.area, (o) => { s.area = o; pintarFiltrosSen(); pintarSen(); }));
  box.append(buscador(s.texto, (v) => { s.texto = v; pintarSen(); }, "Buscar empresa, tema o lugar"));
  box.append(selector([["relevancia", "Más relevantes primero"], ["reciente", "Más recientes primero"]], s.orden, (v) => { s.orden = v; pintarSen(); }, "Orden"));
  box.append(interruptor(`Solo relevantes (≥ ${PISO_SENAL})`, s.relevantes, (v) => { s.relevantes = v; pintarFiltrosSen(); pintarSen(); }));
  box.append(interruptor("Solo guardadas", s.favs, (v) => { s.favs = v; pintarSen(); }));
  box.append(el("span", "contador"));
}
function tarjetaSen(x) {
  const t = el("article", "tarjeta senal" + (x.score < PISO_SENAL ? " tenue" : ""));
  const top = el("div", "meta-sen");
  top.append(el("span", "tipo-chip " + (TIPO_CLASE[x.tipo_senal] || "tipo-ten"), x.tipo_senal));
  if (x.en_ancash) top.append(el("span", "tag tag-ancash", "Áncash"));
  if (esNuevo(x)) top.append(el("span", "tag", "Nueva"));
  t.append(top);
  const h3 = el("h3"); h3.append(enlace(x.titulo, x.url)); t.append(h3);
  if (x.resumen) t.append(el("p", "resumen", x.resumen));
  const pq = el("div", "porque"); pq.append(el("b", null, "Por qué importa para MH"), x.por_que); t.append(pq);
  const meta = el("div", "meta-sen");
  meta.append(el("span", "paso", "→ " + x.siguiente_paso));
  const rel = el("span", "relev"); const barra = el("span", "barra"); const i = el("i"); i.style.width = x.score + "%"; barra.append(i);
  rel.append("Relevancia", barra, String(x.score)); rel.title = "Relevancia temática (palabras clave): " + ((x.palabras || []).map((p) => p.trim()).join(", ") || "ninguna");
  meta.append(rel);
  (x.areas || []).forEach((a) => meta.append(el("span", "tag", a)));
  meta.append(el("span", null, `${x.entidad || x.fuente}${x.publicado ? " · " + fmt(fecha(x.publicado)) : ""}`));
  t.append(meta);
  t.append(botonesAccion(x, "senal", () => { pintarSen(); }));
  return t;
}
function pintarSen() {
  if (!R) return;
  const s = st.sen, q = s.texto.trim().toLowerCase();
  let lista = R.senales.filter((x) => (!s.relevantes || x.score >= PISO_SENAL) && (s.tipo === "Todos" || x.tipo_senal === s.tipo)
    && (s.area === "Todas" || (x.areas || []).includes(s.area)) && (verDescartados || !descartados.has(clave(x)))
    && (!s.favs || favs.has(clave(x))) && (!q || `${x.titulo} ${x.resumen} ${x.entidad || ""}`.toLowerCase().includes(q)));
  lista.sort(s.orden === "reciente" ? (a, b) => (b.publicado || "").localeCompare(a.publicado || "") : (a, b) => (b.en_ancash - a.en_ancash) || (b.score - a.score));
  visibles = lista.map((x) => ({ tipo: "Señal · " + x.tipo_senal, titulo: x.titulo, entidad: x.entidad || x.fuente, estado: "", afinidad: x.score, deadline: x.deadline, apertura: "", monto: "", url: x.url }));
  const box = document.getElementById("lista-sen"); box.textContent = "";
  document.querySelector("#f-sen .contador").textContent = `${lista.length} señal${lista.length === 1 ? "" : "es"}`;
  if (!lista.length) box.append(el("p", "vacio", "No hay señales con estos filtros. Desactiva «Solo relevantes» para ver todas."));
  lista.slice(0, 120).forEach((x) => box.append(tarjetaSen(x)));
}

// ---------- calendario ----------
function pintarCalendario() {
  const fs = fondosConFecha();
  const meses = document.getElementById("meses"); meses.textContent = "";
  MESES.forEach((m, i) => {
    const c = el("div", "mes" + (i === HOY.getMonth() ? " actual" : "")); c.append(el("div", "nom", m));
    fs.filter((f) => f.mes_apertura === i + 1).forEach((f) => c.append(el("span", "ev", "Abre: " + f.fondo)));
    fs.filter((f) => f.mes_cierre === i + 1).forEach((f) => c.append(el("span", "ev cierre", "Cierra: " + f.fondo)));
    meses.append(c);
  });
  const box = document.getElementById("lista-fondos"); box.textContent = "";
  [...fs].sort((a, b) => (a.dias ?? 9999) - (b.dias ?? 9999)).forEach((f) => {
    const t = el("article", "tarjeta");
    const top = el("div", "meta-sen");
    const est = f.dias == null ? ["Ventanilla o sin mes fijo", "e-sin"] : f.dias <= AVISO_DIAS ? ["Preparar ahora", "e-abierta"] : ["Más adelante", "e-proxima"];
    top.append(el("span", "estado-chip " + est[1], est[0]), el("span", "tag", f.programa), el("span", "tag", f.tipo)); t.append(top);
    const h3 = el("h3"); h3.append(enlace(f.fondo, f.url)); t.append(h3);
    t.append(el("div", "t-org", f.entidad));
    const datos = el("div", "datos");
    datos.append(dato("Próxima apertura", f.apertura ? `${fmt(f.apertura)} (en ${f.dias} días)` : "—"), dato("Monto", f.monto || "No especificado"));
    t.append(datos);
    t.append(el("p", "elegib", f.requisitos || ""));
    t.append(el("p", "evidencia", `Última convocatoria: ${f.ultima_convocatoria || "—"} · ${f.verificacion}`));
    box.append(t);
  });
}

// ---------- método ----------
function pintarMetodo() {
  const ev = R.evaluacion || { criterios: [], fuentes: [], descartadas: [] };
  const t = document.getElementById("tabla-eval"); t.textContent = "";
  const th = el("thead"), tr = el("tr");
  ["Fuente", "Tipo", ...ev.criterios, "Uso", "Notas"].forEach((h) => tr.append(el("th", null, h))); th.append(tr); t.append(th);
  const tb = el("tbody");
  const usoCls = (u) => (u.startsWith("Automatizada") ? "uso-auto" : u.startsWith("Señales") ? "uso-sen" : u.startsWith("Pistas") || u.startsWith("Descubrimiento") ? "uso-pis" : "uso-man");
  ev.fuentes.forEach((f) => {
    const r = el("tr"); r.append(el("td", null, f.fuente), el("td", null, f.tipo));
    f.puntajes.forEach((p) => { const td = el("td", "c"); td.append(el("span", "punt p" + p, String(p))); r.append(td); });
    const tu = el("td"); tu.append(el("span", "uso " + usoCls(f.uso), f.uso)); r.append(tu, el("td", null, f.notas)); tb.append(r);
  });
  t.append(tb);
  const te = document.getElementById("tabla-estado"); te.textContent = "";
  const h2 = el("thead"), r2 = el("tr"); ["Fuente", "Clase", "Estado", "Detalle"].forEach((h) => r2.append(el("th", null, h))); h2.append(r2); te.append(h2);
  const b2 = el("tbody");
  R.fuentes.forEach((f) => { const r = el("tr"); r.append(el("td", null, f.fuente), el("td", null, f.categoria || f.tipo), el("td", f.ok ? "ok" : "err", f.ok ? "OK" : "Error"),
    el("td", null, f.ok ? (f.detalle || `${f.items} ítems`) : (f.error || "").slice(0, 90))); b2.append(r); });
  te.append(b2);
  const mo = document.getElementById("modelo"); mo.textContent = "";
  const razones = { tematica: "educación, nutrición, salud, desarrollo rural", geografia: "Perú y Áncash > América Latina > global", elegibilidad: "¿una ONG peruana puede postular directamente?",
    institucional: "encaje con el tipo de proyecto y las capacidades de MH", financiera: "monto útil, cofinanciamiento, restricciones" };
  Object.entries(COMP).forEach(([k, [n, max]]) => { const f = el("div", "modelo-fila"); f.append(el("b", null, n), el("span", null, `${max} pts`), el("span", null, razones[k])); mo.append(f); });
  mo.append(el("p", "evidencia", "Si MH no puede postular (elegibilidad 0), la afinidad total se limita a 15, aunque el tema sea muy afín. Alta ≥ 70 · Media 45-69 · Baja < 45."));
  const ul = document.getElementById("descartadas"); ul.textContent = "";
  ev.descartadas.forEach((d) => { const li = el("li"); li.append(el("b", null, d.fuente + ": "), d.motivo); ul.append(li); });
}

// ---------- exportar ----------
document.getElementById("exportar").addEventListener("click", () => {
  const datos = (vista === "convocatorias" || vista === "senales") ? visibles
    : R.convocatorias.map((c) => ({ tipo: "Convocatoria", titulo: c.nombre, entidad: c.organizacion, estado: c.estado, afinidad: c.afinidad, deadline: c.deadline, apertura: c.apertura, monto: `${c.monto} ${c.moneda}`.trim(), url: c.fuente }));
  const cols = ["tipo", "titulo", "entidad", "estado", "afinidad", "deadline", "apertura", "monto", "url"];
  const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const csv = "﻿" + [cols.join(","), ...datos.map((i) => cols.map((c) => esc(i[c])).join(","))].join("\r\n");
  const a = el("a"); a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = `radar_mh_${HOY.toISOString().slice(0, 10)}.csv`; a.click(); URL.revokeObjectURL(a.href);
});

cargar();
