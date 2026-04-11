import os
import sys
import logging
import spidev as SPI
from lib import LCD_2inch
from PIL import Image,ImageDraw,ImageFont
import time
import sqlite3
from datetime import datetime

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

# Pin configs 
RST = 27
DC = 25
BL = 18
bus = 0 
device = 0 
logging.basicConfig(level=logging.DEBUG)

LOG_INTERVAL = 60

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
        curr_time = datetime.now()
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
            first = temps_1hr[0][0]
            last = temps_1hr[-1][0]

            res = last - first
            if res > 1:
                curr_status = f"increasing: Δ{res}C"
            elif res < -1:
                curr_status = f"decreasing: Δ{res}C"
            else:
                curr_status = f"stable: Δ{res}C"

        logging.debug(f"[temp]: {curr_temp}")
        logging.debug(f"[timestamp]: {curr_time_str}")
        logging.debug(f"[status]: {curr_status}")

        # header
        draw.text((160, 10), f"{curr_time_str}", fill="WHITE", font=font_small)
        draw.text((8, 8), f"{curr_temp}C", fill="WHITE", font=font_temp)
        draw.text((8, 44), f"{curr_status}", fill="WHITE", font=font_small)

        disp.ShowImage(image)
        # TODO: figure out optimal polling period
        time.sleep(1)

except IOError as e:
    logging.info(e)    
except KeyboardInterrupt:
    disp.module_exit()
    logging.info("quit:")
    exit()