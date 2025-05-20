import time
import os
import subprocess
import hashlib
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

WATCH_FILE = 'projects/mia-2/app.py'
SERVICE_NAME = 'mia2.service'
CHECK_INTERVAL = 2  # seconds
DEBOUNCE_DELAY = 10  # seconds to wait before acting on change

last_hash = None
last_trigger_time = 0

def hash_file(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

class ChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        global last_trigger_time, last_hash

        if event.src_path != WATCH_FILE:
            return

        current_time = time.time()
        if current_time - last_trigger_time < DEBOUNCE_DELAY:
            return

        new_hash = hash_file(WATCH_FILE)
        if new_hash == last_hash:
            return  # No real change

        last_hash = new_hash
        last_trigger_time = current_time

        print(f"[watchdog] Significant change detected in {WATCH_FILE}. Restarting service...")
        subprocess.run(["sudo", "systemctl", "restart", SERVICE_NAME])
        print(f"[watchdog] Restarted {SERVICE_NAME}")

if __name__ == "__main__":
    if not os.path.exists(WATCH_FILE):
        print(f"File {WATCH_FILE} does not exist.")
        exit(1)

    last_hash = hash_file(WATCH_FILE)
    event_handler = ChangeHandler()
    observer = Observer()
    observer.schedule(event_handler, path=os.path.dirname(WATCH_FILE), recursive=False)
    observer.start()
    print(f"[watchdog] Watching {WATCH_FILE}...")

    try:
        while True:
            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()