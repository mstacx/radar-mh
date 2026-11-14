"""
Convocatorias de financiamiento desde FUENTES OFICIALES (estándar de evidencia alto).

Regla: aquí solo entran oportunidades publicadas por la entidad que financia, con condiciones
consultables. Las noticias y los agregadores NO producen convocatorias: van a Señales o a
"Pistas por verificar" (ver radar_convocatorias.py).

Cada convocatoria lleva los campos: nombre, organización, fuente (URL oficial), país, temática,
monto, moneda, deadline, estado, elegibilidad, afinidad MH (0-100, en 5 componentes) y
justificación. Si un dato no está publicado, se deja como "No especificado" o vacío:
nunca se inventa.

Afinidad MH (0-100):
  Temática      30  educación, nutrición, salud, desarrollo rural
  Geografía     20  Perú > América Latina > global
  Elegibilidad  25  ¿una ONG peruana puede postular directamente?
  Institucional 15  encaje con el tipo de proyecto y las capacidades de MH
  Financiera    10  monto útil para MH, cofinanciamiento, restricciones
Si la elegibilidad es 0 (no admite ONG peruanas), la afinidad total se limita a 15.

Fuentes verificadas el 14-nov-2026 (ver 1-evidencia/notas/evaluacion_fuentes.md).
"""
import html
import json
import re
import time
import urllib.parse
import urllib.request
import uuid
from datetime import date

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MH-Radar/2.0 (+https://misionhuascaran.org.pe)",
      "Accept-Language": "es-PE,es;q=0.9,en;q=0.8"}
PESOS = {"tematica": 30, "geografia": 20, "elegibilidad": 25, "institucional": 15, "financiera": 10}
TOPE_NO_ELEGIBLE = 15

MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
         "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
         "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
         "september": 9, "october": 10, "november": 11, "december": 12}


def abrir(req, timeout=45, intentos=3):
    """urlopen con reintentos: los sitios de embajadas y la API de la UE a veces tardan."""
    for i in range(intentos):
        try:
            return urllib.request.urlopen(req, timeout=timeout).read()
        except Exception:
            if i == intentos - 1:
                raise
            time.sleep(3 * (i + 1))


def leer(url, timeout=45):
    """Devuelve (html, texto plano) de una página oficial."""
    raw = abrir(urllib.request.Request(url, headers=UA), timeout).decode("utf-8", "ignore")
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S | re.I)
    return raw, html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))).strip()


def fecha_texto(d, mes, y):
    try:
        return date(int(y), MESES[mes.lower()], int(d)).isoformat()
    except (KeyError, ValueError):
        return None


def fragmento(texto, patron, ancho=220):
    m = re.search(patron, texto, re.I)
    if not m:
        return ""
    return texto[max(0, m.start() - 40): m.start() + ancho].strip()


def afinidad(c):
    """Suma los 5 componentes (cada uno con su razón) y arma la justificación."""
    comp = c["componentes"]
    total = sum(v["puntos"] for v in comp.values())
    if comp["elegibilidad"]["puntos"] == 0:
        total = min(total, TOPE_NO_ELEGIBLE)
    etiquetas = {"tematica": "Temática", "geografia": "Geografía", "elegibilidad": "Elegibilidad",
                 "institucional": "Institucional", "financiera": "Financiera"}
    partes = [f"{etiquetas[k]} {v['puntos']}/{PESOS[k]}: {v['razon']}" for k, v in comp.items()]
    if comp["elegibilidad"]["puntos"] == 0:
        partes.append(f"Como MH no puede postular, la afinidad se limita a {TOPE_NO_ELEGIBLE}.")
    c["afinidad"] = total
    c["nivel"] = "Alta" if total >= 70 else "Media" if total >= 45 else "Baja"
    c["justificacion"] = " ".join(partes)
    return c


def estado(hoy, deadline=None, apertura=None, ventanilla=False, base="Sin confirmar"):
    if deadline and deadline < hoy.isoformat():
        return "Cerrada"
    if apertura and apertura > hoy.isoformat():
        return "Próxima"
    if ventanilla:
        return "Abierta (ventanilla continua)"
    if deadline:
        return "Abierta"
    return base


