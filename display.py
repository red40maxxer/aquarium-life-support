import os
import sys
import time
import logging
import spidev as SPI
from lib import LCD_2inch
from PIL import Image,ImageDraw,ImageFont

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

    image1 = Image.new("RGB", (disp.height, disp.width ), "BLACK")
    draw = ImageDraw.Draw(image1)

    font = ImageFont.truetype("agamefont.ttf",25)
    draw.text((5, 58), 'hello world', fill="WHITE", font=font)
    
    disp.ShowImage(image1)
    
except IOError as e:
    logging.info(e)    
except KeyboardInterrupt:
    disp.module_exit()
    logging.info("quit:")
    exit()