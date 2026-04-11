import glob
import time

base_dir = '/sys/bus/w1/devices/'
device_folder = glob.glob(base_dir + '28*')[0]
device_file = device_folder + '/w1_slave'

def read_temp_raw():
    f = open(device_file, 'r')
    lines = f.readlines()
    f.close()
    return lines
 
def read_temp():
    """
    strips the unecessary info from the raw temp file and returns it in celsius
    """
    lines = read_temp_raw()
    while lines[0].strip()[-3:] != 'YES':
        time.sleep(0.2)
        lines = read_temp_raw()
    equals_pos = lines[1].find('t=')
    if equals_pos != -1:
        temp_string = lines[1][equals_pos+2:]
        temp_c = float(temp_string) / 1000.0
        return temp_c

def log_temp(conn, temp_c, ts=None):
    if ts is None:
        ts = int(time.time())
    conn.execute(
        "INSERT INTO temperature_log (ts, temp_c) VALUES (?, ?)",
        (ts, temp_c),
    )
    conn.commit()


def get_last_24h(conn):
    cutoff = int(time.time()) - 86400
    cur = conn.execute(
        "SELECT ts, temp_c FROM temperature_log WHERE ts >= ? ORDER BY ts",
        (cutoff,),
    )
    return cur.fetchall()

def get_last_1hr(conn):
    cutoff = int(time.time()) - 3600
    cur = conn.execute(
        "SELECT ts, temp_c FROM temperature_log WHERE ts >= ? ORDER BY ts",
        (cutoff,),
    )
    return cur.fetchall()

def delete_old_data(conn, days=30):
    cutoff = int(time.time()) - days * 86400
    conn.execute("DELETE FROM temperature_log WHERE ts < ?", (cutoff,))
    conn.commit()