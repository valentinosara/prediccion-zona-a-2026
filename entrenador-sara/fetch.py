"""
fetch.py - Fetcher HTTP robusto con cache en disco, para Transfermarkt.

Por que existe: Transfermarkt tiene deteccion anti-bot mas estricta que
worldfootball.net. Para no pelear esa deteccion mas de una vez por pagina,
cacheamos a disco cada respuesta exitosa. El parseo posterior (parse.py)
trabaja siempre sobre el cache.

Estrategia (misma base que rachas-primera-nacional/fetch.py, endurecida para
la corrida completa de ~156 partidos):
- requests.Session (mantiene cookies entre requests).
- "Calienta" cookies visitando la home antes de pedir paginas internas.
- Un User-Agent FIJO por sesion (elegido una vez en __init__, locale en-US ya
  que el host base es el mirror .us de Transfermarkt): rotarlo en cada
  request de una sesion que ya arrastra cookies es una señal de deteccion,
  no una forma de evitarla.
- Reintentos con backoff exponencial + jitter ante 403/429/5xx, body corto/
  vacio, o contenido que no pasa el `validator` esperado para esa pagina
  (bot-detection/interstitial servido con status 200 - ver `get()`).
- Circuit breaker: si se acumulan demasiados `get()` consecutivos fallados
  del todo, aborta (raise) en vez de seguir moliendo ~70s/URL contra un host
  que ya esta bloqueando.
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

# Cuantos get() consecutivos deben fallar del todo (agotando sus propios
# reintentos) antes de abortar la corrida completa en vez de seguir
# moliendo URL por URL contra un host que ya esta bloqueando.
CIRCUIT_BREAKER_THRESHOLD = 8


def _cache_path(url):
    h = hashlib.md5(url.encode("utf-8")).hexdigest()[:16]
    # nombre legible + hash para evitar colisiones / chars invalidos en Windows
    slug = url.rstrip("/").split("/")[-1][:60].replace(":", "_")
    return os.path.join(CACHE_DIR, f"{slug}__{h}.html")


class Fetcher:
    def __init__(self, base="https://www.transfermarkt.us/", min_delay=2.5, max_delay=5.0):
        self.base = base
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.s = requests.Session()
        self._warmed = False
        # UA fijo para toda la vida de la sesion (ver docstring del modulo).
        self.user_agent = random.choice(_USER_AGENTS)
        self._consecutive_failures = 0

    def _headers(self, referer):
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
            "Referer": referer,
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    def _warm(self):
        """Visita la home para obtener cookies de sesion antes de paginas internas."""
        if self._warmed:
            return
        try:
            self.s.get(self.base, headers=self._headers(self.base), timeout=25)
        except Exception:
            pass
        self._warmed = True
        time.sleep(random.uniform(1.0, 2.0))

    def get(self, url, force=False, max_retries=5, validator=None):
        """Devuelve el HTML de `url`, usando cache si existe.

        `validator`: callable opcional `html_text -> bool`. Si se pasa, una
        respuesta 200 con body largo ADEMAS debe pasar `validator` para
        aceptarse y cachearse; si no la pasa (tipico de una pagina de
        bot-detection/interstitial servida con status 200 y body grande) se
        trata como un fetch fallido mas: reintenta, y si se agotan los
        reintentos devuelve status=-1 SIN escribir nada a cache.

        Retorna (html, from_cache, status). html=None si fallo definitivamente.
        """
        cp = _cache_path(url)
        if not force and os.path.exists(cp):
            with open(cp, "r", encoding="utf-8") as f:
                return f.read(), True, 200

        self._warm()
        referer = self.base
        backoff = 3.0
        rewarmed = False
        for attempt in range(max_retries):
            try:
                r = self.s.get(url, headers=self._headers(referer), timeout=30)
            except Exception:
                r = None

            if r is not None:
                if (r.status_code == 200 and len(r.text) > 500
                        and (validator is None or validator(r.text))):
                    with open(cp, "w", encoding="utf-8") as f:
                        f.write(r.text)
                    time.sleep(random.uniform(self.min_delay, self.max_delay))
                    self._consecutive_failures = 0
                    return r.text, False, 200
                if r.status_code == 404:
                    self._consecutive_failures = 0  # el host responde: no es un bloqueo
                    return None, False, 404  # no existe: no reintentar

            # 403/429/5xx, body corto/vacio, contenido que no pasa `validator`,
            # o excepcion de red: backoff y reintento.
            time.sleep(backoff + random.uniform(0, 2.0))
            backoff *= 1.8
            if not rewarmed:
                # re-calentar cookies UNA sola vez (no en cada intento: eso
                # duplicaria la carga sobre un host que ya esta bloqueando).
                self._warmed = False
                self._warm()
                rewarmed = True

        self._consecutive_failures += 1
        if self._consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
            raise RuntimeError(
                f"Fetcher: {self._consecutive_failures} fetches consecutivos "
                f"fallaron del todo (ultima url: {url}). Probable bloqueo/ban "
                f"del host: abortando en vez de seguir moliendo el resto de "
                f"la cola."
            )
        return None, False, -1


if __name__ == "__main__":
    f = Fetcher()
    html, cached, status = f.get("https://www.transfermarkt.us/juan-sara/profil/trainer/94335")
    print("status", status, "cached", cached, "len", len(html) if html else None)
