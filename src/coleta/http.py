"""Cliente HTTP compartilhado pelos coletores.

Três regras valem para toda requisição do BELUGA:

1. User-Agent identificado (`src.config.USER_AGENT`), com link do projeto.
2. robots.txt respeitado. O arquivo é lido uma vez por host; caminho proibido
   levanta `BloqueadoPorRobots` sem tocar na URL. `Crawl-Delay` vira
   intervalo mínimo entre requisições ao host. robots.txt ausente (4xx) libera
   o host; robots.txt que não responde (5xx, rede) bloqueia a coleta, porque
   na dúvida não se coleta. A única exceção é opcional e explícita
   (`robots_inacessivel_bloqueia=False`), usada só para a API de malhas do
   IBGE: é uma API pública documentada para consumo automatizado, e o
   robots.txt de servicodados.ibge.gov.br não responde (conferido em
   2026-11-21). Se ele voltar a responder, o que disser vale.
3. Taxa limitada por host: `intervalo_minimo` entre o início de duas
   requisições ao mesmo host, ou o Crawl-Delay, o que for maior.

Falha transitória (rede, 429, 5xx, erro do ArcGIS com HTTP 200) é retentada
com espera exponencial. Os tempos são generosos de propósito, como no ORCA:
a coleta roda uma vez por mês e servidores públicos brasileiros alcançados da
rede do GitHub respondem devagar.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from src.config import USER_AGENT

logger = logging.getLogger(__name__)


class ColetaError(RuntimeError):
    """A fonte não entregou o dado (fora do ar, vazia, truncada, formato mudou)."""


class BloqueadoPorRobots(ColetaError):
    """O robots.txt do host proíbe o caminho para o User-Agent do BELUGA."""


class _Transitoria(Exception):
    """Falha que vale tentar de novo."""


STATUS_RETENTAVEIS = {429, 500, 502, 503, 504}
ROBOTS_INACESSIVEL = "inacessivel"


class Cliente:
    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: float = 120.0,
        max_tentativas: int = 5,
        backoff: float = 5.0,
        dormir: Callable[[float], None] = time.sleep,
        relogio: Callable[[], float] = time.monotonic,
        robots_inacessivel_bloqueia: bool = True,
        timeout_robots: float = 20.0,
    ) -> None:
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.timeout = timeout
        self.max_tentativas = max_tentativas
        self.backoff = backoff
        self._dormir = dormir
        self._relogio = relogio
        self.robots_inacessivel_bloqueia = robots_inacessivel_bloqueia
        self.timeout_robots = timeout_robots
        # None = host sem robots.txt; ROBOTS_INACESSIVEL = não respondeu.
        self._robots: dict[str, RobotFileParser | str | None] = {}
        self._ultima: dict[str, float] = {}

    # ------------------------------------------------------------ robots.txt
    def _robots_do_host(self, base: str) -> RobotFileParser | str | None:
        """Parser do robots.txt de `base`, None se não há arquivo, ou
        `ROBOTS_INACESSIVEL`. O resultado fica guardado por host, inclusive a
        falha: sem isso cada URL repetiria minutos de espera."""
        if base in self._robots:
            return self._robots[base]
        url = f"{base}/robots.txt"

        def fazer() -> requests.Response:
            try:
                resp = self.session.get(url, timeout=self.timeout_robots)
            except requests.RequestException as exc:
                raise _Transitoria(str(exc)) from exc
            if resp.status_code in STATUS_RETENTAVEIS:
                raise _Transitoria(f"HTTP {resp.status_code}")
            return resp

        resultado: RobotFileParser | str | None
        tentativas, self.max_tentativas = self.max_tentativas, min(self.max_tentativas, 2)
        try:
            resp = self._com_retentativa(fazer, url, checar_robots=False)
        except ColetaError:
            resultado = ROBOTS_INACESSIVEL
        else:
            if resp.status_code >= 400:
                resultado = None
            else:
                resultado = RobotFileParser()
                resultado.parse(resp.text.splitlines())
        finally:
            self.max_tentativas = tentativas
        self._robots[base] = resultado
        return resultado

    def _crawl_delay(self, base: str) -> float:
        parser = self._robots.get(base)
        if not isinstance(parser, RobotFileParser):
            return 0.0
        valor = parser.crawl_delay(USER_AGENT)
        return float(valor) if valor else 0.0

    def checar_robots(self, url: str) -> None:
        partes = urlsplit(url)
        base = f"{partes.scheme}://{partes.netloc}"
        parser = self._robots_do_host(base)
        if parser == ROBOTS_INACESSIVEL:
            if self.robots_inacessivel_bloqueia:
                raise ColetaError(f"robots.txt de {partes.netloc} não respondeu; coleta bloqueada")
            logger.warning("robots.txt de %s não respondeu; seguindo (exceção explícita).", partes.netloc)
            return
        if isinstance(parser, RobotFileParser) and not parser.can_fetch(USER_AGENT, url):
            raise BloqueadoPorRobots(f"robots.txt de {partes.netloc} proíbe {partes.path}")

    # ------------------------------------------------------------- requisição
    def _esperar_vez(self, base: str, intervalo_minimo: float) -> None:
        intervalo = max(intervalo_minimo, self._crawl_delay(base))
        anterior = self._ultima.get(base)
        if anterior is not None:
            falta = intervalo - (self._relogio() - anterior)
            if falta > 0:
                self._dormir(falta)
        self._ultima[base] = self._relogio()

    def _requisitar(self, url: str, params: dict[str, Any] | None) -> requests.Response:
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise _Transitoria(str(exc)) from exc
        if resp.status_code in STATUS_RETENTAVEIS:
            raise _Transitoria(f"HTTP {resp.status_code}")
        return resp

    def _com_retentativa(
        self, fazer: Callable[[], requests.Response], url: str, checar_robots: bool = True,
        intervalo_minimo: float = 1.0,
    ) -> requests.Response:
        partes = urlsplit(url)
        base = f"{partes.scheme}://{partes.netloc}"
        ultimo: Exception | None = None
        for tentativa in range(1, self.max_tentativas + 1):
            if checar_robots:
                self._esperar_vez(base, intervalo_minimo)
            try:
                return fazer()
            except _Transitoria as exc:
                ultimo = exc
                espera = self.backoff * (2 ** (tentativa - 1))
                logger.warning(
                    "Falha em %s (tentativa %d/%d): %s. Aguardando %.1fs.",
                    url, tentativa, self.max_tentativas, exc, espera,
                )
                if tentativa < self.max_tentativas:
                    self._dormir(espera)
        raise ColetaError(f"{url} não respondeu após {self.max_tentativas} tentativas: {ultimo}")

    def get(
        self, url: str, params: dict[str, Any] | None = None, intervalo_minimo: float = 1.0,
    ) -> requests.Response:
        """GET com robots.txt, taxa por host e retentativa. 4xx vira `ColetaError` na hora."""
        self.checar_robots(url)
        resp = self._com_retentativa(
            lambda: self._requisitar(url, params), url, intervalo_minimo=intervalo_minimo,
        )
        if resp.status_code >= 400:
            raise ColetaError(f"{url} respondeu HTTP {resp.status_code}")
        return resp

    def get_json(
        self, url: str, params: dict[str, Any] | None = None, intervalo_minimo: float = 1.0,
    ) -> dict[str, Any]:
        """GET que espera JSON. O ArcGIS devolve erro transitório com HTTP 200
        (`{"error": ...}`), então isso também é retentado."""

        def fazer() -> requests.Response:
            resp = self._requisitar(url, params)
            if resp.status_code >= 400:
                return resp
            try:
                corpo = resp.json()
            except ValueError as exc:
                raise _Transitoria(f"resposta não é JSON: {resp.text[:120]!r}") from exc
            if isinstance(corpo, dict) and "error" in corpo:
                raise _Transitoria(f"serviço devolveu erro: {corpo['error']}")
            return resp

        self.checar_robots(url)
        resp = self._com_retentativa(fazer, url, intervalo_minimo=intervalo_minimo)
        if resp.status_code >= 400:
            raise ColetaError(f"{url} respondeu HTTP {resp.status_code}")
        corpo = resp.json()
        if not isinstance(corpo, dict):
            raise ColetaError(f"{url} devolveu JSON que não é objeto")
        return corpo
