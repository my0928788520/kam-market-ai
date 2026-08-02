"""Application logging that redacts common secret assignments."""
import logging, re
from pathlib import Path

class RedactingFilter(logging.Filter):
    pattern=re.compile(
        r"(?i)(fubon_neo_(?:personal_id|password|cert_path|cert_password)|"
        r"personal_id|password|secret|api[_-]?key|token|cert(?:ificate)?(?:[_-]?(?:path|password))?)"
        r"\s*[=:]\s*\S+"
    )
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg=self.pattern.sub(r"\1=[REDACTED]",str(record.msg)); record.args=()
        return True

def configure_logging(level: str="INFO", path: str | Path="logs/kam.log") -> None:
    log_path=Path(path); log_path.parent.mkdir(parents=True,exist_ok=True)
    formatter=logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handlers: list[logging.Handler]=[logging.StreamHandler(),logging.FileHandler(log_path,encoding="utf-8")]
    for handler in handlers: handler.setFormatter(formatter); handler.addFilter(RedactingFilter())
    logging.basicConfig(level=getattr(logging,level,"INFO"),handlers=handlers,force=True)
