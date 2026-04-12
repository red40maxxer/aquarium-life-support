import os
import sys
import signal
import logging
import spidev as SPI
from lib import LCD_2inch
from PIL import Image,ImageDraw,ImageFont
import time
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import temp

DB_PATH = "aquarium.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS temperature_log (
            ts INTEGER NOT NULL,
            temp_c REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_temperature_log_ts
        ON temperature_log(ts)
    """)
    conn.commit()
    return conn

def draw_sparkline(draw, points, x, y, w, h, color="WHITE"):
    if not points or len(points) < 2:
        return

    vals = [float(p[1]) for p in points]
    vmin = min(vals)
    vmax = max(vals)

    if vmax == vmin:
        vmax += 0.1

    step_x = w / (len(vals) - 1)
    coords = []

    for i, v in enumerate(vals):
        px = x + i * step_x
        py = y + h - ((v - vmin) / (vmax - vmin)) * h
        coords.append((px, py))

    for i in range(len(coords) - 1):
        draw.line((coords[i], coords[i + 1]), fill=color, width=2)

# Pin configs 
RST = 27
DC = 25
BL = 18
bus = 0 
device = 0 
logging.basicConfig(level=logging.DEBUG)

LOG_INTERVAL = 60

def shutdown(signum, frame):
    logging.info(f"received signal {signum}, shutting down")
    disp.module_exit()
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown)

try:
    conn = init_db()
    logging.info("[db] initialized")

    disp = LCD_2inch.LCD_2inch()
    # Initialize library.
    disp.Init()
    # Clear display.
    disp.clear()
    #Set the backlight to 100
    disp.bl_DutyCycle(50)

    font_temp = ImageFont.truetype("agamefont.ttf", 32)
    font_small = ImageFont.truetype("agamefont.ttf", 16)
    font_status = ImageFont.truetype("agamefont.ttf", 18)    

    last_log = 0
    # keep it running forever
    while True:
        # refresh image each time 
        image = Image.new("RGB", (disp.height, disp.width ), "BLACK")
        draw = ImageDraw.Draw(image)


        curr_temp = temp.read_temp()
        curr_time = datetime.now(tz=ZoneInfo("America/New_York"))
        curr_time_str = curr_time.strftime("%d-%m-%Y %H:%M:%S")

        # log temperature to db
        now_ts = time.time()
        if now_ts - last_log >= LOG_INTERVAL:
            temp.log_temp(conn, curr_temp, curr_time)
            last_log = now_ts

        curr_status = "no data"
        # get temp trend to derive status
        temps_1hr = temp.get_last_1hr(conn)
        if temps_1hr and len(temps_1hr) > 2:
            first = float(temps_1hr[0][1])
            last = float(temps_1hr[-1][1])

            res = round(last - first, 3)
            if res > 1:
                curr_status = f"increasing: {res}C"
            elif res < -1:
                curr_status = f"decreasing: {res}C"
            else:
                curr_status = f"stable: {res}C"

        logging.debug(f"[temp]: {curr_temp}")
        logging.debug(f"[timestamp]: {curr_time_str}")
        logging.debug(f"[status]: {curr_status}")

        # header
        draw.text((160, 10), f"{curr_time_str}", fill="WHITE", font=font_small)
        draw.text((8, 8), f"{curr_temp}C", fill="WHITE", font=font_temp)
        draw.text((8, 44), f"{curr_status}", fill="WHITE", font=font_small)

        # 24h sparkline
        temps_24hr = temp.get_last_24h(conn)
        draw.text((8, 68), "24h", fill="GRAY", font=font_small)
        draw_sparkline(draw, temps_24hr, 8, 88, 304, 130)
        disp.ShowImage(image)
        # TODO: figure out optimal polling period
        time.sleep(1)

except IOError as e:
    logging.info(e)    
except KeyboardInterrupt:
    disp.module_exit()
    logging.info("quit:")
    exit()