def comp(puntos, razon):
    return {"puntos": puntos, "razon": razon}


def convocatoria(**kw):
    base = {"monto": "No especificado", "moneda": "", "deadline": None, "apertura": None, "evidencia": "",
            "notas": "", "origen": "Oficial (lectura automática)"}
    base.update(kw)
    return afinidad(base)


# ---------------------------------------------------------------------------
# 1. Unión Europea · Funding & Tenders (API oficial) · llamados EuropeAid por país
# ---------------------------------------------------------------------------
EU_API = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
LATAM = {"PE": "Perú", "BO": "Bolivia", "EC": "Ecuador", "CO": "Colombia", "CL": "Chile", "AR": "Argentina", "BR": "Brasil",
         "PY": "Paraguay", "UY": "Uruguay", "VE": "Venezuela", "MX": "México", "GT": "Guatemala", "HN": "Honduras",
         "SV": "El Salvador", "NI": "Nicaragua", "CR": "Costa Rica", "PA": "Panamá", "DO": "República Dominicana",
         "HT": "Haití", "CU": "Cuba"}
AREAS_MH = r"educa|school|nutri|food|health|salud|child|early|rural|water|wash|anemia"


def eu_europeaid(hoy):
    filtro = json.dumps({"bool": {"must": [{"terms": {"type": ["1", "2", "8"]}},
                                            {"terms": {"status": ["31094501", "31094502"]}}]}})
    vistos, salida = set(), []
    for q in ["EuropeAid civil society", "EuropeAid Peru", "EuropeAid Latin America", "EuropeAid nutrition", "EuropeAid education"]:
        fr = uuid.uuid4().hex
        cuerpo = "".join(f'--{fr}\r\nContent-Disposition: form-data; name="{n}"\r\nContent-Type: application/json\r\n\r\n{v}\r\n'
                         for n, v in [("query", filtro), ("languages", '["en","es"]')]) + f"--{fr}--\r\n"
        req = urllib.request.Request(f"{EU_API}?apiKey=SEDIA&pageSize=50&pageNumber=1&text={urllib.parse.quote(q)}",
                                     data=cuerpo.encode(), method="POST",
                                     headers={**UA, "Content-Type": f"multipart/form-data; boundary={fr}"})
        datos = json.loads(abrir(req, timeout=60))
        for r in datos.get("results", []):
            md = r.get("metadata", {})
            g = lambda k: (md.get(k) or [None])[0]  # noqa: E731
            ident, dl = g("identifier") or "", (g("deadlineDate") or "")[:10]
            if not ident.startswith("EuropeAid") or ident in vistos or not dl or dl < hoy.isoformat():
                continue
            vistos.add(ident)
            cod = ident.rsplit("/", 1)[-1]
            titulo = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", g("title") or ident))).strip()
            pais = LATAM.get(cod, "Multipaís" if cod == "Multi" else cod)
            es_pe = cod == "PE"
            tema = 30 if re.search(AREAS_MH, titulo, re.I) else 12
            salida.append(convocatoria(
                id=ident, nombre=titulo, organizacion="Comisión Europea · Delegación de la UE",
                fuente=r.get("url") or f"https://webgate.ec.europa.eu/prospect/external/publishedcalls.htm?callId={ident.split('/')[1]}",
                pais=pais, tematica=["Sociedad civil"] + (["Área MH"] if tema == 30 else []), deadline=dl,
                estado=estado(hoy, dl), elegibilidad=f"Organizaciones de la sociedad civil del país del llamado ({pais}).",
                componentes={
                    "tematica": comp(tema, "toca un área de MH" if tema == 30 else "sociedad civil en general, sin foco en las áreas de MH"),
                    "geografia": comp(20 if es_pe else 0, "llamado para Perú" if es_pe else f"llamado solo para {pais}"),
                    "elegibilidad": comp(20 if es_pe else 0, "ONG peruanas elegibles (suelen exigir consorcio y cofinanciamiento)" if es_pe
                                         else "solo organizaciones de ese país"),
                    "institucional": comp(8, "requiere gestión de fondos UE (reportes y auditoría exigentes)"),
                    "financiera": comp(6, "montos altos con cofinanciamiento obligatorio"),
                },
                evidencia=f"Identificador oficial {ident} · cierre {dl}"))
    return salida, f"{len(salida)} llamados EuropeAid vigentes · {sum(1 for c in salida if c['pais'] == 'Perú')} para Perú"


