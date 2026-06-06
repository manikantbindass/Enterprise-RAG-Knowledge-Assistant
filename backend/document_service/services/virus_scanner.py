"""
ClamAV virus scanner integration via pyclamd.

Graceful fallback: if ClamAV daemon unreachable, logs warning and allows file
(configurable). Never blocks uploads silently — always logs decision.
"""

from __future__ import annotations

import asyncio
import time
from functools import lru_cache

import structlog

logger = structlog.get_logger(__name__)


class VirusScanResult:
    """Result of a virus scan operation."""

    __slots__ = ("is_clean", "virus_name", "scan_time_ms", "scanner_available")

    def __init__(
        self,
        is_clean: bool,
        virus_name: str | None = None,
        scan_time_ms: float = 0.0,
        scanner_available: bool = True,
    ) -> None:
        self.is_clean = is_clean
        self.virus_name = virus_name
        self.scan_time_ms = scan_time_ms
        self.scanner_available = scanner_available


class VirusScannerService:
    """
    ClamAV integration via pyclamd.

    Runs scans in a thread pool executor to avoid blocking the async event loop
    (pyclamd is synchronous). Falls back to allow-all if ClamAV is not reachable,
    but emits a structured warning so ops teams know scanning is degraded.
    """

    def __init__(self, host: str, port: int, timeout: int = 30) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._clamd: object | None = None
        self._available: bool = False

    def _init_clamd(self) -> None:
        """Attempt to connect to ClamAV daemon (blocking, called in executor)."""
        try:
            import pyclamd  # type: ignore[import-untyped]

            cd = pyclamd.ClamdNetworkSocket(
                host=self._host,
                port=self._port,
                timeout=self._timeout,
            )
            cd.ping()
            self._clamd = cd
            self._available = True
            logger.info(
                "clamav_connected",
                host=self._host,
                port=self._port,
                version=cd.version(),
            )
        except Exception as exc:
            self._available = False
            logger.warning(
                "clamav_unavailable",
                host=self._host,
                port=self._port,
                error=str(exc),
                fallback="allow_upload",
            )

    async def initialize(self) -> None:
        """Connect to ClamAV in executor (non-blocking)."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._init_clamd)

    def _scan_bytes_sync(self, content: bytes) -> VirusScanResult:
        """Blocking scan — must run in executor."""
        if not self._available or self._clamd is None:
            return VirusScanResult(
                is_clean=True,
                scanner_available=False,
                scan_time_ms=0.0,
            )

        start = time.monotonic()
        try:
            import pyclamd  # type: ignore[import-untyped]

            result = self._clamd.scan_stream(content)  # type: ignore[union-attr]
            elapsed = (time.monotonic() - start) * 1000

            if result is None:
                # No threats found
                return VirusScanResult(
                    is_clean=True,
                    scan_time_ms=elapsed,
                    scanner_available=True,
                )

            # result = {'stream': ('FOUND', 'Eicar-Test-Signature')}
            _status, virus_name = next(iter(result.values()))
            logger.warning(
                "virus_detected",
                virus_name=virus_name,
                scan_time_ms=elapsed,
            )
            return VirusScanResult(
                is_clean=False,
                virus_name=virus_name,
                scan_time_ms=elapsed,
                scanner_available=True,
            )

        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            logger.error(
                "virus_scan_error",
                error=str(exc),
                fallback="allow_upload",
            )
            # Treat scan errors as clean to avoid blocking uploads
            # (ops team notified via error log)
            return VirusScanResult(
                is_clean=True,
                scan_time_ms=elapsed,
                scanner_available=False,
            )

    async def scan_file(self, content: bytes) -> VirusScanResult:
        """
        Scan file content for viruses.

        Args:
            content: Raw file bytes to scan.

        Returns:
            VirusScanResult with is_clean=True if safe (or scanner degraded).
        """
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._scan_bytes_sync, content)

        log = logger.bind(
            size_bytes=len(content),
            scan_time_ms=result.scan_time_ms,
            scanner_available=result.scanner_available,
        )

        if not result.scanner_available:
            log.warning("virus_scan_skipped_scanner_unavailable")
        elif result.is_clean:
            log.info("virus_scan_clean")
        else:
            log.warning("virus_scan_infected", virus_name=result.virus_name)

        return result

    @property
    def is_available(self) -> bool:
        """Return True if ClamAV daemon is reachable."""
        return self._available


@lru_cache(maxsize=1)
def get_virus_scanner(host: str, port: int, timeout: int = 30) -> VirusScannerService:
    """Return cached scanner singleton (initialized separately via lifespan)."""
    return VirusScannerService(host=host, port=port, timeout=timeout)
