# Guion de presentación — 7 diapositivas (≈4 min)

**Reglas de oro**: una idea por diapositiva, una cifra por frase, nunca leer la pantalla.
Arranca con la demo **ya abierta en otra pestaña** (`https://gestion2026.online`) para
pasar a ella en el minuto 2:30. La baraja se navega con ← →.

---

## Diapositiva 1 · Portada — «VISOR LUNAR» (0:00 – 0:20)

**Se dice:**
> «No trajimos un panel de instrumentos. Trajimos un casco. Un visor donde la decisión aparece dibujada sobre el suelo que vas a pisar. Ábrelo y camina: sin instalar, sin registro, sin servidor.»

**Visual:** título gigante, subtítulo, URL de la demo.
**Tono:** pausado, sin prisa. Dejar 3 segundos de silencio después de «un casco».
**Transición:** «¿Y por qué hace falta un casco y no una tabla?»

---

## Diapositiva 2 · Introducción / El reto (0:20 – 0:55)

**Se dice:**
> «En el polo sur, el Sol está a −73,7 grados: sombras que no terminan. La Tierra entra y sale de la línea de visión, así que el enlace directo se cae sin avisar. Y no hay GPS. Cada rodeo se paga dos veces: en oxígeno y en kilocalorías. Un astronauta con cuarenta números delante no está más seguro: está más ocupado.»

**Remate (frase para recordar):**
> «Necesita la decisión correcta, ya proyectada sobre el terreno.»

**Visual:** tres tarjetas (−73,7° / 0 / O₂). Señalar la tercera con la mano.
**Transición:** «Entonces metimos todo dentro del campo de visión.»

---

## Diapositiva 3 · La idea — «Un visor. Todo dentro.» (0:55 – 1:30)

**Se dice:**
> «Primera persona, inercia de un sexto de G, dos flechas curvas con chevrons que se adaptan al relieve, retícula láser, cámara trasera de 180 grados, pantalla táctica en la muñeca y el sistema de alertas — todo conviviendo en el mismo fotograma. Un solo archivo. Un solo enlace.»

**Aquí se cambia a la demo en vivo** (30 s de caminata real con WASD, abrir TAB, pulsar M y volver):
> «Esto no es una maqueta: es la misma página que están viendo, corriendo en producción ahora mismo.»

**Visual:** captura real + chips de teclas. Mencionar que la captura es real, no generada.
**Transición:** «Lo primero que hicimos fue quitar el paisaje falso.»

---

## Diapositiva 4 · Terreno real (1:30 – 2:05)

**Se dice:**
> «No modelamos el cráter con una función seno. Descargamos el LDEM de LRO/LOLA del borde de Shackleton a 5 metros por píxel, lo convertimos en 512 por 512 alturas reales —524 288 bytes exactos— y lo servimos al navegador. La altitud que ves, 758,4 metros, es la altitud real. La ruta de 41 kilómetros del simulador C++ se recalcula sobre ese relieve. Y medimos el error de muestreo: 0,406 metros. Si faltan los datos, el HUD lo admite y dice SIMULADO. Eso también es ingeniería.»

**Visual:** las tres cifras grandes. No leer la tabla; solo la cifra de 0,406 m.
**Transición:** «Sobre ese suelo real, cinco capas toman decisiones.»

---

## Diapositiva 5 · Cinco capas de ingeniería (2:05 – 2:50)

**Se dice (ritmo rápido, una por línea, marcando con el dedo):**
> «Uno: A* metabólico — pendientes de más de 25 grados y rocas entran en el coste, y el ahorro de oxígeno y las kcal por minuto se ven en pantalla, no se presumen. Dos: visión artificial con Canny implementado en JavaScript puro, cajas tácticas sobre objetos reales de la webcam. Tres: efemérides consultadas en vivo; cuando la Tierra se oculta, el visor conmuta solo al relé. Cuatro: Caution & Warning clases 1, 2 y 3 con modo fail-safe monocromo a 20 fotogramas. Cinco: telemetría bidireccional con un ESP32, demostrable en Wokwi sin tener la placa.»

**Remate:**
> «Cinco capas. Un solo bucle de render. Y la física de movimiento no la tocamos.»

**Transición:** «Y ahora, la parte que casi nadie enseña: la evidencia.»

---

## Diapositiva 6 · Evidencia verificada (2:50 – 3:25)

**Se dice:**
> «Cero errores de consola en producción. El DEM llega completo por HTTPS. Sol: azimut 264,4 grados, elevación −73,7. Tierra: +3,4 grados, enlace directo activo. Firmware compilado sin warnings, 63 tramas de telemetría validadas, diagrama de Wokwi contra el pinout oficial.»
> «Y lo que NO pudimos probar también está escrito en el repo: no flasheamos una placa física y el navegador de pruebas no tenía webcam. Prefiero decirlo yo a que lo descubra el jurado.»

**Visual:** chips verdes. Al decir la última frase, bajar el tono — genera más credibilidad que cualquier superlativo.
**Transición:** «Esto ya funciona. Lo que sigue es hacerlo más grande.»

---

## Diapositiva 7 · Cierre (3:25 – 4:00)

**Se dice:**
> «Hoy cualquiera abre un enlace y camina sobre Shackleton. Mañana: más sitios de aterrizaje con sus propios relieve real, perfil metabólico por astronauta, exportación de la ruta A* y la misma telemetría en una placa de verdad.»
> «No vinimos a enseñar un render. Vinimos a dejar una herramienta funcionando en la web. Ábranla: WASD para avanzar, TAB para la muñeca, M para la emergencia. StartRoot. Gracias.»

**Visual:** CTA con la URL completa. Dejar la diapositiva en pantalla para preguntas; tener el repo abierto en otra pestaña.

---

## Notas de producción

- **≤7 diapositivas** ✔ (portada e introducción incluidas). La baraja HTML está en
  `diapositivas.html` y se publica en `https://gestion2026.online/diapositivas.html`.
- **Sin vídeo**: la demo en vivo sustituye al vídeo de 30 s; si el jurado pide vídeo,
  grabar 25 s con el guion de la diapositiva 3 (caminar → TAB → M → volver).
- **Prohibido en pantalla**: logos, banderas o identificadores de misión; ninguna
  imagen generada por SI. La única imagen es una captura real y va etiquetada como tal.
- **Si algo falla en directo**: la demo degrada sola (terreno estático + efemérides
  etiquetadas SIM). Decirlo en voz alta: está diseñado para fallar con elegancia.
