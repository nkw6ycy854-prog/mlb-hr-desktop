from __future__ import annotations

from datetime import datetime,timezone
import json,logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


class JsonFormatter(logging.Formatter):
    def format(self,record:logging.LogRecord)->str:
        payload={
            "timestamp":datetime.now(timezone.utc).isoformat(),
            "level":record.levelname,
            "logger":record.name,
            "message":record.getMessage(),
        }
        for key in ("run_id","snapshot_id","prediction_id","game_pk","module","error_code","duration_ms","model_version"):
            value=getattr(record,key,None)
            if value is not None:payload[key]=value
        if record.exc_info:payload["exception"]=self.formatException(record.exc_info)
        return json.dumps(payload,ensure_ascii=False,default=str)


def configure_logging(log_dir:Path)->None:
    log_dir.mkdir(parents=True,exist_ok=True)
    root=logging.getLogger();root.setLevel(logging.INFO)
    if any(isinstance(h,RotatingFileHandler) for h in root.handlers):return
    handler=RotatingFileHandler(log_dir/"mlb_hr.log",maxBytes=4*1024*1024,backupCount=5,encoding="utf-8")
    handler.setFormatter(JsonFormatter());root.addHandler(handler)
