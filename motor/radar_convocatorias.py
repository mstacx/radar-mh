"""
Radar de convocatorias - Misión Huascarán (motor real de scraping)
==================================================================
Lee fuentes reales de oportunidades de financiamiento y calcula un score de afinidad
con MH. Es la misma lógica que las fórmulas de la hoja 'Radar' del Hub (la paridad está
verificada). Clasifica cada ítem (convocatoria o señal, área y deadline) y guarda:

  4-salidas/data/radar_<fecha>.json         corrida del día (insumo del Hub)
  <--web DIR>/radar.json + fondos.json      datos de la web del Radar (acumulados con historial)

Tres clases de resultado, separadas a propósito (revisión del 14-nov-2026):
  - Convocatorias: SOLO desde fuentes oficiales (fuentes_oficiales.py), con afinidad MH en 5 componentes.
  - Pistas por verificar: lo que publican los agregadores (fundsforNGOs, Opportunity Desk, PROCIENCIA).
  - Señales: noticias (ProActivo, búsquedas de Google News) con tipo, por qué importa y siguiente paso.
El score por palabras clave (relevancia temática) se mantiene igual que en la hoja Radar del Hub.

Uso:
    python radar_convocatorias.py                         # corrida del día
    python radar_convocatorias.py --min 35                # muestra solo score >= 35
    python radar_convocatorias.py --web ../radar_web/data # además actualiza la web

Solo usa la biblioteca estándar de Python: corre igual en un PC que en GitHub Actions.
"""
import argparse
import html
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "data"
UA = {"User-Agent": "Mozilla/5.0 (MH-Fundraising-Hub radar; +https://misionhuascaran.org.pe)"}


def google_news(q: str, idioma: str = "es") -> str:
    """URL RSS pública de una búsqueda en Google News (también la puede leer Power Automate)."""
    loc = {"es": ("es-419", "PE", "PE:es-419"), "en": ("en-US", "US", "US:en")}[idioma]
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q, "hl": loc[0], "gl": loc[1], "ceid": loc[2]})


# Fuentes RSS. El flujo F1 de Power Automate puede leerlas todas, incluidas las de Google News.
FUENTES = [
    {"fuente": "fundsforNGOs News", "url": "https://news.fundsforngos.org/feed/", "tipo": "Agregador internacional", "categoria": "Descubrimiento"},
    {"fuente": "fundsforNGOs Donors", "url": "https://donors.fundsforngos.org/feed/", "tipo": "Agregador internacional", "categoria": "Descubrimiento"},
    {"fuente": "Opportunity Desk", "url": "https://www.opportunitydesk.org/feed/", "tipo": "Agregador internacional", "categoria": "Descubrimiento"},
    {"fuente": "PROCIENCIA (CONCYTEC)", "url": "https://prociencia.gob.pe/feed/", "tipo": "Fondo público Perú", "categoria": "Descubrimiento"},
    {"fuente": "ProActivo (RSE Perú)", "url": "https://proactivo.com.pe/feed/", "tipo": "Señales corporativas Perú", "categoria": "Señales"},
    {"fuente": "Google News: fondos concursables Perú", "tipo": "Búsqueda en noticias", "categoria": "Señales",
     "url": google_news('"fondos concursables" OR "fondo concursable" Perú when:30d')},
    {"fuente": "Google News: convocatorias ONG Perú", "tipo": "Búsqueda en noticias", "categoria": "Señales",
     "url": google_news('convocatoria (ONG OR "sin fines de lucro" OR "sociedad civil") Perú when:30d')},
    {"fuente": "Google News: anemia y nutrición", "tipo": "Búsqueda en noticias", "categoria": "Señales",
     "url": google_news('(convocatoria OR premio OR fondo) (anemia OR desnutrición OR "nutrición infantil") when:30d')},
    {"fuente": "Google News: primera infancia y educación rural", "tipo": "Búsqueda en noticias", "categoria": "Señales",
     "url": google_news('(convocatoria OR fondo OR premio) ("primera infancia" OR "educación rural") when:30d')},
    {"fuente": "Google News: inversión social Áncash", "tipo": "Señales corporativas Perú", "categoria": "Señales",
     "url": google_news('("responsabilidad social" OR "inversión social") (Áncash OR Huaraz OR Antamina) when:30d')},
    {"fuente": "Google News: grants NGOs Latin America", "tipo": "Búsqueda en noticias", "categoria": "Señales",
     "url": google_news('("call for proposals" OR "grant") NGOs "Latin America" when:30d', "en")},
]

