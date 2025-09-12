# tracking.py

import os
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

APP_SECRET_KEY      = os.getenv("APP_SECRET_KEY")

def make_click_token(user_id: int, url: str, source: str = "digest") -> str:
    s = URLSafeTimedSerializer(APP_SECRET_KEY)
    payload = {"uid": user_id, "url": url, "s": source}
    return s.dumps(payload)
def make_unsub_token(user_id: int, email: str, source: str) -> str:
    s = URLSafeTimedSerializer(APP_SECRET_KEY)
    payload = {"uid": user_id, "e": email, "s": source}
    return s.dumps(payload)

def verify_link_token(token: str, max_age: int = 60*60*24*30):
    s = URLSafeTimedSerializer(APP_SECRET_KEY)
    try:
        return s.loads(token, max_age=max_age)
    except (SignatureExpired, BadSignature):
        return None