# ---------------------------------------------------------------------------
# 2. Canadá · Fondo Canadá para Iniciativas Locales (tabla oficial por país)
# ---------------------------------------------------------------------------
FCIL_URL = "https://www.international.gc.ca/world-monde/funding-financement/cfli-fcil/index.aspx?lang=eng"


def canada_fcil(hoy):
    _, t = leer(FCIL_URL)
    i = t.find("Call per country")
    tabla = t[i: i + 8000] if i >= 0 else ""
    m = re.search(r"\bPer[uú]\b\s+(Open|Closed|closed|open)\s+(\d{4}-\d{2}-\d{2})", tabla)
    if not m:
        return [], "Perú no figura en la tabla oficial de convocatorias por país (sin FCIL para Perú este ciclo)"
    dl = m.group(2)
    return [convocatoria(
        id="FCIL-PE", nombre="Fondo Canadá para Iniciativas Locales (FCIL) · Perú", organizacion="Gobierno de Canadá · Embajada en Lima",
        fuente=FCIL_URL, pais="Perú", tematica=["Desarrollo local", "Inclusión"], deadline=dl, estado=estado(hoy, dl),
        elegibilidad="Organizaciones locales (ONG, comunitarias) del país.",
        componentes={"tematica": comp(18, "prioridades temáticas por país; suelen incluir inclusión y desarrollo local"),
                     "geografia": comp(20, "convocatoria para Perú"), "elegibilidad": comp(25, "ONG locales elegibles"),
                     "institucional": comp(12, "proyectos pequeños diseñados por socios locales"),
                     "financiera": comp(7, "fondos pequeños de un año")},
        evidencia=m.group(0))], f"Perú figura en la tabla: {m.group(1)} hasta {dl}"


# ---------------------------------------------------------------------------
# 3. Australia · Direct Aid Program (DAP) · Perú y Bolivia
# ---------------------------------------------------------------------------
DAP_URL = "https://peru.embassy.gov.au/lima/DevelopmentDevelopment.html"


def australia_dap(hoy):
    _, t = leer(DAP_URL)
    m = re.search(r"DEADLINE:\s*\w+\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", t)
    dl = fecha_texto(*m.groups()) if m else None
    ciclo = re.search(r"(\d{4}-\d{2})\s+call for applications", t)
    monto = re.search(r"up to\s+AUD\$?\s?([\d,]+)", t)
    return [convocatoria(
        id="DAP-PE", nombre=f"Direct Aid Program (DAP) {ciclo.group(1) if ciclo else ''}".strip(),
        organizacion="Gobierno de Australia · Embajada en Lima", fuente=DAP_URL, pais="Perú y Bolivia",
        tematica=["Inclusión social (educación y capacidades)", "Crecimiento económico inclusivo", "Acción climática"],
        monto=f"Hasta {monto.group(1)}" if monto else "No especificado", moneda="AUD" if monto else "",
        deadline=dl, estado=estado(hoy, dl),
        elegibilidad="ONG locales o internacionales, grupos comunitarios y entidades académicas sin fines de lucro, "
                     "con sede u oficina en Perú o Bolivia. Beneficiarios: mujeres y niñas, comunidades indígenas, personas con discapacidad.",
        componentes={"tematica": comp(24, "inclusión social mediante educación; MH debe enfocarse en mujeres, niñas o comunidades indígenas"),
                     "geografia": comp(20, "exclusivo para Perú y Bolivia"),
                     "elegibilidad": comp(25, "ONG sin fines de lucro con oficina en Perú: MH califica"),
                     "institucional": comp(13, "proyectos pequeños y concretos, como los de MH"),
                     "financiera": comp(6, "hasta AUD 20,000: útil para un componente, no para un programa completo")},
        evidencia=fragmento(t, r"call for applications"), notas="Convocatoria anual. Si está cerrada, preparar la próxima edición (aprox. set.-nov.)."
    )], f"Ciclo {ciclo.group(1) if ciclo else '?'} · cierre {dl or 'no publicado'}"