# Palabras clave: (texto a buscar, categoría, peso). Búsqueda sin distinguir
# mayúsculas ni tildes, por subcadena (equivalente a SEARCH() en Excel).
# Topes por categoría en TOPES. Esta tabla es la misma que la hoja 'Parametros'.
KEYWORDS = [
    # Se escriben como quedan tras normalizar: minúsculas y sin guiones (el Excel cambia
    # la puntuación por espacios). Las palabras en español van con y sin tilde porque
    # el Excel no quita tildes. Espacios a los lados = palabra completa.
    # Área: Nutrición
    ("anemia", "Area", 15), ("malnutrition", "Area", 15), ("desnutricion", "Area", 15), ("desnutrición", "Area", 15),
    ("stunting", "Area", 12), ("nutrition", "Area", 12), ("nutricion", "Area", 12), ("nutrición", "Area", 12),
    ("food security", "Area", 10), ("seguridad alimentaria", "Area", 10),
    ("fortified", "Area", 8), ("fortificad", "Area", 8), ("alimentacion", "Area", 8), ("alimentación", "Area", 8),
    # Área: Educación
    ("early childhood", "Area", 10), ("primera infancia", "Area", 10),
    ("education", "Area", 10), ("educacion", "Area", 10), ("educación", "Area", 10),
    ("literacy", "Area", 8), ("lectora", "Area", 8), ("school", "Area", 6), ("escuela", "Area", 6),
    ("colegio", "Area", 6), ("teacher", "Area", 5), ("docente", "Area", 5),
    ("library", "Area", 5), ("biblioteca", "Area", 5),
    # Área: Salud
    ("primary health", "Area", 10), ("atencion primaria", "Area", 10), ("atención primaria", "Area", 10),
    ("telemedicine", "Area", 10), ("telemedicina", "Area", 10), ("maternal", "Area", 8),
    ("child health", "Area", 10), ("salud", "Area", 8), ("health", "Area", 8), ("medical", "Area", 5),
    ("water and sanitation", "Area", 6), ("agua y saneamiento", "Area", 6),
    # Geografía
    ("peru", "Geo", 30), ("perú", "Geo", 30), ("ancash", "Geo", 30), ("áncash", "Geo", 30), ("huaraz", "Geo", 30),
    ("andes", "Geo", 20), ("andean", "Geo", 20), ("andino", "Geo", 20),
    ("latin america", "Geo", 18), ("america latina", "Geo", 18), ("américa latina", "Geo", 18),
    ("latinoamerica", "Geo", 18), ("latinoamérica", "Geo", 18), ("south america", "Geo", 18),
    ("caribbean", "Geo", 12), (" lmic", "Geo", 10), ("middle income", "Geo", 10),
    ("developing countries", "Geo", 10), ("worldwide", "Geo", 8), ("global", "Geo", 6),
    # Contexto / población objetivo
    ("rural", "Contexto", 8), ("indigenous", "Contexto", 6), ("indigena", "Contexto", 6), ("indígena", "Contexto", 6),
    ("children", "Contexto", 6), ("ninos", "Contexto", 6), ("niños", "Contexto", 6), ("communit", "Contexto", 5),
    ("comunidad", "Contexto", 5), ("vulnerable", "Contexto", 4), ("poverty", "Contexto", 4), ("pobreza", "Contexto", 4),
    # Elegibilidad (ONG)
    (" ngo ", "Elegibilidad", 15), (" ngos ", "Elegibilidad", 15), (" ong ", "Elegibilidad", 10),
    (" ongs ", "Elegibilidad", 10), ("non profit", "Elegibilidad", 15), ("nonprofit", "Elegibilidad", 15),
    ("sin fines de lucro", "Elegibilidad", 15), ("civil society", "Elegibilidad", 12),
    ("sociedad civil", "Elegibilidad", 12), (" cso ", "Elegibilidad", 8), (" csos ", "Elegibilidad", 8),
    ("community based", "Elegibilidad", 10), ("organizaciones sociales", "Elegibilidad", 10),
    # Negativas: modalidades o geografías que MH no puede usar
    ("fellowship", "Negativa", -20), ("scholarship", "Negativa", -20), (" phd ", "Negativa", -20),
    ("journalis", "Negativa", -15), ("artist", "Negativa", -15), (" film", "Negativa", -10),
    ("startup", "Negativa", -15), ("start up", "Negativa", -15), (" smes ", "Negativa", -15),
    ("africa", "Negativa", -20), (" asia ", "Negativa", -15), (" india ", "Negativa", -20),
    ("nigeria", "Negativa", -25), ("kenya", "Negativa", -25), ("uganda", "Negativa", -25),
    ("pakistan", "Negativa", -25), ("bangladesh", "Negativa", -25), ("hong kong", "Negativa", -25),
    ("ireland", "Negativa", -20), ("europe", "Negativa", -10), ("united kingdom", "Negativa", -15),
    (" uk ", "Negativa", -15), ("australia", "Negativa", -15), ("canada", "Negativa", -10),
    ("united states", "Negativa", -10),
]
TOPES = {"Area": 40, "Geo": 30, "Contexto": 15, "Elegibilidad": 20, "Negativa": -40}
UMBRAL_ALTA, UMBRAL_MEDIA = 55, 35


