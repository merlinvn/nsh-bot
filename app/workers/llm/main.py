"""LLM worker entry point — consumes llm.process queue."""
import asyncio
import signal
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from app.core.config import get_settings
from app.workers.llm.consumer import LLMConsumer
from app.workers.shared.heartbeat import start_heartbeat_loop
from app.workers.shared.logging import get_logger, setup_logging

settings = get_settings()
logger: object | None = None
_shutdown_event = asyncio.Event()
_consumer_running = True

WORKER_HEALTH_PORT = int(settings.worker_metrics_port)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            if _consumer_running:
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"healthy")
            else:
                self.send_response(503)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"unhealthy")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def start_health_server(port: int) -> None:
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    asyncio.get_event_loop().run_in_executor(None, server.serve_forever)


def _setup_signals(loop: asyncio.AbstractEventLoop) -> None:
    def handle_sigterm(signum: int, frame) -> None:
        sig_name = signal.Signals(signum).name
        if logger:
            logger.info(f"Received {sig_name}, initiating graceful shutdown...")
        _shutdown_event.set()

    def handle_sigint(signum: int, frame) -> None:
        sig_name = signal.Signals(signum).name
        if logger:
            logger.info(f"Received {sig_name}, initiating graceful shutdown...")
        _shutdown_event.set()

    loop.add_signal_handler(signal.SIGTERM, handle_sigterm, signal.SIGTERM, None)
    loop.add_signal_handler(signal.SIGINT, handle_sigint, signal.SIGINT, None)


async def _graceful_shutdown(consumer: LLMConsumer) -> None:
    logger.info("Starting graceful shutdown")
    await _shutdown_event.wait()
    await consumer.close()
    logger.info("LLM worker exited")


async def main() -> None:
    global logger, _consumer_running

    logger = setup_logging(settings.log_level)
    logger.info("Starting LLM worker", extra={"queue": "llm.process"})

    start_health_server(WORKER_HEALTH_PORT)
    _setup_signals(asyncio.get_running_loop())

    consumer = LLMConsumer()
    _consumer_running = True

    heartbeat_task = await start_heartbeat_loop("llm-worker")

    shutdown_task = asyncio.create_task(_graceful_shutdown(consumer))

    try:
        await consumer.run()
    except asyncio.CancelledError:
        logger.info("LLM worker cancelled")
    except Exception:
        logger.exception("LLM worker consumer error")
    finally:
        _consumer_running = False
        heartbeat_task.cancel()
        shutdown_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        try:
            await shutdown_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