# ---------------------------------------------------------------------------
# 4. República Checa · Proyectos de desarrollo a pequeña escala (Perú y Ecuador)
# ---------------------------------------------------------------------------
CZ_INDICE = "https://mzv.gov.cz/lima/es/comercio_y_economia/index.html"


def checa_lima(hoy):
    raw, _ = leer(CZ_INDICE)
    enlaces = sorted(set(re.findall(r'href="(/lima/es/comercio_y_economia/convocatoria_(\d{4})_para_proyectos_de[^"]*\.html)"', raw)),
                     key=lambda x: x[1], reverse=True)
    if not enlaces:
        return [], "No se encontraron páginas de convocatoria"
    anio = enlaces[0][1]
    # La embajada a veces publica la misma convocatoria en dos páginas: se usa la que trae más datos.
    candidatas = []
    for ruta, a in enlaces:
        if a != anio:
            continue
        url = "https://mzv.gov.cz" + ruta
        _, t = leer(url)
        m = re.search(r"fecha l[ií]mite para las propuestas es el (\d{1,2}) de (\w+) de (\d{4})", t, re.I)
        ap = re.search(r"dar[aá] inicio el (\d{1,2}) de (\w+) de (\d{4})", t, re.I)
        mo = re.search(r"entre CZK ([\d\s.]+?) y ([\d\s.]+?)\s+por proyecto", t)
        candidatas.append((bool(m) + bool(ap) + bool(mo), url, m, ap, mo))
    salida = []
    for _, url, m, ap, mo in sorted(candidatas, key=lambda x: -x[0])[:1]:
        dl = fecha_texto(*m.groups()) if m else None
        salida.append(convocatoria(
            id=f"CZ-PE-{anio}", nombre=f"Convocatoria {anio} para proyectos de desarrollo a pequeña escala",
            organizacion="República Checa · Embajada en Lima", fuente=url, pais="Perú y Ecuador",
            tematica=["Desarrollo económico de población vulnerable", "Resultados sostenibles"],
            monto=(f"{mo.group(1).strip()} – {mo.group(2).strip()}" if mo else "No especificado"), moneda="CZK" if mo else "",
            deadline=dl, apertura=fecha_texto(*ap.groups()) if ap else None, estado=estado(hoy, dl),
            elegibilidad="Entidades sin fines de lucro registradas en Perú. No pueden postular empresas, municipalidades, "
                         "gobiernos regionales, entidades del Estado ni organismos de la ONU.",
            componentes={"tematica": comp(18, "mejorar la situación económica de población vulnerable: encaja con la panadería "
                                              "de pan fortificado, no con capacitaciones (excluidas)"),
                         "geografia": comp(20, "exclusivo para Perú y Ecuador"),
                         "elegibilidad": comp(25, "ONG registradas en Perú: MH califica"),
                         "institucional": comp(12, "proyecto pequeño ejecutado de marzo a octubre; formulario en inglés"),
                         "financiera": comp(6, "~US$12K-24K; el riesgo cambiario lo asume la ONG")},
            evidencia=m.group(0) if m else "", notas="Convocatoria anual: abre en septiembre y cierra en octubre."))
    return salida, f"Convocatoria {anio} · cierre {salida[0]['deadline'] if salida else '?'}"


# ---------------------------------------------------------------------------
# 5. Inter-American Foundation (EE.UU.) · grants a organizaciones de base
# ---------------------------------------------------------------------------
IAF_URL = "https://www.iaf.gov/apply-for-grant/"


