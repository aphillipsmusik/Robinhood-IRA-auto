import json
import os
from datetime import datetime, timezone


def _load(path: str) -> list:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def log_trade(action: str, shares: float, price: float, cash: float, path: str = "trades.json") -> None:
    trades = _load(path)
    trades.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "shares": shares,
        "price": price,
        "cash": cash,
    })
    with open(path, "w") as f:
        json.dump(trades, f, indent=2)
