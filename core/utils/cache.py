# cache.py

import os
import json
import logging
from hashlib import sha256
from collections import defaultdict
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# -------- Config --------
CACHE_TTL_SECONDS   =   int(os.getenv("QUERY_CACHE_TTL"))
CACHE_MAX_PER_USER  =   int(os.getenv("QUERY_CACHE_MAX_PER_USER"))
REDIS_URL           =   os.getenv("REDIS_URL")
KEY_PREFIX          =   os.getenv("QUERY_CACHE_PREFIX")

# -------- Backend setup --------
_redis = None
try:
    import redis  # type: ignore
    _redis = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    _redis.ping()
    logger.info("Query cache using Redis at %s", REDIS_URL)
except Exception as e:
    _redis = None
    logger.warning("Redis unavailable (%s). Falling back to in-process cache (per worker).", e)

# Fallback per-process cache (only used if Redis is not available)
_inproc = defaultdict(lambda: TTLCache(maxsize=CACHE_MAX_PER_USER, ttl=CACHE_TTL_SECONDS))

# -------- Helpers --------
def _normalize(text: str) -> str:
    return text.strip().lower()

def _make_key(user_id, text: str) -> str:
    norm = _normalize(text)
    h = sha256(f"{user_id}:{norm}".encode()).hexdigest()
    return f"{KEY_PREFIX}{user_id}:{h}"

def get_cache_value(user_id, query_text):
    k = _make_key(user_id, query_text)
    if _redis:
        val = _redis.get(k)
        if val is not None:
            logger.info("HIT - Cache hit for user %s", user_id)
            return json.loads(val)
        logger.info("MISS - Cache miss for user %s", user_id)
        return None
    # fallback
    res = _inproc[user_id].get(k)
    logger.info("%s - Cache %s for user %s",
                "HIT" if res is not None else "MISS",
                "hit" if res is not None else "miss", user_id)
    return res

def store_cache(user_id, query_text, result_json):
    k = _make_key(user_id, query_text)
    if _redis:
        _redis.setex(k, CACHE_TTL_SECONDS, json.dumps(result_json))
        # track keys per user for fast clear
        setkey = f"{KEY_PREFIX}keys:{user_id}"
        _redis.sadd(setkey, k)
        _redis.expire(setkey, CACHE_TTL_SECONDS + 300)
    else:
        _inproc[user_id][k] = result_json
    logger.info("STORE - Cached result for user %s key %s", user_id, k)
    return k

def clear_user_cache(user_id):
    if _redis:
        setkey = f"{KEY_PREFIX}keys:{user_id}"
        keys = list(_redis.smembers(setkey))
        deleted = 0
        if keys:
            deleted = _redis.delete(*keys)
        _redis.delete(setkey)
        logger.info("CLEAR - Cleared %d Redis keys for user %s", deleted, user_id)
        return
    # fallback
    if user_id in _inproc:
        cleared = len(_inproc[user_id])
        _inproc[user_id].clear()
        logger.info("CLEAR - Cleared %d in-process entries for user %s", cleared, user_id)