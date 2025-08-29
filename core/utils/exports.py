# helpers/exports.py

import os, json, zipfile, secrets, hashlib, time
from io import BytesIO

EXPORT_DIR = os.getenv("EXPORT_DIR", "/var/forgor/exports")
os.makedirs(EXPORT_DIR, exist_ok=True)

def write_zip_to_path(user_files, master_data) -> dict:
    """
    Creates a ZIP on disk and returns metadata: {token, zip_path, size, sha256, expires_at}
    """
    token = secrets.token_urlsafe(24)                # unguessable
    zip_path = os.path.join(EXPORT_DIR, f"{token}.zip")
    expires_at = int(time.time()) + 24*60*60         # 24h TTL

    # write zip
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("master.json", json.dumps(master_data, indent=2))
        for f in user_files:
            path = f.file_path
            if path and os.path.exists(path):
                zf.write(path, arcname=f"files/{os.path.basename(path)}")

    # checksum + size
    h = hashlib.sha256()
    with open(zip_path, "rb") as fp:
        for chunk in iter(lambda: fp.read(1024*1024), b""):
            h.update(chunk)
    size = os.path.getsize(zip_path)
    sha256 = h.hexdigest()

    # write tiny metadata alongside (lets us validate user + expiry)
    meta = {
        "user_id": user_files[0].user_id if user_files else None,
        "token": token,
        "zip": os.path.basename(zip_path),
        "size": size,
        "sha256": sha256,
        "expires_at": expires_at,
        "used": False,
    }
    with open(os.path.join(EXPORT_DIR, f"{token}.json"), "w") as mf:
        json.dump(meta, mf)

    return meta