def iaf(hoy):
    _, t = leer(IAF_URL)
    abierta = bool(re.search(r"accept grant proposals 365 days", t, re.I))
    aviso = bool(re.search(r"Executive Order", t, re.I))
    return [convocatoria(
        id="IAF", nombre="Grants para desarrollo liderado por comunidades", organizacion="Inter-American Foundation (EE.UU.)",
        fuente=IAF_URL, pais="América Latina y el Caribe (incluye Perú)",
        tematica=["Desarrollo económico", "Agricultura", "Recursos naturales", "Participación cívica"],
        estado="Abierta (ventanilla continua)" if abierta else "Sin confirmar",
        elegibilidad="Organizaciones locales sin fines de lucro de América Latina; el grupo debe aportar recursos propios "
                     "(dinero o especie). No: entidades públicas, individuos ni empresas privadas.",
        componentes={"tematica": comp(16, "desarrollo económico comunitario; encaja con la panadería y la producción local, "
                                          "no con salud ni educación"),
                     "geografia": comp(18, "Perú es país prioritario"),
                     "elegibilidad": comp(22, "ONG locales elegibles; exige contrapartida"),
                     "institucional": comp(8, "privilegia proyectos liderados por las propias comunidades"),
                     "financiera": comp(3, "monto no publicado e incertidumbre por la revisión de la ayuda exterior de EE.UU.")},
        evidencia=fragmento(t, r"accept grant proposals"),
        notas=("La página advierte que su financiamiento se alinea con una Orden Ejecutiva de EE.UU. sobre ayuda exterior: "
               "confirmar disponibilidad antes de invertir tiempo." if aviso else ""))], \
        ("Recepción continua" if abierta else "Estado no detectado") + (" · con aviso de Orden Ejecutiva" if aviso else "")


# ---------------------------------------------------------------------------
# 6. Tinker Foundation · Institutional Grants (línea Educación)
# ---------------------------------------------------------------------------
TINKER_URL = "https://tinker.org/institutional-grants/"


def tinker(hoy):
    _, t = leer(TINKER_URL)
    m = re.search(r"(\d{4}) Cycle Opens ([A-Za-z]+) (\d{1,2})", t)
    ap = fecha_texto(m.group(3), m.group(2), m.group(1)) if m else None
    mo = re.search(r"From \$([\d,]+) to \$([\d,]+) per year", t)
    return [convocatoria(
        id="TINKER-EDU", nombre=f"Institutional Grants · Educación (ciclo {m.group(1) if m else 'próximo'})",
        organizacion="Tinker Foundation", fuente=TINKER_URL, pais="América Latina",
        tematica=["Educación (resultados de aprendizaje)", "Gobernanza democrática"],
        monto=(f"{mo.group(1)} – {mo.group(2)} por año, hasta 3 años" if mo else "No especificado"), moneda="USD" if mo else "",
        apertura=ap, estado=estado(hoy, apertura=ap),
        elegibilidad="Organizaciones que trabajan por América Latina, con énfasis en organizaciones de la región.",
        componentes={"tematica": comp(18, "educación con foco en resultados de aprendizaje y evidencia; encaja en parte con comprensión lectora"),
                     "geografia": comp(14, "regional, sin foco específico en Perú rural"),
                     "elegibilidad": comp(20, "organizaciones latinoamericanas elegibles"),
                     "institucional": comp(7, "prioriza cambio de políticas, escala y evidencia rigurosa: exige mostrar medición de aprendizajes"),
                     "financiera": comp(10, "US$50K-100K al año por hasta 3 años: monto muy relevante para MH")},
        evidencia=m.group(0) if m else "")], f"Próximo ciclo: {ap or 'no publicado'}"