PUNTUACION = ".,:;()/-’'\"!?"


def sin_tildes(texto: str) -> str:
    """Minúsculas, sin tildes y con la puntuación cambiada por espacios.
    Equivale a la columna 'TextoNorm' del Radar en el Excel."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    for ch in PUNTUACION:
        texto = texto.replace(ch, " ")
    return " " + re.sub(r"\s+", " ", texto).strip() + " "


def limpiar_html(texto: str) -> str:
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    return re.sub(r"\s+", " ", html.unescape(texto)).strip()


def puntuar(texto: str) -> dict:
    t = sin_tildes(texto)
    sub = {k: 0 for k in TOPES}
    hits, vistas = [], set()
    for palabra, cat, peso in KEYWORDS:
        clave = sin_tildes(palabra)
        clave = clave if palabra.startswith(" ") or palabra.endswith(" ") else clave.strip()
        if clave in vistas:  # variante con/sin tilde: cuenta una sola vez (igual que en Excel)
            continue
        vistas.add(clave)
        if clave in t:
            sub[cat] += peso
            hits.append(palabra)
    for cat, tope in TOPES.items():
        sub[cat] = max(tope, sub[cat]) if tope < 0 else min(tope, sub[cat])
    total = max(0, min(100, sum(sub.values())))
    nivel = "Alta" if total >= UMBRAL_ALTA else "Media" if total >= UMBRAL_MEDIA else "Baja"
    return {"score": total, "nivel": nivel, "detalle": sub, "palabras": hits}


MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
         "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
         "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
         "september": 9, "october": 10, "november": 11, "december": 12}
_MES = "|".join(MESES)
_CLAVE_CIERRE = (r"(?:deadline|due|closes?|closing date|hasta(?: el)?|cierre|cierra|vence|plazo|"
                 r"fecha l[ií]mite|postula(?:ciones)?)")


def _fecha(d, m, y, hoy):
    try:
        y = int(y) if y else (hoy.year + (1 if m < hoy.month - 1 else 0))
        y = 2000 + y if y < 100 else y
        return date(y, m, int(d)).isoformat()
    except ValueError:
        return None


def extraer_deadline(texto: str, hoy: date | None = None):
    """Busca la fecha de cierre en el texto (inglés o español). Devuelve ISO o None."""
    hoy = hoy or date.today()
    t = texto.lower()
    m = re.search(r"deadline:\s*(\d{1,2})-([a-z]{3})-(\d{2,4})", t)  # fundsforNGOs: Deadline: 13-Jul-2026
    if m:
        try:
            y = m.group(3) if len(m.group(3)) == 4 else "20" + m.group(3)
            return datetime.strptime(f"{m.group(1)}-{m.group(2)}-{y}", "%d-%b-%Y").date().isoformat()
        except ValueError:
            pass
    patrones = [
        (_CLAVE_CIERRE + r"[^.\n]{0,40}?(\d{1,2}) de (" + _MES + r")(?: de(?:l)? (\d{4}))?", (1, 2, 3)),
        (_CLAVE_CIERRE + r"[^.\n]{0,40}?(\d{1,2}) (" + _MES + r"),? (\d{4})", (1, 2, 3)),
        (_CLAVE_CIERRE + r"[^.\n]{0,40}?(" + _MES + r") (\d{1,2}),? (\d{4})", (2, 1, 3)),
    ]
    for rx, (gd, gm, gy) in patrones:
        m = re.search(rx, t)
        if m:
            return _fecha(m.group(gd), MESES[m.group(gm)], m.group(gy), hoy)
    m = re.search(_CLAVE_CIERRE + r"[^.\n]{0,40}?(\d{1,2})/(\d{1,2})/(\d{4})", t)
    if m:
        return _fecha(m.group(1), int(m.group(2)), m.group(3), hoy)
    return None


AREAS = {
    "Nutrición": r"anemia|nutri|desnutri|alimentaci|food security|seguridad alimentaria|fortific|hunger|hambre|stunting",
    "Educación": r"educa|school|escuela|colegio|literacy|lectura|lectora|teacher|docente|primera infancia|"
                 r"early childhood|biblioteca|library",
    "Salud": r"salud|health|m[eé]dic|telemedic|cl[ií]nic|hospital|maternal|saneamiento|sanitation",
    "Desarrollo rural": r"rural|comunidades? campesinas?|andin|agricult|productiv",
}
TERRITORIO = r"[áa]ncash|huaraz|carhuaz|yungay|huaylas|cordillera (blanca|negra)|callej[oó]n de huaylas"

# Tipos de señal, en orden de prioridad: (tipo, patrón, por qué importa para MH, siguiente paso sugerido).
# "Pista de financiamiento" exige lenguaje explícito de convocatoria: la palabra "premio" sola NO basta.
TIPOS_SENAL = [
    ("Pista de financiamiento",
     r"convocatoria|postula|postulaciones|fondos? concursables?|call for (proposals|applications)|applications? (are )?open|"
     r"inscripciones abiertas|bases del concurso|subvenci",
     "Menciona un fondo o concurso. No es una convocatoria verificada: hay que confirmar en la fuente oficial si una ONG peruana puede postular.",
     "Verificar bases en la fuente oficial"),
    ("Inversión social empresarial",
     r"responsabilidad social|inversi[oó]n social|gesti[oó]n social|valor compartido|sostenibilidad|\brse\b|"
     r"minera|empresa|compañ[ií]a|corporaci|grupo empresarial",
     "Empresa con programas de impacto social: posible aliado corporativo o modelo de intervención a replicar.",
     "Evaluar como prospecto en el CRM"),
    ("Filantropía y cooperación",
     r"fundaci[oó]n|cooperaci[oó]n|embajada|donaci[oó]n|dona |unicef|\bonu\b|\bbid\b|banco mundial|\bpma\b|\bops\b",
     "Actor filantrópico o de cooperación activo en temas de MH: fuente potencial de recursos o alianzas.",
     "Seguir y buscar un contacto"),
    ("Política pública",
     r"ministerio|minsa|minedu|midis|gobierno|congreso|\bley\b|programa nacional|municipalidad|regional|estado peruano",
     "Programa o decisión pública que puede abrir convenios, fondos o cambiar prioridades en el territorio.",
     "Monitorear y evaluar convenio"),
    ("Tendencia y contexto", r".",
     "Dato o tendencia útil como evidencia para propuestas y conversaciones con aliados.",
     "Usar como evidencia en propuestas"),
]
# PROCIENCIA publica en su RSS contrataciones de personal: no son fondos.
NO_ES_FONDO = r"-CS-INDV|consultor|especialista|analista|asistente|servicio de|t[eé]cnico en|l[ií]der t[eé]cnico|contrataci"


def clasificar(texto: str, categoria: str) -> dict:
    """Clase del ítem: 'Pista' (descubrimiento en agregadores, por verificar) o 'Señal' (noticia).
    Ningún ítem de RSS es Convocatoria: esa clase la producen solo las fuentes oficiales."""
    t = texto.lower()
    areas = [a for a, rx in AREAS.items() if re.search(rx, t)]
    en_ancash = bool(re.search(TERRITORIO, t))
    if categoria == "Descubrimiento":
        return {"areas": areas, "en_ancash": en_ancash, "clase": "Pista", "tipo_senal": "Convocatoria por verificar",
                "por_que": "Publicada por un agregador: puede ser real, pero debe verificarse en la fuente oficial "
                           "(elegibilidad para ONG peruanas, fecha y monto) antes de considerarla.",
                "siguiente_paso": "Verificar en la fuente oficial"}
    for tipo, rx, por_que, paso in TIPOS_SENAL:
        if re.search(rx, t):
            if en_ancash:
                por_que += " Ocurre en Áncash, el territorio de MH."
            if areas:
                por_que += " Temas: " + ", ".join(areas) + "."
            return {"areas": areas, "en_ancash": en_ancash, "clase": "Señal", "tipo_senal": tipo,
                    "por_que": por_que, "siguiente_paso": paso}


def _item(fuente, tipo, categoria, titulo, url, resumen, publicado, entidad=None):
    texto = f"{titulo}. {resumen}"
    return {"fuente": fuente, "tipo_fuente": tipo, "entidad": entidad, "titulo": titulo, "url": url,
            "resumen": resumen, "publicado": publicado, "deadline": extraer_deadline(texto),
            **clasificar(texto, categoria), **puntuar(texto)}


def leer_rss(f: dict, timeout=25) -> list:
    req = urllib.request.Request(f["url"], headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raiz = ET.fromstring(r.read())
    items = []
    for it in raiz.iter("item"):
        titulo = limpiar_html(it.findtext("title"))
        if re.search(NO_ES_FONDO, titulo, re.I):
            continue
        entidad = limpiar_html(it.findtext("source")) or None
        if entidad and titulo.endswith(" - " + entidad):  # Google News agrega " - Medio" al título
            titulo = titulo[: -len(" - " + entidad)]
        desc = limpiar_html(it.findtext("description"))
        if entidad and desc.startswith(titulo):  # en Google News la descripción repite el título
            desc = ""
        pub = it.findtext("pubDate")
        try:
            pub = parsedate_to_datetime(pub).date().isoformat() if pub else None
        except (TypeError, ValueError):
            pub = None
        items.append(_item(f["fuente"], f["tipo"], f["categoria"], titulo, (it.findtext("link") or "").strip(),
                           desc[:600], pub, entidad))
    return items


def actualizar_historial(ruta: Path, nuevos: list, hoy: date) -> list:
    """Acumula lo visto entre corridas (los RSS solo muestran lo último) y descarta lo vencido."""
    hist = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    for it in nuevos:
        previo = hist.get(it["url"], {})
        hist[it["url"]] = {**it, "primera_vez": previo.get("primera_vez", hoy.isoformat()), "ultima_vez": hoy.isoformat()}
    vigentes = {}
    for url, it in hist.items():
        if "tipo_senal" not in it or it.get("clase") not in ("Señal", "Pista"):
            continue  # formato anterior a la v2: se reclasifica cuando la fuente vuelva a publicarlo
        if it.get("deadline"):
            if date.fromisoformat(it["deadline"]) < hoy - timedelta(days=15):
                continue  # cerró hace más de 15 días
        elif date.fromisoformat(it["ultima_vez"]) < hoy - timedelta(days=60):
            continue  # sin deadline y sin verse hace 60 días
        vigentes[url] = it
    ruta.write_text(json.dumps(vigentes, ensure_ascii=False, indent=1), encoding="utf-8")
    return list(vigentes.values())


def main():
    from fuentes_oficiales import CRITERIOS, DESCARTADAS, EVALUACION, recolectar
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=0, help="score mínimo a mostrar")
    ap.add_argument("--web", type=Path, help="carpeta data/ de la web del Radar a actualizar")
    args = ap.parse_args()
    hoy = date.today()

    convocatorias, estado = recolectar(hoy)
    resultados = []
    for f in FUENTES:
        try:
            items = leer_rss(f)
            resultados += items
            estado.append({"fuente": f["fuente"], "tipo": f["tipo"], "categoria": f["categoria"], "ok": True,
                           "items": len(items)})
        except Exception as e:  # una fuente caída no debe detener el radar
            estado.append({"fuente": f["fuente"], "tipo": f["tipo"], "categoria": f["categoria"], "ok": False,
                           "error": str(e)[:200]})

    vistos, unicos = set(), []
    for r in sorted(resultados, key=lambda x: -x["score"]):
        clave_titulo = sin_tildes(r["titulo"])[:80]
        if r["url"] not in vistos and clave_titulo not in vistos:  # misma noticia en varias búsquedas
            vistos.update({r["url"], clave_titulo})
            unicos.append(r)

    generado = datetime.now(timezone.utc).isoformat(timespec="seconds")  # con zona: el navegador lo pasa a hora local
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"radar_{hoy.isoformat()}.json"
    out.write_text(json.dumps({"generado": generado, "fuentes": estado, "convocatorias": convocatorias, "items": unicos},
                              ensure_ascii=False, indent=2), encoding="utf-8")

    if args.web:
        from fondos_recurrentes import FONDOS
        args.web.mkdir(parents=True, exist_ok=True)
        # Si una fuente oficial falló hoy (p. ej., timeout), se conservan sus convocatorias de la última
        # lectura exitosa, marcadas como tales, para que no desaparezcan de la web por un día.
        previo = args.web / "radar.json"
        caidas = {e["fuente"] for e in estado if e.get("categoria") == "Oficial" and not e["ok"]}
        if caidas and previo.exists():
            anteriores = json.loads(previo.read_text(encoding="utf-8")).get("convocatorias", [])
            arrastre = [{**c, "notas": (c.get("notas", "") + f" (Dato de la última lectura exitosa: {c.get('verificado_el')}; "
                                        "la fuente no respondió hoy).").strip()}
                        for c in anteriores if c.get("fuente_nombre") in caidas]
            convocatorias += arrastre
            print(f"Fuentes caídas hoy: {sorted(caidas)} -> se conservan {len(arrastre)} convocatorias de la última lectura")
        acumulado = actualizar_historial(args.web / "historial.json", unicos, hoy)
        orden = lambda x: (-x["score"], x["titulo"])  # noqa: E731
        (args.web / "radar.json").write_text(json.dumps({
            "generado": generado, "fuentes": estado, "umbrales": {"alta": UMBRAL_ALTA, "media": UMBRAL_MEDIA},
            "convocatorias": convocatorias,
            "evaluacion": {"criterios": CRITERIOS,
                           "fuentes": [{"fuente": f, "tipo": t, "notas": n, "uso": u, "puntajes": p} for f, t, p, u, n in EVALUACION],
                           "descartadas": [{"fuente": f, "motivo": mo} for f, mo in DESCARTADAS]},
            "pistas": sorted([i for i in acumulado if i["clase"] == "Pista"], key=orden),
            "senales": sorted([i for i in acumulado if i["clase"] == "Señal"], key=orden)}, ensure_ascii=False), encoding="utf-8")
        # La web puede ser pública: se omite "relación existente MH" (dice con quién conversa MH).
        campos = ["fondo", "entidad", "tipo", "programa", "monto", "mes_apertura", "mes_cierre", "ultima_convocatoria",
                  None, "requisitos", "verificacion", "url"]
        fondos = [{c: v for c, v in zip(campos, f) if c} for f in FONDOS]
        (args.web / "fondos.json").write_text(json.dumps(fondos, ensure_ascii=False), encoding="utf-8")
        print(f"Web actualizada: {args.web} ({len(acumulado)} señales y pistas vigentes en historial)")

    for s in estado:
        print(("OK " if s["ok"] else "ERR"), f"[{s['categoria']}]", s["fuente"], s.get("detalle", s.get("items", s.get("error"))))
    print(f"\nConvocatorias oficiales: {len(convocatorias)} · elegibles para MH: "
          f"{sum(1 for c in convocatorias if c['componentes']['elegibilidad']['puntos'] > 0)}")
    for c in convocatorias:
        if c["componentes"]["elegibilidad"]["puntos"] > 0:
            print(f"  [{c['afinidad']:>3}] {c['estado']:<30} {c['nombre'][:70]}")
    print(f"\nSeñales y pistas de hoy: {len(unicos)} -> {out}")
    for r in unicos:
        if r["score"] >= args.min:
            print(f"[{r['score']:>3}] {r['clase']:<6} {r['tipo_senal'][:26]:<26} {r['titulo'][:80]}")


if __name__ == "__main__":
    sys.exit(main())
