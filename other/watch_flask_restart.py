import time
import subprocess
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

MONITORED_PATHS = [
    os.path.join(PROJECT_ROOT, 'core'),
    os.path.join(PROJECT_ROOT, 'routes'),
    os.path.join(PROJECT_ROOT, 'app.py')
]

SERVICE_NAME = 'forgor-api.service'
RESTART_COMMAND = ['sudo', 'systemctl', 'restart', SERVICE_NAME]

DEBOUNCE_DELAY = 10 # seconds to wait before acting on consecutive changes

last_trigger_time = 0

class ChangeHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        global last_trigger_time

        if event.is_directory:
            return

        current_time = time.time()
        if current_time - last_trigger_time < DEBOUNCE_DELAY:
            print(f"Change detected in {event.src_path} but debouncing. Skipping restart.")
            return

        is_relevant_path = False
        for monitored_path in MONITORED_PATHS:
            if os.path.isdir(monitored_path):
                if event.src_path.startswith(monitored_path + os.sep):
                    is_relevant_path = True
                    break
                if event.src_path == monitored_path:
                    is_relevant_path = True
                    break
        
        if not is_relevant_path:
            print(f"Ignoring change in non-monitored file: {event.src_path}")
            return


        print(f"Detected change in {event.src_path}. Restarting {SERVICE_NAME}...")
        try:
            last_trigger_time = current_time # Update timestamp immediately
            result = subprocess.run(RESTART_COMMAND, check=True, capture_output=True, text=True)
            print(f"{SERVICE_NAME} restarted successfully.")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
        except subprocess.CalledProcessError as e:
            print(f"Error restarting {SERVICE_NAME}: {e}")
            print("STDOUT:", e.stdout)
            print("STDERR:", e.stderr)
        except FileNotFoundError:
            print(f"Error: Command '{RESTART_COMMAND[0]}' not found. Make sure systemctl is in PATH.")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    print(f"Starting watchdog for project root: {PROJECT_ROOT}")
    print(f"Monitoring paths: {MONITORED_PATHS}")

    event_handler = ChangeHandler()
    observer = Observer()

    for path in MONITORED_PATHS:
        if not os.path.exists(path):
            print(f"Warning: Monitored path does not exist: {path}. Please check your configuration.")
            continue
        
        observer.schedule(event_handler, path, recursive=True if os.path.isdir(path) else False)

    observer.start()
    print("Watchdog started. Press Ctrl+C to stop in development (Ctrl+C won't work in systemd).")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("Watchdog stopped.")
    observer.join()