# ---------------------------------------------------------------------------
# 7. Verificadas manualmente (fuente oficial que no permite lectura automática)
# ---------------------------------------------------------------------------
def verificadas_manualmente(hoy):
    apc = convocatoria(
        id="APC-JP", nombre="Asistencia para Proyectos Comunitarios de Seguridad Humana (APC)",
        organizacion="Gobierno de Japón · Embajada en Lima", fuente="https://www.pe.emb-japan.go.jp",
        pais="Perú", tematica=["Infraestructura comunitaria: salud, educación, agua"],
        estado="Sin confirmar",
        elegibilidad="ONG sin fines de lucro, hospitales, escuelas y municipalidades en Perú (programa vigente desde 1989).",
        componentes={"tematica": comp(24, "financia infraestructura y equipamiento de salud y educación (p. ej., postas, aulas)"),
                     "geografia": comp(20, "exclusivo para Perú"), "elegibilidad": comp(25, "ONG peruanas elegibles"),
                     "institucional": comp(10, "solo bienes e infraestructura; requiere cotizaciones y expediente técnico"),
                     "financiera": comp(5, "monto no publicado en la fuente consultada")},
        origen="Oficial (verificado manualmente)",
        evidencia="Formatos de solicitud y presentación del programa en pe.emb-japan.go.jp (la web bloquea la lectura automática).",
        notas="Confirmar con la Embajada si hay ventanilla abierta para el año fiscal en curso.")
    return [apc], "1 programa verificado a mano (APC Japón)"


# Evaluación de fuentes (14-nov-2026). Escala 1-5 por criterio:
# autoridad, frecuencia de publicación, pertinencia para Perú, facilidad de extracción,
# campos disponibles (deadline/monto/temática/requisitos), página individual por convocatoria, detección de cambios.
CRITERIOS = ["Autoridad", "Frecuencia", "Pertinencia Perú", "Extracción", "Campos", "Página individual", "Detección de cambios"]
EVALUACION = [
    ("Unión Europea · Funding & Tenders", "Multilateral (oficial)", [5, 5, 3, 5, 4, 5, 5], "Automatizada (API)",
     "API JSON oficial con identificador, país y fecha de cierre. Los llamados para Perú son esporádicos: hay que vigilarlos."),
    ("Australia · Direct Aid Program", "Embajada (oficial)", [5, 3, 5, 4, 5, 3, 4], "Automatizada",
     "Exclusivo Perú-Bolivia; la página publica ciclo, deadline, monto, ejes y elegibilidad."),
    ("República Checa · Proyectos a pequeña escala", "Embajada (oficial)", [5, 3, 5, 4, 5, 5, 5], "Automatizada",
     "Una página por convocatoria anual con apertura, cierre, monto y exclusiones. Perú-Ecuador."),
    ("Canadá · FCIL (tabla por país)", "Gobierno (oficial)", [5, 3, 2, 5, 3, 4, 5], "Automatizada (vigilancia)",
     "Tabla oficial de estado y deadline por país. Perú no figura en 2026: el recolector avisa si aparece."),
    ("Inter-American Foundation", "Agencia de cooperación (oficial)", [5, 5, 4, 3, 3, 3, 3], "Automatizada (estado)",
     "Ventanilla continua para organizaciones de base de LatAm; no publica montos; riesgo por la revisión de la ayuda de EE.UU."),
    ("Tinker Foundation", "Fundación (oficial)", [4, 3, 3, 4, 4, 3, 4], "Automatizada",
     "Publica fecha de apertura de ciclo y rango de montos de su línea de Educación."),
    ("Japón · APC", "Embajada (oficial)", [5, 4, 5, 1, 2, 2, 1], "Verificación manual anual",
     "Programa idóneo para infraestructura de salud y educación, pero la web bloquea la lectura automática (HTTP 403)."),
    ("UN Partner Portal (UNICEF, PMA, OPS…)", "Multilateral (oficial)", [5, 5, 4, 1, 5, 5, 5], "Registro de MH (no scraping)",
     "Los llamados a ONG de las agencias ONU se publican aquí, pero requieren cuenta: MH debe registrarse y recibir alertas."),
    ("PROCIENCIA (CONCYTEC)", "Fondo público Perú (oficial)", [5, 4, 4, 3, 2, 3, 4], "Descubrimiento con filtro",
     "Su RSS mezcla convocatorias con contrataciones de personal (se filtran). Fondos orientados a investigación: requiere socio académico."),
    ("fundsforNGOs (News, Donors)", "Agregador", [2, 5, 2, 4, 2, 3, 4], "Pistas por verificar",
     "Útil para descubrir, no para decidir: siempre verificar en la fuente oficial. El feed principal está roto (redirección en bucle)."),
    ("Opportunity Desk", "Agregador", [2, 5, 1, 4, 2, 3, 4], "Pistas por verificar", "Mayormente becas y premios individuales."),
    ("ProActivo (RSE Perú)", "Medio especializado", [3, 5, 5, 5, 1, 3, 4], "Señales",
     "Inversión social y sostenibilidad de empresas en Perú: insumo para prospección corporativa."),
    ("Google News (6 búsquedas curadas)", "Medios (búsqueda)", [3, 5, 4, 5, 1, 2, 4], "Señales",
     "Detecta anuncios, tendencias y pistas; nunca se trata como convocatoria."),
]
DESCARTADAS = [
    ("fundsforNGOs (feed global)", "Error HTTP 301: el sitio redirige el feed a sí mismo (falla del origen)."),
    ("Embajada de EE.UU. en Lima · grants", "La página de grants ya no existe (HTTP 404)."),
    ("Embajada de Alemania en Lima · microproyectos", "No publica un programa de microproyectos para Perú."),
    ("Finlandia y Nueva Zelanda · fondos locales", "Tienen fondos locales en otros países, pero no en Perú."),
    ("GlobalGiving Accelerator", "Bloquea la lectura automática (HTTP 403) y es crowdfunding, no un grant."),
    ("Grants.gov", "Fondos federales de EE.UU. sin pertinencia para una ONG peruana; la API rechaza el acceso (403)."),
    ("Devex Funding / DevelopmentAid", "Requieren suscripción paga o cuenta."),
]


