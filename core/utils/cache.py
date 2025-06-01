from cachetools import TTLCache
from hashlib import sha256
import logging

logger = logging.getLogger(__name__)

query_cache = TTLCache(maxsize=1000, ttl=300)

def get_cache_key(user_id, query_text):
    return sha256(f"{user_id}:{query_text}".encode()).hexdigest()

def clear_user_cache(user_id):
    keys_to_remove = [k for k in query_cache.keys() if k.startswith(f"{user_id}:")]
    if keys_to_remove:
        logger.info(f"Clearing {len(keys_to_remove)} cache entries for user {user_id}")
        for k in keys_to_remove:
            try:
                del query_cache[k]
            except KeyError:
                pass # Handle concurrent deletion if necessary