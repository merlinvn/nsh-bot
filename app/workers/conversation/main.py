"""Conversation worker entry point.

- Loads settings from environment
- Sets up signal handlers (SIGTERM, SIGINT) for graceful shutdown
- Initializes and runs the RabbitMQ consumer
- Completes in-flight work within 30s on shutdown
"""

import asyncio
import signal
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from app.workers.conversation.consumer import ConversationConsumer
from app.workers.shared.logging import get_logger, setup_logging
from app.workers.shared.heartbeat import start_heartbeat_loop
from app.core.config import get_settings

settings = get_settings()
logger = get_logger("conversation-worker")

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
    logger.info(f"Health server started on port {port}")


def main() -> None:
    # Setup structured logging first
    from app.core.config import get_settings
    settings = get_settings()
    setup_logging(settings.log_level)

    # Start health check server
    start_health_server(WORKER_HEALTH_PORT)

    shutdown_event = asyncio.Event()

    def handle_signal(signum: int, frame) -> None:
        logger.info("shutdown_signal_received", signum=signum)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logger.info("Starting conversation worker")

    try:
        asyncio.run(run_consumer(shutdown_event))
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt")
    finally:
        logger.info("worker_exiting")


async def run_consumer(shutdown_event: asyncio.Event) -> None:
    consumer = ConversationConsumer()

    async def on_shutdown() -> None:
        logger.info("shutdown_initiated")
        await consumer.close()
        logger.info("shutdown_complete")

    loop = asyncio.get_running_loop()

    # Start Redis heartbeat
    heartbeat_task = await start_heartbeat_loop("conversation-worker")

    # Run shutdown task in background
    shutdown_task = asyncio.create_task(_wait_for_shutdown(shutdown_event, on_shutdown))

    try:
        await consumer.run()
    except asyncio.CancelledError:
        logger.info("consumer_cancelled")
    finally:
        shutdown_task.cancel()
        heartbeat_task.cancel()
        try:
            await shutdown_task
        except asyncio.CancelledError:
            pass
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        await on_shutdown()


async def _wait_for_shutdown(shutdown_event: asyncio.Event, callback) -> None:
    try:
        await asyncio.wait_for(shutdown_event.wait(), timeout=None)
    except asyncio.TimeoutError:
        pass
    await callback()


if __name__ == "__main__":
    main()
