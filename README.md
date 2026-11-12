# Radar de oportunidades: Misión Huascarán

Esta web se **actualiza sola cada día** con convocatorias y señales reales de financiamiento, puntuadas por afinidad con MH (educación, nutrición y salud en Áncash). No contiene datos internos de MH: el pipeline, los contactos y los convenios viven en el MH Fundraising Hub (Excel interno).

## Cómo funciona
```
06:00 Lima ─ GitHub Actions ─► motor/radar_convocatorias.py
                                 ├─ 6 RSS (fundsforNGOs, Opportunity Desk, PROCIENCIA, ProActivo)
                                 ├─ 6 búsquedas curadas en Google News (español e inglés)
                                 └─ API de la UE (llamados EuropeAid a la sociedad civil)
                               ► score de afinidad 0-100 (misma fórmula que el Hub)
                               ► web/data/radar.json (+ historial acumulado)
                               ► publica web/ en GitHub Pages
```

## Puesta en marcha (una sola vez, ~15 minutos, costo S/ 0)
1. Crea una cuenta en GitHub (o usa la de 180DC o la de MH) y un repositorio **público** nuevo, p. ej. `radar-mh`.
   GitHub Pages es gratis en repositorios públicos. El contenido es solo información pública de convocatorias.
2. En tu PC, arma la carpeta del repositorio:
   ```
   python 4-salidas/scripts/preparar_repo_radar.py
   ```
   Se crea `4-salidas/radar_repo/` con `motor/`, `web/`, `.github/workflows/radar.yml` y este README.
3. Sube esa carpeta al repositorio (con GitHub Desktop: *Add existing repository* → *Publish*; o con `git push`).
4. En GitHub, ve a **Settings › Pages › Build and deployment › Source: GitHub Actions**.
5. Ve a **Actions › Radar MH diario › Run workflow** para la primera corrida. Al terminar, la web queda en
   `https://<usuario>.github.io/radar-mh/`. Desde ese momento corre sola todos los días.

## Mantenimiento
| Quiero… | Dónde |
|---|---|
| Agregar o quitar una fuente o una búsqueda de Google News | `motor/radar_convocatorias.py` › `FUENTES` |
| Cambiar palabras clave o pesos del score | `motor/radar_convocatorias.py` › `KEYWORDS` (y lo mismo en la hoja Parametros del Hub) |
| Actualizar el calendario de fondos recurrentes | `motor/fondos_recurrentes.py` |
| Ver si una fuente falló | Pestaña **Fuentes y método** de la web, o el historial de **Actions** |

Si una fuente falla (sitio caído, bloqueo), el radar sigue con las demás y la web lo muestra en rojo.
GitHub desactiva los workflows programados después de 60 días sin actividad en el repositorio. Si pasa, basta con presionar *Enable workflow* en **Actions**.

## Alternativa sin GitHub
Correr `python radar_convocatorias.py --web ../radar_web/data` en cualquier PC y abrir la carpeta `radar_web` con un servidor local (`python -m http.server --directory radar_web`). Funciona igual, pero solo se actualiza cuando alguien lo ejecuta.
