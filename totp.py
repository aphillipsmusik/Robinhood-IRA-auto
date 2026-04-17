import os
import pyotp
from dotenv import load_dotenv

load_dotenv()


def get_totp_code() -> str:
    secret = os.environ.get("TOTP_SECRET")
    if not secret:
        raise RuntimeError("TOTP_SECRET not set in environment")
    totp = pyotp.TOTP(secret)
    return totp.now()
