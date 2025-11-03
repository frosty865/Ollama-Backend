import time
from pathlib import Path
import requests
from app.utils.config import HOST, PORT, INCOMING_DIR
from app.utils.logger import get_logger


logger = get_logger("auto-processor")


API = f"http://{HOST}:{PORT}/api/documents/process-one"


def main():
    logger.info("Auto-processor watching: %s", INCOMING_DIR)
    while True:
        try:
            r = requests.post(API, json={}, timeout=180)
            if r.status_code == 200:
                j = r.json()
                msg = j if isinstance(j, dict) else {"raw": j}
                logger.info("process-one → %s", msg)
            elif r.status_code == 500:
                logger.error("process-one failed: %s", r.text)
            else:
                logger.warning("process-one unexpected: %s %s", r.status_code, r.text)
        except Exception as e:
            logger.error("process-one error: %s", e)
        time.sleep(3)


if __name__ == "__main__":
    main()

