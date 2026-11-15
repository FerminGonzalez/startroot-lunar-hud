/**
 * ============================================================================
 * StartRoot — Proxy de efemérides Horizons con CORS (Cloudflare Worker)
 * ============================================================================
 * Problema que resuelve: en el visor alojado en Cloudflare Pages (estático),
 * el navegador no puede llamar directamente a
 *   https://ssd.jpl.nasa.gov/api/horizons.api
 * porque el servicio de efemérides no envía cabeceras CORS (Access-Control-Allow-Origin).
 *
 * Este Worker hace de puente:
 *   - Recibe la MISMA query que horizons.api (COMMAND='10' Sol, '399' Tierra…)
 *   - La reenvía al servicio de efemérides y devuelve la respuesta con CORS abierto
 *   - Cache de 5 min por query (las efemérides cambian poco en 30 min)
 *
 * Uso:  https://<este-worker>/api/horizons.api?format=text&COMMAND='10'&...
 * (idéntico a horizons.api — el visor solo cambia el dominio)
 */

export default {
  async fetch(request) {
    const url = new URL(request.url);

    // Preflight CORS
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, OPTIONS',
          'Access-Control-Allow-Headers': '*',
          'Access-Control-Max-Age': '86400',
        },
      });
    }

    if (url.pathname === '/api/horizons.api' || url.pathname === '/horizons') {
      const target = 'https://ssd.jpl.nasa.gov/api/horizons.api' + url.search;
      try {
        const r = await fetch(target, { cf: { cacheTtl: 300, cacheEverything: true } });
        const resp = new Response(r.body, { status: r.status });
        resp.headers.set('Access-Control-Allow-Origin', '*');
        resp.headers.set('Content-Type', 'text/plain; charset=utf-8');
        resp.headers.set('Cache-Control', 'public, max-age=300');
        return resp;
      } catch (err) {
        return new Response('StartRoot proxy: efemérides inalcanzables: ' + String(err), {
          status: 502,
          headers: { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'text/plain; charset=utf-8' },
        });
      }
    }

    return new Response(
      'StartRoot — proxy de efemérides Horizons (con CORS).\n' +
      'Uso: /api/horizons.api?format=text&COMMAND=\'10\'&CENTER=\'coord@301\'&SITE_COORD=\'-89.9,0.0,0\'&...\n',
      { status: 200, headers: { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'text/plain; charset=utf-8' } }
    );
  },
};
