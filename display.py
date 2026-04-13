import sys
import signal
import logging
from lib import LCD_2inch
from PIL import Image,ImageDraw,ImageFont
import time
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import temp

DB_PATH = "aquarium.db"
DISPLAY_TZ = ZoneInfo("America/Toronto")
PUFFER_IMAGE = "puffer.png"
SCREEN_BG = (0, 0, 0)

disp = None
latest_log_message = ""

try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE = Image.LANCZOS

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


class LatestLogHandler(logging.Handler):
    def emit(self, record):
        global latest_log_message
        latest_log_message = self.format(record)

def text_size(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_right_aligned(draw, text, right, y, font, fill):
    width, _ = text_size(draw, text, font)
    draw.text((right - width, y), text, fill=fill, font=font)


def fit_text(draw, text, font, max_width):
    if text_size(draw, text, font)[0] <= max_width:
        return text

    ellipsis = "..."
    while text and text_size(draw, text + ellipsis, font)[0] > max_width:
        text = text[:-1]
    return text + ellipsis if text else ellipsis


def format_temp(value):
    return f"{float(value):.1f}C"


def load_puffer_image(path=PUFFER_IMAGE, max_size=(88, 76)):
    try:
        puffer = Image.open(path).convert("RGB")
    except OSError as exc:
        logging.warning(f"[puffer] could not load {path}: {exc}")
        return None

    puffer.thumbnail(max_size, RESAMPLE)
    return puffer


def paste_centered(base_image, overlay, center_x, y):
    if overlay is None:
        return

    x = int(center_x - overlay.width / 2)
    base_image.paste(overlay, (x, y))


def draw_sparkline(
    draw,
    points,
    x,
    y,
    w,
    h,
    font,
    color=(92, 232, 244),
    now_ts=None,
    window_seconds=None,
):
    chart_bg = (4, 12, 13)
    grid = (22, 46, 49)
    border = (58, 91, 95)
    label = (145, 165, 164)

    draw.rectangle((x, y, x + w, y + h), fill=chart_bg, outline=border)

    inner_x = x + 5
    inner_y = y + 7
    inner_w = w - 10
    inner_h = h - 14

    for frac in (0.25, 0.5, 0.75):
        gy = inner_y + int(inner_h * frac)
        draw.line((inner_x, gy, inner_x + inner_w, gy), fill=grid, width=1)

    if not points:
        draw_sparkline_message(draw, "collecting trend data", x, y, w, h, font, label)
        return None

    rows = sorted((int(p[0]), float(p[1])) for p in points)
    end_ts = int(now_ts) if now_ts is not None else rows[-1][0]
    end_ts = max(end_ts, rows[-1][0])

    if window_seconds is not None:
        cutoff_ts = end_ts - window_seconds
        rows = [(ts, value) for ts, value in rows if ts >= cutoff_ts]

    if not rows:
        draw_sparkline_message(draw, "collecting trend data", x, y, w, h, font, label)
        return None

    vals = [value for _, value in rows]
    vmin = min(vals)
    vmax = max(vals)

    if vmax == vmin:
        display_min = vmin - 0.1
        display_max = vmax + 0.1
    else:
        pad = (vmax - vmin) * 0.08
        display_min = vmin - pad
        display_max = vmax + pad

    start_ts = rows[0][0]
    if window_seconds is not None and end_ts - start_ts > window_seconds:
        start_ts = end_ts - window_seconds
    if end_ts <= start_ts:
        start_ts = end_ts - 1

    time_span = end_ts - start_ts
    coords = []

    for ts, v in rows:
        px = inner_x + ((ts - start_ts) / time_span) * inner_w
        py = inner_y + inner_h - ((v - display_min) / (display_max - display_min)) * inner_h
        coords.append((px, py))

    if len(coords) == 1:
        px, py = coords[0]
        draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill=color)
    else:
        for i in range(len(coords) - 1):
            draw.line((coords[i], coords[i + 1]), fill=color, width=2)

    min_idx = vals.index(vmin)
    max_idx = vals.index(vmax)
    min_x, min_y = coords[min_idx]
    max_x, max_y = coords[max_idx]
    draw.ellipse((min_x - 3, min_y - 3, min_x + 3, min_y + 3), fill=(105, 194, 255))
    draw.ellipse((max_x - 3, max_y - 3, max_x + 3, max_y + 3), fill=(255, 218, 88))

    return {"min": vmin, "max": vmax, "first": vals[0], "last": vals[-1]}


def draw_sparkline_message(draw, msg, x, y, w, h, font, fill):
    msg_w, msg_h = text_size(draw, msg, font)
    draw.text(
        (x + (w - msg_w) / 2, y + (h - msg_h) / 2),
        msg,
        fill=fill,
        font=font,
    )

# Pin configs 
RST = 27
DC = 25
BL = 18
bus = 0 
device = 0 
logging.basicConfig(level=logging.DEBUG)
latest_log_handler = LatestLogHandler()
latest_log_handler.setFormatter(logging.Formatter("%(levelname).1s %(message)s"))
logging.getLogger().addHandler(latest_log_handler)

