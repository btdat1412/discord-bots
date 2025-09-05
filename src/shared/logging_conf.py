import logging, sys


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if root.handlers:
        # Avoid duplicate handlers in REPL/Dev
        return
    root.setLevel(level)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(processName)s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.addHandler(ch)
