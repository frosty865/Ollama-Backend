import os
import time
import json
import shutil
import requests
from dotenv import load_dotenv
from supabase import create_client, Client
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
WATCH_FOLDER = os.getenv("WATCH_FOLDER", "/ollama/incoming")
PROCESSED_FOLDER = os.getenv("PROCESSED_FOLDER", "/ollama/processed")
ERROR_FOLDER = os.getenv("ERROR_FOLDER", "/ollama/errors")
MODEL = os.getenv("MODEL", "vofc-engine")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def record_to_supabase(file_name: str, status: str, result_path: str = None, error_log: str = None):
    try:
        data = {
            "file_name": file_name,
            "model_used": MODEL,
            "status": status,
            "result_path": result_path,
            "error_log": error_log,
        }
        supabase.table("submissions").insert(data).execute()
        log(f"📤 Metadata synced to Supabase: {file_name}")
    except Exception as e:
        log(f"⚠️ Supabase update failed: {e}")

class FileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        file_path = event.src_path
        file_name = os.path.basename(file_path)

        time.sleep(2)  # ensure file fully written before processing
        try:
            from vofc_pipeline import process_document
            output_dict = process_document(file_path)
            output = json.dumps(output_dict, indent=2)

            output_file = os.path.join(PROCESSED_FOLDER, f"{file_name}.json")
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(output)

            shutil.move(file_path, PROCESSED_FOLDER)
            record_to_supabase(file_name, "processed", output_file)
            log(f"✅ Processed: {file_name}")

        except Exception as e:
            err_file = os.path.join(ERROR_FOLDER, f"{file_name}.log")
            with open(err_file, "w") as ef:
                ef.write(str(e))
            shutil.move(file_path, ERROR_FOLDER)
            record_to_supabase(file_name, "error", error_log=str(e))
            log(f"❌ Error logged for {file_name}")

if __name__ == "__main__":
    log("📡 Watching folder for new files...")
    event_handler = FileHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_FOLDER, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