LOG_INTERVAL = 60
SPARKLINE_WINDOW_SECONDS = 24 * 60 * 60


def merge_temp_points(*point_sets):
    points_by_ts = {}
    for points in point_sets:
        for ts, temp_c in points:
            points_by_ts[int(ts)] = float(temp_c)

    return sorted(points_by_ts.items())


def trim_points(points, cutoff_ts):
    return [(ts, temp_c) for ts, temp_c in points if ts >= cutoff_ts]

def shutdown(signum, frame):
    logging.info(f"received signal {signum}, shutting down")
    if disp is not None:
        disp.module_exit()
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown)

def main():
    global disp

    try:
        conn = init_db()
        logging.info("[db] initialized")

        disp = LCD_2inch.LCD_2inch()
        # Initialize library.
        disp.Init()
        # Clear display.
        disp.clear()
        # Set the backlight to 50%.
        disp.bl_DutyCycle(50)

        font_temp = ImageFont.truetype("agamefont.ttf", 30)
        font_small = ImageFont.truetype("agamefont.ttf", 16)
        font_tiny = ImageFont.truetype("agamefont.ttf", 14)
        puffer_img = load_puffer_image()

        last_log = 0
        live_points = []
        # keep it running forever
        while True:
            # refresh image each time
            image = Image.new("RGB", (disp.height, disp.width), SCREEN_BG)
            draw = ImageDraw.Draw(image)
            screen_w, _ = image.size

            curr_temp = temp.read_temp()
            curr_time = datetime.now(tz=DISPLAY_TZ)
            curr_time_str = curr_time.strftime("%m/%d %H:%M")

            # log temperature to db
            now_ts = time.time()
            now_ts_int = int(now_ts)
            if not live_points or live_points[-1][0] != now_ts_int:
                live_points.append((now_ts_int, curr_temp))

            if now_ts - last_log >= LOG_INTERVAL:
                temp.log_temp(conn, curr_temp, now_ts_int)
                last_log = now_ts
                live_points = [(now_ts_int, curr_temp)]
                logging.info(f"[db] logged {curr_temp:.3f}C")

            live_points = trim_points(
                live_points,
                now_ts_int - SPARKLINE_WINDOW_SECONDS,
            )

            curr_status = "warming up"
            # get temp trend to derive status
            temps_1hr = merge_temp_points(temp.get_last_1hr(conn), live_points)
            if temps_1hr and len(temps_1hr) > 2:
                first = float(temps_1hr[0][1])
                last = float(temps_1hr[-1][1])

                res = round(last - first, 1)
                if res > 1:
                    curr_status = f"rising +{res:.1f}C/hr"
                elif res < -1:
                    curr_status = f"falling {res:.1f}C/hr"
                else:
                    curr_status = f"stable {res:+.1f}C/hr"

            logging.debug(f"[temp]: {curr_temp}")
            logging.debug(f"[timestamp]: {curr_time_str}")
            logging.debug(f"[status]: {curr_status}")

            # header
            draw.text((8, 7), format_temp(curr_temp), fill="WHITE", font=font_temp)
            draw_right_aligned(draw, curr_time_str, screen_w - 8, 10, font_small, (212, 222, 222))
            draw.text((8, 42), curr_status, fill=(168, 224, 184), font=font_small)

            paste_centered(image, puffer_img, screen_w / 2, 60)

            # 24h sparkline
            temps_24hr_db = temp.get_last_24h(conn)
            temps_24hr = merge_temp_points(temps_24hr_db, live_points)
            spark_stats = draw_sparkline(
                draw,
                temps_24hr,
                8,
                164,
                screen_w - 16,
                58,
                font_tiny,
                now_ts=now_ts_int,
                window_seconds=SPARKLINE_WINDOW_SECONDS,
            )
            spark_label = f"24h db{len(temps_24hr_db)}"
            draw.text((8, 146), spark_label, fill=(150, 160, 160), font=font_tiny)
            if spark_stats:
                spark_label_w, _ = text_size(draw, spark_label, font_tiny)
                draw.text(
                    (16 + spark_label_w, 146),
                    f"min {format_temp(spark_stats['min'])}",
                    fill=(116, 198, 255),
                    font=font_tiny,
                )
                draw_right_aligned(
                    draw,
                    f"max {format_temp(spark_stats['max'])}",
                    screen_w - 8,
                    146,
                    font_tiny,
                    (255, 220, 95),
                )

            log_line = fit_text(draw, latest_log_message, font_tiny, screen_w - 16)
            draw.text((8, 229), log_line, fill=(115, 128, 128), font=font_tiny)

            disp.ShowImage(image)
            # TODO: figure out optimal polling period
            time.sleep(1)

    except IOError as e:
        logging.info(e)
    except KeyboardInterrupt:
        if disp is not None:
            disp.module_exit()
        logging.info("quit:")
        exit()


if __name__ == "__main__":
    main()
