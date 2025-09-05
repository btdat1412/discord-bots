from multiprocessing import Process
import logging

from src.shared.config import get_bot_configs
from src.shared.logging_conf import setup_logging
from src.core.bot_runner import run_bot


def main():
    setup_logging()
    log = logging.getLogger("launcher")
    bot_configs = get_bot_configs()

    procs = []
    # Start multiple bot
    for bot_cfg in bot_configs:
        p = Process(
            target=run_bot, args=(bot_cfg,), name=f"bot:{bot_cfg.name}", daemon=False
        )
        p.start()
        log.info("Started bot process: %s (pid=%s)", bot_cfg.name, p.pid)
        procs.append(p)

    for p in procs:
        p.join()


if __name__ == "__main__":
    main()
