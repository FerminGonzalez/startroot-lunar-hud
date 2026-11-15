// ============================================================
// SIMULADOR DE CAMINATA LUNAR — Módulo C++
// NASA Space Apps Challenge 2026 — Polo Sur Lunar (CLPS)
//
// Física de caminata IDÉNTICA al visor HTML (misma inercia 1/6G):
//   vel objetivo adelante  = 0.24 m/frame-equivalente-60fps (≈ 1.44 m/s reales)
//   rampa de inercia       = 0.08 por frame-normalizado (dt*60)
//   giro                   = 1.4 °/frame-normalizado
//   delta-time             = dt normalizado a 60 FPS (mismo código que el visor)
//
// Genera una travesía REAL de larga distancia (decenas de km) por el
// terreno polar sur, dejando "migajas de pan" (breadcrumbs) cada 6 m.
// Salida: datos_caminata.json compatible con el visor 3D.
//
// Compilar:  g++ -O2 -std=c++17 -o simulador_caminata simulador_caminata.cpp
// Ejecutar:  ./simulador_caminata [metros_a_caminar] [archivo_salida]
// ============================================================

#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <vector>
#include <string>
#include <fstream>
#include <sstream>
#include <chrono>
#include <algorithm>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

// ------------------------------------------------------------
// Constantes físicas (misma fuente que el visor HTML)
// ------------------------------------------------------------
static const double G_LUNAR     = 1.62;      // m/s²  gravedad lunar (1/6 de la Tierra)
static const double VEL_AVANCE  = 0.24;      // unidades/frame-normalizado (identico al visor)
static const double VEL_ATRAS   = -0.16;
static const double RAMP_INERCIA= 0.08;      // inercia suave (idéntica al visor)
static const double RAMP_GIRO   = 0.12;
static const double GIRO_VEL    = 1.4;       // °/frame-normalizado
static const double PASO_MIGAS  = 6.0;       // metros entre migajas de pan (idéntico al visor)
static const double LONG_ZANCADA= 0.85;      // factor de ciclo de zancada (idéntico al visor)

// ------------------------------------------------------------
// Terreno polar sur — misma función de alturas que el visor
// ------------------------------------------------------------
static double alturaTerreno(double x, double z)
{
    return std::sin(x * 0.013) * 3.5
         + std::cos(z * 0.011) * 3.0
         + std::sin(x * 0.04 + z * 0.025) * 1.8
         + std::cos(x * 0.07 - z * 0.05) * 1.2;
}

// Pendiente en grados hacia adelante (idéntica al visor)
static double pendienteGrados(double x, double z, double heading)
{
    const double rad = heading * M_PI / 180.0;
    const double h0 = alturaTerreno(x, z);
    const double h1 = alturaTerreno(x + std::sin(rad) * 2.0, z - std::cos(rad) * 2.0);
    return std::fabs((h1 - h0) * 14.0);
}

// Riesgo de cráter/obstáculo: caída de altura brusca delante del astronauta
static bool craterDelante(double x, double z, double heading)
{
    const double rad = heading * M_PI / 180.0;
    for (double d = 3.0; d <= 18.0; d += 3.0) {
        const double h0 = alturaTerreno(x, z);
        const double h1 = alturaTerreno(x + std::sin(rad) * d, z - std::cos(rad) * d);
        if (h1 < h0 - d * 0.45) return true;   // foso profundo
    }
    return false;
}

struct Miga {
    double x, z, elev;
    double pendiente;
    double o2;
    long   tSeg;
    std::string evento;
};

// ------------------------------------------------------------
// Simulación frame a frame — MISMA lógica que el bucle animateLoop()
// ------------------------------------------------------------
struct Estado {
    double posX = 0, posZ = 0;
    double heading = 180;          // sur inicial, igual que el visor
    double velForward = 0, velTurn = 0;
    double walkCycle = 0;
    double distanciaTotal = 0;
    double o2Restante = 100;       // %
    double tSeg = 0;
    std::vector<Miga> migas;
};

