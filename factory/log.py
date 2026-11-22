import logging
from logging.handlers import RotatingFileHandler

from .config import LOGS

log = logging.getLogger("factory")
if not log.handlers:
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = RotatingFileHandler(LOGS / "factory.log", maxBytes=5_000_000, backupCount=3)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    log.addHandler(fh)
    log.addHandler(sh)
