"""
fetch.py - Fetcher HTTP robusto con cache en disco.

Por que existe: worldfootball.net (y otras fuentes) aplican bot-detection
inconsistente (la misma URL devuelve 200 y, segundos despues, 403). Para no
pelear esa deteccion mas de una vez por pagina, cacheamos a disco cada
respuesta exitosa. El parseo posterior trabaja siempre sobre el cache.

Estrategia:
- requests.Session (mantiene cookies entre requests; muchas defensas anti-bot
  setean una cookie en la home y la exigen luego).
- "Calienta" cookies visitando la home antes de pedir paginas internas.
- Rota User-Agent y manda headers de navegador realistas.
- Reintentos con backoff exponencial + jitter ante 403/429/5xx.
- Pausa aleatoria entre fetches en vivo (cortesia / evitar rate-limit).
"""
import hashlib
import os
import random
import time

import requests

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def _headers(referer):
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        "Referer": referer,
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


def _cache_path(url):
    h = hashlib.md5(url.encode("utf-8")).hexdigest()[:16]
    # nombre legible + hash para evitar colisiones / chars invalidos en Windows
    slug = url.rstrip("/").split("/")[-1][:60].replace(":", "_")
    return os.path.join(CACHE_DIR, f"{slug}__{h}.html")


class Fetcher:
    def __init__(self, base="https://www.worldfootball.net/", min_delay=2.5, max_delay=5.0):
        self.base = base
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.s = requests.Session()
        self._warmed = False

    def _warm(self):
        """Visita la home para obtener cookies de sesion antes de paginas internas."""
        if self._warmed:
            return
        try:
            self.s.get(self.base, headers=_headers(self.base), timeout=25)
        except Exception:
            pass
        self._warmed = True
        time.sleep(random.uniform(1.0, 2.0))

    def get(self, url, force=False, max_retries=5):
        """Devuelve el HTML de `url`, usando cache si existe.

        Retorna (html, from_cache, status). html=None si fallo definitivamente.
        """
        cp = _cache_path(url)
        if not force and os.path.exists(cp):
            with open(cp, "r", encoding="utf-8") as f:
                return f.read(), True, 200

        self._warm()
        referer = self.base
        backoff = 3.0
        for attempt in range(max_retries):
            try:
                r = self.s.get(url, headers=_headers(referer), timeout=30)
                if r.status_code == 200 and len(r.text) > 500:
                    with open(cp, "w", encoding="utf-8") as f:
                        f.write(r.text)
                    time.sleep(random.uniform(self.min_delay, self.max_delay))
                    return r.text, False, 200
                if r.status_code == 404:
                    return None, False, 404  # no existe: no reintentar
                # 403 / 429 / 5xx: backoff y reintento
                time.sleep(backoff + random.uniform(0, 2.0))
                backoff *= 1.8
                self._warmed = False
                self._warm()  # re-calentar cookies
            except Exception:
                time.sleep(backoff + random.uniform(0, 2.0))
                backoff *= 1.8
        return None, False, -1


if __name__ == "__main__":
    f = Fetcher()
    html, cached, status = f.get("https://www.worldfootball.net/competition/arg-primera-b-nacional/")
    print("status", status, "cached", cached, "len", len(html) if html else None)
