import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

_config = json.load(open("config.json"))
_provider = _config["notifications"]["provider"]
_ntfy_topic = _config["notifications"].get("ntfy_topic", "robinhood-okll")
_pushover_token = os.environ.get("PUSHOVER_TOKEN")
_pushover_user = os.environ.get("PUSHOVER_USER")


async def notify(message: str) -> None:
    try:
        if _provider == "ntfy":
            async with httpx.AsyncClient() as client:
                await client.post(f"https://ntfy.sh/{_ntfy_topic}", content=message.encode())
        elif _provider == "pushover":
            async with httpx.AsyncClient() as client:
                await client.post("https://api.pushover.net/1/messages.json", data={
                    "token": _pushover_token,
                    "user": _pushover_user,
                    "message": message,
                })
    except Exception as e:
        print(f"[notify] failed: {e}")