RECOLECTORES = [
    ("Unión Europea · Funding & Tenders (API)", "Multilateral", eu_europeaid),
    ("Canadá · FCIL (tabla por país)", "Cooperación bilateral", canada_fcil),
    ("Australia · Direct Aid Program", "Cooperación bilateral", australia_dap),
    ("República Checa · Proyectos a pequeña escala", "Cooperación bilateral", checa_lima),
    ("Inter-American Foundation", "Agencia de cooperación", iaf),
    ("Tinker Foundation", "Fundación internacional", tinker),
    ("Verificación manual (APC Japón)", "Cooperación bilateral", verificadas_manualmente),
]


def recolectar(hoy=None):
    """Ejecuta todos los recolectores oficiales. Una fuente caída no detiene a las demás."""
    hoy = hoy or date.today()
    convocatorias, estados = [], []
    for nombre, tipo, fn in RECOLECTORES:
        try:
            items, detalle = fn(hoy)
            for c in items:
                c.setdefault("verificado_el", hoy.isoformat())
                c["fuente_nombre"] = nombre
            convocatorias += items
            estados.append({"fuente": nombre, "tipo": tipo, "categoria": "Oficial", "ok": True, "items": len(items), "detalle": detalle})
        except Exception as e:
            estados.append({"fuente": nombre, "tipo": tipo, "categoria": "Oficial", "ok": False, "error": str(e)[:200]})
    orden = {"Abierta": 0, "Abierta (ventanilla continua)": 1, "Próxima": 2, "Sin confirmar": 3, "Cerrada": 4}
    convocatorias.sort(key=lambda c: (c["componentes"]["elegibilidad"]["puntos"] == 0, orden.get(c["estado"], 5), -c["afinidad"]))
    return convocatorias, estados


if __name__ == "__main__":
    cs, es = recolectar()
    for e in es:
        print("OK " if e["ok"] else "ERR", e["fuente"], "·", e.get("detalle", e.get("error")))
    print()
    for c in cs:
        print(f"[{c['afinidad']:>3} {c['nivel']:<5}] {c['estado']:<30} {c['deadline'] or c['apertura'] or '':<10} {c['nombre'][:70]}")
