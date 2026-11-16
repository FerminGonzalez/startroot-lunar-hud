# Presentation

## Slide 1 · Title — "LUNAR VISOR"

> "This is not an instrument panel. We brought a helmet. A visor where the decision appears drawn on the ground you are about to walk on. Open it and walk: no install, no sign-up, no server."


## Slide 2 · Introduction

> "At the south pole, the Sun sits at −73.7 degrees: shadows that never end. The Earth drifts in and out of line of sight, so the direct link drops without warning. And there is no GPS. Every detour is paid twice: in oxygen and in kilocalories. An astronaut with forty numbers in front of them is not safer: they are busier."

> "They need the right decision, already projected onto the terrain."

## Slide 3 · The idea — "One visor. All in one"

> "First person, one sixth G inertia, two curved arrows with chevrons that adapt to the terrain, laser rangefinder, 180-degree rear camera, tactical wrist display and the alert system — all living in the same frame. One single file. One single link."

## Slide 4 · Real terrain

> "We did not model the crater with a sine wave. We downloaded the LRO/LOLA LDEM from the Shackleton rim at 5 metres per pixel, converted it into 512 by 512 real heights — exactly 524,288 bytes — and served it to the browser. The altitude you see, 758.4 metres, is the real altitude. The 41-kilometre route of the C++ simulator is recomputed over that relief. And we measured the sampling error: 0.406 metres. If the data is missing, the HUD admits it and says SIMULATED. That is engineering too."

## Slide 5 · Five layers of engineering

> "One: metabolic A* — slopes steeper than 25 degrees and rocks enter the cost, and the oxygen savings and kcal per minute are shown on screen, not assumed. Two: computer vision with Canny implemented in pure JavaScript, tactical boxes over real objects from the webcam. Three: ephemerides queried live; when the Earth sets, the visor switches to the relay on its own. Four: Caution & Warning classes 1, 2 and 3 with monochrome fail-safe at 20 frames per second. Five: bidirectional telemetry with an ESP32, demonstrable in Wokwi without owning the board."

> "Five layers. One single render loop. And we never touched the movement physics."

## Slide 6 · Verified evidence

> "Zero console errors in production. The DEM arrives complete over HTTPS. Sun: azimuth 264.4 degrees, elevation −73.7. Earth: +3.4 degrees, direct link active. Firmware compiled without warnings, 63 telemetry frames validated, Wokwi diagram checked against the official pinout."
> "And what we could NOT test is written in the repo too: we did not flash a physical board and the test browser had no webcam. I would rather say it myself than have the jury discover it."

It already works. What comes next is making it bigger.

## Slide 7 · Closing

> "Today anyone opens a link and walks across Shackleton. Tomorrow: more landing sites with their own real relief, a metabolic profile per astronaut, A* route export and the same telemetry on real hardware."
> "We did not come to show a render. We came to leave a tool running on the web. Open it: WASD to move, TAB for the wrist, M for emergency mode. StartRoot.
>
> Thank you."
