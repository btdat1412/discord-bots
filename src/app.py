from multiprocessing import Process
import logging
import time
import signal
import sys

from src.shared.config import get_bot_configs
from src.shared.logging_conf import setup_logging
from src.core.bot_runner import run_bot


def safe_run_bot(bot_cfg):
    """Wrapper for run_bot that handles exceptions gracefully."""
    try:
        run_bot(bot_cfg)
    except Exception as e:
        log = logging.getLogger(f"bot:{bot_cfg.name}")
        log.exception("Bot '%s' crashed with error: %s", bot_cfg.name, e)


def main():
    setup_logging()
    log = logging.getLogger("launcher")
    bot_configs = get_bot_configs()

    running_procs = []
    failed_bots = []

    # Start all bots
    for bot_cfg in bot_configs:
        try:
            p = Process(
                target=safe_run_bot,
                args=(bot_cfg,),
                name=f"bot:{bot_cfg.name}",
                daemon=False,
            )
            p.start()
            log.info("✅ Started bot process: %s (pid=%s)", bot_cfg.name, p.pid)
            running_procs.append((bot_cfg.name, p))
        except Exception as e:
            log.error("❌ Failed to start bot '%s': %s", bot_cfg.name, e)
            failed_bots.append(bot_cfg.name)

    if not running_procs:
        log.error("❌ No bots could be started successfully. Exiting.")
        return

    log.info(
        "🚀 Successfully started %d bot(s), %d failed to start",
        len(running_procs),
        len(failed_bots),
    )

    # Set up signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        log.info("🛑 Shutdown signal received. Stopping all bots...")
        for bot_name, proc in running_procs:
            if proc.is_alive():
                log.info("Stopping bot: %s", bot_name)
                proc.terminate()
                proc.join(timeout=5)
                if proc.is_alive():
                    log.warning("Force killing bot: %s", bot_name)
                    proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Monitor running processes
    try:
        while True:
            active_procs = []
            for bot_name, proc in running_procs:
                if proc.is_alive():
                    active_procs.append((bot_name, proc))
                else:
                    # Bot process died
                    exit_code = proc.exitcode
                    if exit_code == 0:
                        log.info("✅ Bot '%s' shut down normally", bot_name)
                    else:
                        log.error(
                            "❌ Bot '%s' crashed with exit code: %s",
                            bot_name,
                            exit_code,
                        )

            running_procs = active_procs

            if not running_procs:
                log.warning("⚠️ All bots have stopped. Exiting launcher.")
                break

            # Check every 5 seconds
            time.sleep(5)

    except KeyboardInterrupt:
        log.info("🛑 Keyboard interrupt received. Stopping all bots...")
        for bot_name, proc in running_procs:
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)
                if proc.is_alive():
                    proc.kill()


if __name__ == "__main__":
    main()
