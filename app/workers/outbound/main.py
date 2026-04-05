"""Outbound worker entry point with graceful shutdown."""
import asyncio
import signal
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.core.config import get_settings
from app.workers.outbound.consumer import OUTBOUND_QUEUE, run_consumer, shutdown_consumer
from app.workers.shared.logging import get_logger, set_correlation_id, setup_logging
from app.workers.shared.zalo_token_manager import get_zalo_token_manager

settings = get_settings()
logger: object | None = None
_shutdown_event = asyncio.Event()

WORKER_HEALTH_PORT = int(settings.worker_metrics_port)


class HealthHandler(BaseHTTPRequestHandler):
    """Simple health endpoint for Docker healthcheck."""

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"healthy")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress request logging


def start_health_server(port: int) -> None:
    """Start a background HTTP server for health checks."""
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    asyncio.get_event_loop().run_in_executor(None, server.serve_forever)
    if logger:
        logger.info(f"Health server started on port {port}")


def _setup_signals(loop: asyncio.AbstractEventLoop) -> None:
    """Register SIGTERM/SIGINT handlers for graceful shutdown."""

    def _handle_sigterm(signum: int, frame) -> None:
        sig_name = signal.Signals(signum).name
        if logger:
            logger.info(f"Received {sig_name}, initiating graceful shutdown...")
        _shutdown_event.set()

    def _handle_sigint(signum: int, frame) -> None:
        sig_name = signal.Signals(signum).name
        if logger:
            logger.info(f"Received {sig_name}, initiating graceful shutdown...")
        _shutdown_event.set()

    loop.add_signal_handler(signal.SIGTERM, _handle_sigterm, signal.SIGTERM, None)
    loop.add_signal_handler(signal.SIGINT, _handle_sigint, signal.SIGINT, None)


async def _graceful_shutdown() -> None:
    """Wait for in-flight messages (up to 30s), then exit."""
    logger.info("Starting graceful shutdown (max 30s)")

    try:
        await asyncio.wait_for(_shutdown_event.wait(), timeout=30.0)
    except asyncio.TimeoutError:
        logger.warning("Graceful shutdown timeout reached, forcing exit")

    await shutdown_consumer()
    logger.info("Outbound worker exited")


async def main() -> None:
    """Worker entry point."""
    global logger

    # Setup structured logging
    logger = setup_logging(settings.log_level)
    logger.info("Starting outbound worker", extra={"queue": OUTBOUND_QUEUE})

    # Start health check server
    start_health_server(WORKER_HEALTH_PORT)

    loop = asyncio.get_running_loop()
    _setup_signals(loop)

    # Ensure correlation ID is set for this worker run
    set_correlation_id(settings.zalo_oa_id or "outbound-worker")

    # Initialize Zalo token storage from static env var (one-time setup)
    token_manager = get_zalo_token_manager()
    await token_manager.initialize_from_static_token()

    try:
        await run_consumer()
    except asyncio.CancelledError:
        logger.info("Outbound worker cancelled")
    finally:
        await _graceful_shutdown()


if __name__ == "__main__":
    asyncio.run(main())
