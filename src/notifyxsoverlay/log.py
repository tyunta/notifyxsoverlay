from __future__ import annotations

import json
import sys
from typing import Any


def log_event(level: str, event: str, **fields: Any) -> None:
    payload = {"level": level, "event": event}
    payload.update(fields)
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
