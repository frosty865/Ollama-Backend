#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ollama Auto Processor - Watcher Script
Monitors incoming folder for new PDF/DOCX files and triggers processing.
"""

import os
import time
import logging
import subprocess
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
WATCH_FOLDER = os.getenv("WATCH_FOLDER", "C:/Users/frost/AppData/Local/Ollama/automation/incoming")
PROCESSED_FOLDER = os.getenv("PROCESSED_FOLDER", "C:/Users/frost/AppData/Local/Ollama/automation/processed")
ERROR_FOLDER = os.getenv("ERROR_FOLDER", "C:/Users/frost/AppData/Local/Ollama/automation/errors")
LIBRARY_FOLDER = os.getenv("LIBRARY_FOLDER", "C:/Users/frost/AppData/Local/Ollama/automation/library")
LOG_DIR = os.getenv("LOG_DIR", "C:/Users/frost/AppData/Local/Ollama/automation/logs")
PIPELINE_SCRIPT = os.path.join(os.path.dirname(__file__), "vofc_pipeline.py")

# Setup logging
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, f"watcher_{time.strftime('%Y%m%d')}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Track files being processed to avoid duplicates
processing_files = set()


class DocumentHandler(FileSystemEventHandler):
    """Handle file system events for incoming documents."""
    
    def __init__(self):
        super().__init__()
        self.min_file_size = 1024  # 1KB minimum
    
    def on_created(self, event):
        """Called when a file is created in the watched directory."""
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        
        # Only process PDF and DOCX files
        if file_path.suffix.lower() not in ['.pdf', '.docx']:
            return
        
        # Check if file is still being written (wait for file to be complete)
        if file_path in processing_files:
            return
        
        # Wait a bit for file to be fully written
        time.sleep(2)
        
        # Verify file is complete
        if not file_path.exists() or file_path.stat().st_size < self.min_file_size:
            logger.warning(f"File {file_path.name} too small or deleted, skipping")
            return
        
        # Check if file is still being written
        initial_size = file_path.stat().st_size
        time.sleep(1)
        if file_path.stat().st_size != initial_size:
            logger.info(f"File {file_path.name} still being written, waiting...")
            time.sleep(3)
        
        self.process_file(file_path)
    
    def on_moved(self, event):
        """Called when a file is moved to the watched directory."""
        if event.is_directory:
            return
        
        file_path = Path(event.dest_path)
        
        if file_path.suffix.lower() not in ['.pdf', '.docx']:
            return
        
        if file_path in processing_files:
            return
        
        time.sleep(1)
        self.process_file(file_path)
    
    def process_file(self, file_path: Path):
        """Process a document file."""
        if file_path in processing_files:
            logger.warning(f"File {file_path.name} already being processed")
            return
        
        processing_files.add(file_path)
        logger.info(f"📄 New file detected: {file_path.name} ({(file_path.stat().st_size / 1024):.2f} KB)")
        
        try:
            # Run the pipeline script
            logger.info(f"🚀 Starting processing for {file_path.name}...")
            
            result = subprocess.run(
                ["python", PIPELINE_SCRIPT, "--file", str(file_path)],
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout
                cwd=os.path.dirname(__file__)
            )
            
            if result.returncode == 0:
                logger.info(f"✅ Successfully processed {file_path.name}")
                
                # Move to processed folder
                processed_path = Path(PROCESSED_FOLDER) / file_path.name
                try:
                    os.makedirs(PROCESSED_FOLDER, exist_ok=True)
                    file_path.rename(processed_path)
                    logger.info(f"📁 Moved {file_path.name} to processed folder")
                except Exception as move_error:
                    logger.error(f"Failed to move file to processed: {move_error}")
            else:
                logger.error(f"❌ Processing failed for {file_path.name}")
                logger.error(f"Error output: {result.stderr}")
                
                # Move to errors folder
                error_path = Path(ERROR_FOLDER) / file_path.name
                try:
                    os.makedirs(ERROR_FOLDER, exist_ok=True)
                    file_path.rename(error_path)
                    logger.info(f"📁 Moved {file_path.name} to errors folder")
                except Exception as move_error:
                    logger.error(f"Failed to move file to errors: {move_error}")
        
        except subprocess.TimeoutExpired:
            logger.error(f"⏱️ Processing timeout for {file_path.name}")
            # Move to errors folder
            try:
                error_path = Path(ERROR_FOLDER) / file_path.name
                os.makedirs(ERROR_FOLDER, exist_ok=True)
                file_path.rename(error_path)
            except Exception as move_error:
                logger.error(f"Failed to move file to errors: {move_error}")
        
        except Exception as e:
            logger.error(f"❌ Error processing {file_path.name}: {e}")
            # Move to errors folder
            try:
                error_path = Path(ERROR_FOLDER) / file_path.name
                os.makedirs(ERROR_FOLDER, exist_ok=True)
                file_path.rename(error_path)
            except Exception as move_error:
                logger.error(f"Failed to move file to errors: {move_error}")
        
        finally:
            processing_files.discard(file_path)


def main():
    """Main watcher function."""
    watch_path = Path(WATCH_FOLDER)
    
    if not watch_path.exists():
        logger.error(f"Watch folder does not exist: {WATCH_FOLDER}")
        logger.info(f"Creating watch folder: {WATCH_FOLDER}")
        os.makedirs(WATCH_FOLDER, exist_ok=True)
    
    if not Path(PIPELINE_SCRIPT).exists():
        logger.error(f"Pipeline script not found: {PIPELINE_SCRIPT}")
        return
    
    logger.info("=" * 50)
    logger.info("Ollama Auto Processor - Watcher")
    logger.info("=" * 50)
    logger.info(f"📁 Watching folder: {WATCH_FOLDER}")
    logger.info(f"📄 Processing script: {PIPELINE_SCRIPT}")
    logger.info(f"✅ Processed folder: {PROCESSED_FOLDER}")
    logger.info(f"❌ Errors folder: {ERROR_FOLDER}")
    logger.info(f"📚 Library folder: {LIBRARY_FOLDER}")
    logger.info("=" * 50)
    logger.info("📡 Watching folder for new files...")
    logger.info("Press Ctrl+C to stop")
    logger.info("")
    
    event_handler = DocumentHandler()
    observer = Observer()
    observer.schedule(event_handler, str(watch_path), recursive=False)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\n🛑 Stopping watcher...")
        observer.stop()
    
    observer.join()
    logger.info("👋 Watcher stopped")


if __name__ == "__main__":
    main()

