import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("presence_sim")

logger.info("Presence Simulation Add-on started")

# Keep container alive
while True:
    time.sleep(60)
