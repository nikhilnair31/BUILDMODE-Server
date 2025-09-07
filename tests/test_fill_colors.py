import json, logging
from dotenv import load_dotenv
from psycopg2.extras import execute_batch
from sqlalchemy import text
from core.database.database import get_db_session

def rgb_to_lab(r,g,b):
    def inv_gamma(u): return u/12.92 if u<=0.04045 else ((u+0.055)/1.055)**2.4
    R,G,B = [inv_gamma(x/255.0) for x in (r,g,b)]
    X = 0.4124564*R + 0.3575761*G + 0.1804375*B
    Y = 0.2126729*R + 0.7151522*G + 0.0721750*B
    Z = 0.0193339*R + 0.1191920*G + 0.9503041*B
    X/=0.95047; Y/=1.00000; Z/=1.08883
    def pivot(u): return u**(1/3) if u>0.008856 else (7.787*u+16/116)
    fx, fy, fz = pivot(X), pivot(Y), pivot(Z)
    L = 116*fy - 16
    a = 500*(fx - fy)
    b = 200*(fy - fz)
    return [L,a,b]

def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2],16) for i in (0,2,4))

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session = get_db_session()

sql = text("SELECT id, tags FROM data WHERE tags IS NOT NULL;")
rows = session.execute(sql).fetchall()

updates = []
for rid, tags in rows:
    try:
        tags_json = tags if isinstance(tags, dict) else json.loads(tags)
        colors = tags_json.get("accent_colors", [])
        if not colors:
            continue
        for hex_val in colors:
            rgb = hex_to_rgb(hex_val)
            lab = rgb_to_lab(*rgb)
            updates.append((rid, hex_val, lab))
    except Exception as e:
        logger.warning("skip %s %s", rid, e)

if updates:
    raw_conn = session.connection().connection
    with raw_conn.cursor() as cur:
        execute_batch(
            cur,
            "INSERT INTO data_color (data_id, color_hex, color_vector) VALUES (%s, %s, %s)",
            updates,
            page_size=500
        )

session.commit()
session.close()