// Decide el rumbo: evita cráteres, mantiene rumbo al objetivo (navegación real)
static void decidirAccion(Estado &st, double objX, double objZ, bool &avanzar, int &giro)
{
    const double dx = objX - st.posX;
    const double dz = objZ - st.posZ;
    double anguloObjetivo = std::atan2(dx, -dz) * 180.0 / M_PI;   // misma convención que el visor
    if (anguloObjetivo < 0) anguloObjetivo += 360.0;

    // Giro suave hacia el objetivo (misma señal que las teclas A/D)
    double diff = anguloObjetivo - st.heading;
    while (diff > 180.0)  diff -= 360.0;
    while (diff < -180.0) diff += 360.0;

    giro = 0;
    if (diff > 5.0)  giro = 1;      // girar derecha
    if (diff < -5.0) giro = -1;     // girar izquierda

    avanzar = true;
    // Seguridad astronauta: frena si hay cráter delante o pendiente extrema
    if (craterDelante(st.posX, st.posZ, st.heading)) avanzar = false;
    if (pendienteGrados(st.posX, st.posZ, st.heading) > 28.0) avanzar = false;
    // Si frena por obstáculo y hay que avanzar, esquiva girando a la derecha
    if (!avanzar && giro == 0) giro = 1;
}

int main(int argc, char **argv)
{
    const double distanciaObjetivo = (argc > 1) ? std::atof(argv[1]) : 42000.0;  // 42 km: travesía polar
    const std::string salida = (argc > 2) ? argv[2] : "datos_caminata.json";

    // Destinos de la travesía (misma región del visor + ruta larga):
    // Lander Base → Depósito de hielo → Torre solar → Rover VIPER →
    // Pico de luz eterna → regreso
    struct Destino { double x, z; const char *nombre; };
    const std::vector<Destino> ruta = {
        {    0,  -145, "LANDER BASE" },
        {   65,   -50, "DEPOSITO HIELO SUR" },
        { -120,  -170, "TORRE SOLAR REPETIDORA" },
        {  -45,    40, "ROVER VIPER" },
        {  220,  -420, "PICO LUZ ETERNA" },
        {  610, -1130, "FOSA SHACKLETON NORTE" },
        { 1180, -2380, "COLINA MALAPERT SUR" },
        { 2350, -4820, "VALLE DE SOMBRA PERPETUA" },
        { 4780, -9760, "BASE AVANZADA CLPS-2" },
        { 8600, -18200, "MIRADOR CRATER DE GAUSS" },
        {    0,  -145, "REGRESO A LANDER BASE" }
    };

    Estado st;
    size_t idxDestino = 0;
    double distAcumDesdeMiga = PASO_MIGAS;   // fuerza primera miga en origen

    const auto t0 = std::chrono::steady_clock::now();

    while (st.distanciaTotal < distanciaObjetivo && idxDestino < ruta.size()) {
        // ---- delta-time normalizado (idéntico al visor: f = dt*60, dt máx 0.1 s)
        static double lastMs = -1;
        const double nowMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
        if (lastMs < 0) lastMs = nowMs;
        double dt = (nowMs - lastMs) / 1000.0;
        // En C++ simulamos a 60 FPS fijos (equivalente al visor a 60 FPS)
        dt = 1.0 / 60.0;
        lastMs = nowMs;
        const double f = dt * 60.0;

        bool avanzar = false; int giro = 0;
        decidirAccion(st, ruta[idxDestino].x, ruta[idxDestino].z, avanzar, giro);

        // ¿Llegamos al destino actual? (menos de 8 m)
        const double dDest = std::hypot(ruta[idxDestino].x - st.posX, ruta[idxDestino].z - st.posZ);
        if (dDest < 8.0) {
            Miga m;
            m.x = st.posX; m.z = st.posZ;
            m.elev = alturaTerreno(st.posX, st.posZ);
            m.pendiente = pendienteGrados(st.posX, st.posZ, st.heading);
            m.o2 = st.o2Restante;
            m.tSeg = (long)st.tSeg;
            m.evento = std::string("LLEGADA: ") + ruta[idxDestino].nombre;
            st.migas.push_back(m);
            ++idxDestino;
            continue;
        }

        // ---- MISMA física que el visor (animateLoop)
        const double targetVel = avanzar ? VEL_AVANCE : 0.0;
        const double targetTurn = (giro == -1) ? -GIRO_VEL : ((giro == 1) ? GIRO_VEL : 0.0);
        st.velForward += (targetVel  - st.velForward) * std::min(1.0, RAMP_INERCIA * f);
        st.velTurn    += (targetTurn - st.velTurn)    * std::min(1.0, RAMP_GIRO   * f);

        if (std::fabs(st.velForward) > 0.005 || std::fabs(st.velTurn) > 0.01) {
            st.heading = std::fmod(st.heading + st.velTurn * f + 360.0, 360.0);
            const double rad = st.heading * M_PI / 180.0;
            const double pasoX = std::sin(rad) * st.velForward * f;
            const double pasoZ = -std::cos(rad) * st.velForward * f;
            const double pasoDist = std::hypot(pasoX, pasoZ);
            st.posX += pasoX;
            st.posZ += pasoZ;
            st.walkCycle += std::fabs(st.velForward) * LONG_ZANCADA * f;
            st.distanciaTotal += pasoDist;
            st.tSeg += dt;

            // Consumo de O₂ realista: ~0.52 %/min en traje EVA (tiempo simulado)
            st.o2Restante = std::max(0.0, st.o2Restante - dt * (0.52 / 60.0));

            // ---- Migajas de pan cada 6 m (idéntico al visor)
            distAcumDesdeMiga += pasoDist;
            if (distAcumDesdeMiga >= PASO_MIGAS) {
                distAcumDesdeMiga = 0;
                Miga m;
                m.x = st.posX; m.z = st.posZ;
                m.elev = alturaTerreno(st.posX, st.posZ);
                m.pendiente = pendienteGrados(st.posX, st.posZ, st.heading);
                m.o2 = st.o2Restante;
                m.tSeg = (long)st.tSeg;
                m.evento = "";
                st.migas.push_back(m);
            }
        }
    }

    // ------------------------------------------------------------
    // Exportar JSON (mismo formato que usa el visor)
    // ------------------------------------------------------------
    std::ostringstream json;
    json.setf(std::ios::fixed);
    json.precision(2);
    json << "{\n";
    json << "  \"simulador\": \"C++ - Simulador de Caminata Lunar\",\n";
    json << "  \"gravedad_m_s2\": " << G_LUNAR << ",\n";
    json << "  \"distancia_total_m\": " << st.distanciaTotal << ",\n";
    json << "  \"tiempo_total_s\": " << (long)st.tSeg << ",\n";
    json << "  \"o2_restante_pct\": " << st.o2Restante << ",\n";
    json << "  \"migajas\": " << st.migas.size() << ",\n";
    json << "  \"trail\": [\n";
    for (size_t i = 0; i < st.migas.size(); ++i) {
        const Miga &m = st.migas[i];
        json << "    {\"x\": " << m.x << ", \"z\": " << m.z
             << ", \"y\": " << m.elev
             << ", \"pendiente\": " << m.pendiente
             << ", \"o2\": " << m.o2
             << ", \"t\": " << m.tSeg
             << ", \"evento\": \"" << m.evento << "\"}"
             << (i + 1 < st.migas.size() ? "," : "") << "\n";
    }
    json << "  ]\n}\n";

    std::ofstream out(salida);
    if (!out) { std::fprintf(stderr, "ERROR: no se pudo escribir %s\n", salida.c_str()); return 1; }
    out << json.str();
    out.close();

    std::printf("SIMULACION C++ COMPLETA\n");
    std::printf("  Distancia caminada : %.1f m (%.2f km)\n", st.distanciaTotal, st.distanciaTotal / 1000.0);
    std::printf("  Tiempo EVA         : %ld min %ld s\n", (long)(st.tSeg / 60), (long)st.tSeg % 60);
    std::printf("  O2 restante        : %.1f %%\n", st.o2Restante);
    std::printf("  Migajas de pan     : %zu\n", st.migas.size());
    std::printf("  Destinos alcanzados: %zu/%zu\n", idxDestino, ruta.size());
    std::printf("  Salida             : %s\n", salida.c_str());
    return (st.o2Restante > 0 && idxDestino == ruta.size()) ? 0 : 2;
}
