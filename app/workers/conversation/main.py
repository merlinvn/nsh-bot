"""Conversation worker entry point.

- Loads settings from environment
- Sets up signal handlers (SIGTERM, SIGINT) for graceful shutdown
- Initializes and runs the RabbitMQ consumer
- Completes in-flight work within 30s on shutdown
"""

import asyncio
import signal
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from app.workers.conversation.consumer import ConversationConsumer
from app.workers.shared.logging import get_logger

logger = get_logger("conversation-worker")


def main() -> None:
    shutdown_event = asyncio.Event()

    def handle_signal(signum: int, frame) -> None:
        logger.info("shutdown_signal_received", signum=signum)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

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

    # Run shutdown task in background
    shutdown_task = asyncio.create_task(_wait_for_shutdown(shutdown_event, on_shutdown))

    try:
        await consumer.run()
    except asyncio.CancelledError:
        logger.info("consumer_cancelled")
    finally:
        shutdown_task.cancel()
        try:
            await shutdown_task
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
