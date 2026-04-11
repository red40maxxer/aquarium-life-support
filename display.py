import os
import sys
import time
import logging
import spidev as SPI
from lib import LCD_2inch
from PIL import Image,ImageDraw,ImageFont
import glob
from datetime import datetime

base_dir = '/sys/bus/w1/devices/'
device_folder = glob.glob(base_dir + '28*')[0]
device_file = device_folder + '/w1_slave'

def read_temp_raw():
    f = open(device_file, 'r')
    lines = f.readlines()
    f.close()
    return lines
 
def read_temp():
    lines = read_temp_raw()
    while lines[0].strip()[-3:] != 'YES':
        time.sleep(0.2)
        lines = read_temp_raw()
    equals_pos = lines[1].find('t=')
    if equals_pos != -1:
        temp_string = lines[1][equals_pos+2:]
        temp_c = float(temp_string) / 1000.0
        return temp_c

# Pin configs 
RST = 27
DC = 25
BL = 18
bus = 0 
device = 0 
logging.basicConfig(level=logging.DEBUG)
try:
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

    # keep it running forever
    while True:
        # refresh image each time 
        image = Image.new("RGB", (disp.height, disp.width ), "BLACK")
        draw = ImageDraw.Draw(image)

        # header
        curr_temp = read_temp()
        curr_time_str = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        draw.text((180, 10), f"{curr_time_str}", fill="WHITE", font=font_small)
        draw.text((8, 8), f"{curr_temp} C", fill="WHITE", font=font_temp)
        #TODO: implement status logic
        draw.text((8, 44), "stablizing", fill="WHITE", font=font_small)

        disp.ShowImage(image)
        # TODO: figure out optimal polling period
        time.sleep(1)

except IOError as e:
    logging.info(e)    
except KeyboardInterrupt:
    disp.module_exit()
    logging.info("quit:")
    exit()