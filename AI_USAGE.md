# Declaración de uso de Super Inteligencia (SI)

Este proyecto fue desarrollado con asistencia de modelos de lenguaje (SI/LLM) como
herramienta de ingeniería. Se declara aquí, en el `README.md` y en los metadatos
del producto (`<meta name="generator">` y cabeceras de `index.html`) para que el
origen de cada elemento sea verificable.

## Dónde y cómo se usó SI

| Ámbito | Uso concreto | Artefactos |
|---|---|---|
| Programación | Generación y refactorización del visor web, backend Python, app de escritorio, firmware y Worker | `index.html`, `servidor_lunar.py`, `visor_lunar_hud.py`, `esp32_casco_hud.ino`, `cloudflare_worker/worker.js` |
| Depuración / resolución de problemas | Corrección del bug de conexión serie, del LED con tres dueños, del `readStringUntil` bloqueante, del fallback 405 en hosting estático y del sondeo falso por SPA fallback | mismos archivos + registros de verificación |
| Análisis e interpretación de datos | Conversión del GeoTIFF LRO/LOLA a rejilla Int16 512×512, validación de 0,406 m de error máximo y del bloque `$$SOE` de efemérides | `datos_reales/procesar_dem.py`, `terreno_meta.json` |
| Redacción, edición y traducción | README, guías de Wokwi, guion de presentación y textos de interfaz | `README.md`, `wokwi_simulador/README_WOKWI.md`, `docs/` |
| Diseño visual | Maquetación de la presentación de 7 diapositivas y del HUD (CSS/Three.js) | `diapositivas.html`, `index.html` |
| Investigación / recopilación de información | Localización de la fuente del LDEM Site04 y de los parámetros de consulta del servicio Horizons (`CENTER='coord@301'`, `SITE_COORD='-89.9,0.0,0'`, `COMMAND='10'/'399'`) | `README.md`, `datos_reales/terreno_meta.json` |

## Marcas de agua y reconocimientos

- **Imágenes y vídeos**: NO se generaron imágenes ni vídeos con SI. La única imagen
  del repo (`assets/hero.png`) es una **captura real del visor en ejecución**, tomada
  con navegador automatizado; por eso no lleva marca de agua de SI y así se etiqueta
  en la presentación.
- **Audio**: NO hay audio generado por SI. Los pitidos del HUD son tonos sintetizados
  en tiempo de ejecución con la Web Audio API (código, no contenido generado).
- **Código y datos**: este archivo, la sección 11 del README y los metadatos de
  `index.html` constituyen el reconocimiento descriptivo exigido.
- **Datos científicos**: NO fueron generados ni modificados por SI. El relieve procede
  del producto LRO/LOLA Site04 (Barker et al., 2021) y las efemérides se consultan en
  vivo al servicio Horizons; solo se redujeron/ cuantificaron para su uso en navegador,
  con el error de muestreo documentado.
- **Marca y diseño**: el proyecto no utiliza, contiene ni modifica logotipos, banderas
  ni identificadores de misión de ninguna agencia espacial. El nombre, los topics y la
  documentación del repositorio son neutros; las citas a fuentes de datos son
  atribución científica, no uso de marca.

## Verificación humana

Toda salida asistida por SI fue ejecutada y comprobada en entornos reales:
`node --check`, `py_compile`, compilación contra stub de Arduino, peticiones HTTP a
los endpoints públicos, navegación con Chrome sin cabeza (0 errores de consola) y
lectura de los 524 288 bytes del DEM desde el dominio de producción. Las limitaciones
(firmware no flasheado, cámara sin webcam en el entorno de prueba) se declaran en el
README en lugar de ocultarse.
