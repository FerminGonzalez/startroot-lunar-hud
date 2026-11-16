#presentación


## Diapositiva 1 · Portada — «VISOR LUNAR» (0:00 – 0:20)

> «No es un panel de instrumentos. Trajimos un casco. Un visor donde la decisión aparece dibujada sobre el suelo que vas a pisar. Ábrelo y camina: sin instalar, sin registro, sin servidor.»


## Diapositiva 2 · Introducción 

> «En el polo sur, el Sol está a −73,7 grados: sombras que no terminan. La Tierra entra y sale de la línea de visión, así que el enlace directo se cae sin avisar. Y no hay GPS. Cada rodeo se paga dos veces: en oxígeno y en kilocalorías. Un astronauta con cuarenta números delante no está más seguro: está más ocupado.»

> «Necesita la decisión correcta, ya proyectada sobre el terreno.»

## Diapositiva 3 · La idea — «Un visor. Todo en uno

> «Primera persona, inercia de un sexto de G, dos flechas curvas con chevrons que se adaptan al relieve, retícula láser, cámara trasera de 180 grados, pantalla táctica en la muñeca y el sistema de alertas — todo conviviendo en el mismo fotograma. Un solo archivo. Un solo enlace.»

## Diapositiva 4 · Terreno real 

> «No modelamos el cráter con una función seno. Descargamos el LDEM de LRO/LOLA del borde de Shackleton a 5 metros por píxel, lo convertimos en 512 por 512 alturas reales —524 288 bytes exactos— y lo servimos al navegador. La altitud que ves, 758,4 metros, es la altitud real. La ruta de 41 kilómetros del simulador C++ se recalcula sobre ese relieve. Y medimos el error de muestreo: 0,406 metros. Si faltan los datos, el HUD lo admite y dice SIMULADO. Eso también es ingeniería.»

## Diapositiva 5 · Cinco capas de ingeniería

> «Uno: A* metabólico — pendientes de más de 25 grados y rocas entran en el coste, y el ahorro de oxígeno y las kcal por minuto se ven en pantalla, no se presumen. Dos: visión artificial con Canny implementado en JavaScript puro, cajas tácticas sobre objetos reales de la webcam. Tres: efemérides consultadas en vivo; cuando la Tierra se oculta, el visor conmuta solo al relé. Cuatro: Caution & Warning clases 1, 2 y 3 con modo fail-safe monocromo a 20 fotogramas. Cinco: telemetría bidireccional con un ESP32, demostrable en Wokwi sin tener la placa.»

> «Cinco capas. Un solo bucle de render. Y la física de movimiento no la tocamos.»

## Diapositiva 6 · Evidencia verificada 

> «Cero errores de consola en producción. El DEM llega completo por HTTPS. Sol: azimut 264,4 grados, elevación −73,7. Tierra: +3,4 grados, enlace directo activo. Firmware compilado sin warnings, 63 tramas de telemetría validadas, diagrama de Wokwi contra el pinout oficial.»
> «Y lo que NO pudimos probar también está escrito en el repo: no flasheamos una placa física y el navegador de pruebas no tenía webcam. Prefiero decirlo yo a que lo descubra el jurado.»

ya funciona. Lo que sigue es hacerlo más grande.

## Diapositiva 7 · Cierre 

> «Hoy cualquiera abre un enlace y camina sobre Shackleton. Mañana: más sitios de aterrizaje con sus propios relieve real, perfil metabólico por astronauta, exportación de la ruta A* y la misma telemetría en una placa de verdad.»
> «No vinimos a enseñar un render. Vinimos a dejar una herramienta funcionando en la web. Ábranla: WASD para avanzar, TAB para la muñeca, M para la emergencia. StartRoot.
>
> Gracias.»

