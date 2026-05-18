# full_esp32_dashboard_updated.py
import serial, time, csv, os, math, threading, re
import tkinter as tk
from collections import deque
from datetime import datetime

# ---------------- USER SETTINGS ----------------
PORT = "COM5"
BAUD_RATE = 115200
UPDATE_INTERVAL = 120  # ms
RADAR_MAX_DISTANCE = 20.0  # meters
SMOOTH_FACTOR = 0.25
TRAIL_LENGTH = 6
BASE_LOG_DIR = "logs"
FILTER_ESP32_MACS = True
ESP32_MACS = set()
UNKNOWN_STRONG_RSSI_THRESHOLD = -55
TAMPER_NO_DATA_SECS = 30

# ---------------- STATE ----------------
wifiList, bleList, btList, magList = [], [], [], []
mag_samples = deque(maxlen=50)
devices = {}
serial_buffer = ""
frame_count = 0
wifi_scroll = ble_scroll = bt_scroll = mag_scroll = 0
last_data_time = time.time()
current_heading = 0.0
motionActive = False
serial_activity_counter = 0
ser = None
stop_threads = False
highlight_enabled = True

# ---------------- Logging ----------------
os.makedirs(BASE_LOG_DIR, exist_ok=True)
today = datetime.now().strftime("%Y-%m-%d")
daily_dir = os.path.join(BASE_LOG_DIR, today)
os.makedirs(daily_dir, exist_ok=True)
LOG_FILENAME = os.path.join(daily_dir, "esp32_detections_log.csv")
TAMPER_LOG_FILENAME = os.path.join(daily_dir, "tamper_log.csv")
if not os.path.exists(LOG_FILENAME):
    with open(LOG_FILENAME, "w", newline='', encoding='utf-8') as f:
        csv.writer(f).writerow(["timestamp_utc","type","nic","name","mac","rssi","txPower","ip","extra"])
if not os.path.exists(TAMPER_LOG_FILENAME):
    with open(TAMPER_LOG_FILENAME, "w", newline='', encoding='utf-8') as f:
        csv.writer(f).writerow(["timestamp_utc","event_type","reason","details"])

def utcnow_iso(): return datetime.utcnow().isoformat()
def log_row(type_, nic, name="", mac="", rssi=None, txPower=None, ip="", extra=""):
    ts = utcnow_iso()
    with open(LOG_FILENAME, "a", newline='', encoding='utf-8') as f:
        csv.writer(f).writerow([ts,type_,nic,name,mac,("" if rssi is None else rssi),("" if txPower is None else txPower),ip,extra])
def log_tamper(event_type, reason, details=""):
    ts = utcnow_iso()
    with open(TAMPER_LOG_FILENAME, "a", newline='', encoding='utf-8') as f:
        csv.writer(f).writerow([ts,event_type,reason,details])

# ---------------- Serial connection ----------------
def connect_locked(port):
    global ser
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=0.1)
        print("Connected to", port)
        return ser
    except Exception as e:
        ser = None
        log_tamper("serial_connect_fail", "Cannot open port", str(e))
        print("Serial connect failed:", e)
        return None

connect_locked(PORT)

# ---------------- Device registration ----------------
def estimate_meters_from_rssi(rssi, txPower=-50):
    try:
        return min(max(0.1, 10 ** ((txPower - rssi)/(10*2.0))), RADAR_MAX_DISTANCE)
    except: return RADAR_MAX_DISTANCE

def register_or_update_device(nic, name, mac, rssi, dtype, txPower=-50):
    global devices
    mac_norm = mac.lower().replace("-",":")
    if FILTER_ESP32_MACS and mac_norm in ESP32_MACS: return None
    now = time.time()
    angle_deg = (hash(mac_norm) % 360)
    meters = estimate_meters_from_rssi(rssi, txPower)
    entry = devices.get(mac_norm)
    if not entry:
        entry = {"name":name,"mac":mac_norm,"rssi":rssi,"nic":nic,"dtype":dtype,"angle_deg":angle_deg,
                 "dist_m":meters,"x":None,"y":None,"trail":deque(maxlen=TRAIL_LENGTH),
                 "last_seen":now,"txPower":txPower}
        devices[mac_norm]=entry
    else:
        entry.update({"name":name,"rssi":rssi,"nic":nic,"dtype":dtype,"angle_deg":angle_deg,
                      "dist_m":meters,"last_seen":now,"txPower":txPower})
    return entry

# ---------------- Alerts ----------------
def trigger_alert(reason, details=""):
    log_tamper("intrusion_alert", reason, details)
    try: import winsound; winsound.MessageBeep()
    except: 
        try: root.bell()
        except: pass
    popup = tk.Toplevel(root)
    popup.attributes("-topmost", True)
    popup.configure(bg="red")
    popup.geometry("520x160")
    tk.Label(popup, text="INTRUSION ALERT", font=("Courier", 24, "bold"), bg="red", fg="white").pack(pady=8)
    tk.Label(popup, text=reason, font=("Courier", 12), bg="red", fg="white").pack()
    tk.Label(popup, text=details, font=("Courier", 10), bg="red", fg="white").pack()
    tk.Button(popup, text="Close", command=popup.destroy, font=("Courier",12)).pack(pady=8)

# ---------------- Serial line parser ----------------
def parse_line(line):
    global wifiList, bleList, btList, magList, current_heading, motionActive, last_data_time
    line=line.strip()
    if not line: return
    serial_activity_counter = 0
    parts = line.split(",")
    typ = parts[0].upper()

    # Motion
    if typ=="MOTION" and len(parts)>=2:
        motionActive = bool(int(parts[1]))
        last_data_time = time.time()
        return

    # Magnetometer
    if typ=="MAG":
        try:
            x = int(re.search(r"X=(-?\d+)", line).group(1))
            y = int(re.search(r"Y=(-?\d+)", line).group(1))
            z = int(re.search(r"Z=(-?\d+)", line).group(1))
            magList.append((x,y,z))
            current_heading = (math.degrees(math.atan2(y,x))) % 360
            mag_samples.appendleft((x,y,z))  # store newest on top
        except: pass
        last_data_time = time.time()
        return

    # IMU
    if typ=="IMU" and len(parts)>=6:
        last_data_time = time.time()
        return

    # Devices
    if typ in ["WIFI","BLE"]:
        name = parts[1]; rssi = int(float(parts[2])); mac = f"{typ}_{name}"; tx = -50
    elif typ=="BT" and len(parts)>=6:
        name = parts[1]; mac = parts[2]; rssi = int(float(parts[3])); tx = int(float(parts[4]))
    else: return

    entry = register_or_update_device(typ,name,mac,rssi,typ,tx)
    tup = (name,mac,rssi,tx)
    if typ=="WIFI" and tup not in wifiList: wifiList.append(tup)
    elif typ=="BLE" and tup not in bleList: bleList.append(tup)
    elif typ=="BT" and tup not in btList: btList.append(tup)
    last_data_time = time.time()

# ---------------- Serial reader thread ----------------
def serial_reader_thread():
    global serial_buffer, ser, stop_threads
    while not stop_threads:
        if ser is None:
            connect_locked(PORT)
            time.sleep(1)
            continue
        try:
            if ser.in_waiting:
                chunk = ser.read(ser.in_waiting).decode(errors='ignore')
                if chunk: serial_buffer += chunk
        except:
            ser.close(); ser=None; time.sleep(1); continue
        while "\n" in serial_buffer:
            line, serial_buffer = serial_buffer.split("\n",1)
            parse_line(line)
        time.sleep(0.01)

# ---------------- Distance ----------------
def estimate_distance_feet(rssi, txPower=-50):
    try: meters = 10 ** ((txPower - rssi)/(10*2.0))
    except: meters = RADAR_MAX_DISTANCE
    return meters*3.28084

# ---------------- GUI Colors ----------------
HIGHLIGHT_STRONG="#1a3d1a"; HIGHLIGHT_NEW="#1a1a3d"; HIGHLIGHT_BOTH="#2d2d2d"

# ---------------- Drawing helpers ----------------
def draw_rssi_bar_in_stats(canvas,x,y,w,label,rssi,txPower,color_fill):
    canvas.create_text(x+6,y+2,anchor="nw",text=label,fill="white",font=("Courier",11,"bold"))
    feet=int(estimate_distance_feet(rssi,txPower))
    canvas.create_text(x+6,y+16,anchor="nw",text=f"{rssi} dB {feet} ft",fill="white",font=("Courier",10))
    max_meter_w=w-20
    normalized=(max(-100,min(-30,rssi))+100)/70.0
    meter_w=int(max_meter_w*normalized)
    canvas.create_rectangle(x+10,y+34,x+10+max_meter_w,y+40,outline="gray50")
    if meter_w>0: canvas.create_rectangle(x+10,y+34,x+10+meter_w,y+40,fill=color_fill,outline="")

def display_scan_panel(canvas,x,y,width,height,device_list,title,color,scroll_index):
    row_height=22
    max_rows=max(1,int(height/row_height)-3)
    canvas.create_text(x+10,y+5,anchor="nw",text=title,fill="white",font=("Courier",14,"bold"))
    if not device_list:
        canvas.create_text(x+10,y+35,anchor="nw",text="No devices detected",fill=color,font=("Courier",12))
        return scroll_index
    newest_device=max(device_list,key=lambda d:d[2],default=None)
    strongest_rssi=max([rssi for _,_,rssi,_ in device_list],default=-1000)
    for i in range(min(len(device_list),max_rows)):
        idx=(scroll_index+i)%len(device_list)
        name,mac,rssi,tx=device_list[idx]
        row_y1=y+30+i*row_height; row_y2=row_y1+row_height
        bg=None
        is_strong=(rssi==strongest_rssi)
        is_newest=(newest_device is not None and name==newest_device[0] and mac==newest_device[1])
        if highlight_enabled:
            if is_strong and is_newest: bg=HIGHLIGHT_BOTH
            elif is_strong: bg=HIGHLIGHT_STRONG
            elif is_newest: bg=HIGHLIGHT_NEW
        if bg: canvas.create_rectangle(x,row_y1,x+width,row_y2,fill=bg,outline="")
        pref=">> " if is_strong else "   "
        display_name=(name[:18]+"..") if len(name)>20 else name
        dist=estimate_distance_feet(rssi,tx)
        canvas.create_text(x+10,row_y1+4,anchor="nw",
                           text=f"{pref}{display_name:20} {mac} Sig:{rssi} TX:{tx} Dist:{int(dist)}ft",
                           fill=color,font=("Courier",9))
    return scroll_index

def display_mag_list_panel(canvas, x, y, width, height, scroll_index=0):
    canvas.create_text(x+10, y+5, anchor="nw", text="Magnetometer Samples", fill="white", font=("Courier",14,"bold"))
    row_height = 20
    max_rows = max(1, int(height/row_height)-2)
    if not mag_samples:
        canvas.create_text(x+10, y+30, anchor="nw", text="No samples yet", fill="gray", font=("Courier",11))
        return scroll_index
    for i in range(min(len(mag_samples), max_rows)):
        idx = (scroll_index+i) % len(mag_samples)
        x_val, y_val, z_val = mag_samples[idx]
        canvas.create_text(x+10, y+30+i*row_height, anchor="nw",
                           text=f"X:{x_val:5} Y:{y_val:5} Z:{z_val:5}", fill="lightgreen", font=("Courier",10))
    return scroll_index

def draw_stats_panel(canvas,x,y,width):
    canvas.create_text(x,y,anchor="nw",text="Network Statistics",fill="white",font=("Courier",14,"bold"))
    cy=y+28
    for dev_type,device_list,fill_color in [("Wi-Fi",wifiList,"lightgreen"),("BLE",bleList,"cyan"),("BT",btList,"orange")]:
        canvas.create_text(x,cy,anchor="nw",text=f"{dev_type} Devices Found: {len(device_list)}",fill="white",font=("Courier",12))
        cy+=18
        if device_list:
            strongest=max(device_list,key=lambda d:d[2])
            closest=min(device_list,key=lambda d: estimate_distance_feet(d[2]))
            canvas.create_text(x,cy,anchor="nw",text=f"Strongest: {strongest[2]} dB ({strongest[0]})",fill="lightgreen",font=("Courier",11))
            cy+=16
            canvas.create_text(x,cy,anchor="nw",text=f"Closest: {closest[0]} ({int(estimate_distance_feet(closest[2]))} ft)",fill="cyan",font=("Courier",11))
            cy+=18
            draw_rssi_bar_in_stats(canvas,x,cy,width,f"{dev_type} Strength",strongest[2],strongest[3],fill_color)
            cy+=50
        else:
            draw_rssi_bar_in_stats(canvas,x,cy,width,f"{dev_type} Strength",-100,-50,"gray")
            cy+=50

def draw_centered_radar(canvas,w,h):
    global frame_count
    cx,cy=w//2,h//2+10
    size=int(min(w,h)*0.38)
    canvas.create_oval(cx-size,cy-size,cx+size,cy+size,outline="gray40")
    for i in range(1,4):
        r=int(size*i/4)
        canvas.create_oval(cx-r,cy-r,cx+r,cy+r,outline="gray30")
        canvas.create_text(cx+r+8,cy,text=f"{int(RADAR_MAX_DISTANCE*i/4)}m",fill="gray60",anchor="w",font=("Courier",9))
    sweep_angle=(frame_count*3)%360
    sweep_rad=math.radians(sweep_angle+current_heading)
    canvas.create_line(cx,cy,cx+size*math.cos(sweep_rad),cy+size*math.sin(sweep_rad),fill="green",width=2)
    banner_text="NEARBY!" if motionActive or any(d[2]>=-55 for d in wifiList+bleList+btList) else "NO MOTION"
    canvas.create_text(10,6,anchor="nw",text=banner_text,fill="white",font=("Courier",18,"bold"))
    now=time.time()
    stale=[m for m,d in list(devices.items()) if now-d["last_seen"]>90]
    for m in stale: del devices[m]
    for mac,d in devices.items():
        r=int((d["dist_m"]/RADAR_MAX_DISTANCE)*size)
        angle_rad=math.radians(d["angle_deg"]+current_heading)
        tx=cx+r*math.cos(angle_rad)
        ty=cy+r*math.sin(angle_rad)
        if d["x"] is None or d["y"] is None: d["x"],d["y"]=tx,ty
        d["x"]+= (tx-d["x"])*SMOOTH_FACTOR
        d["y"]+= (ty-d["y"])*SMOOTH_FACTOR
        d["trail"].append((d["x"],d["y"]))
        color="cyan" if d["dtype"]=="BLE" else ("orange" if d["dtype"]=="BT" else "lightgreen")
        rsize=4
        canvas.create_oval(d["x"]-rsize,d["y"]-rsize,d["x"]+rsize,d["y"]+rsize,fill=color,outline="")
        if len(d["trail"])>1:
            for i in range(1,len(d["trail"])):
                x0,y0=d["trail"][i-1]; x1,y1=d["trail"][i]
                canvas.create_line(x0,y0,x1,y1,fill=color)

# ---------------- Dashboard update ----------------
def update_dashboard():
    global frame_count, wifi_scroll, ble_scroll, bt_scroll, mag_scroll, last_data_time
    frame_count += 1
    canvas.delete("all")
    w,h=canvas.winfo_width(),canvas.winfo_height()
    panel_h=int(h*0.45)

    wifi_scroll=display_scan_panel(canvas,8,8,int(w*0.25),panel_h,wifiList,"Wi-Fi Devices","lightgreen",wifi_scroll)
    ble_scroll=display_scan_panel(canvas,int(w*0.25)+10,8,int(w*0.25),panel_h,bleList,"BLE Devices","cyan",ble_scroll)
    bt_scroll=display_scan_panel(canvas,int(w*0.5)+12,8,int(w*0.25),panel_h,btList,"BT Devices","orange",bt_scroll)
    mag_scroll=display_mag_list_panel(canvas,int(w*0.75)+14,8,int(w*0.25)-20,panel_h,mag_scroll)

    draw_centered_radar(canvas,w,h)
    draw_stats_panel(canvas,8,panel_h+5,int(w*0.75))

    inactive_for=time.time()-last_data_time
    color="red" if ser is None or inactive_for>TAMPER_NO_DATA_SECS else ("yellow" if inactive_for>5 else "green")
    status_text="Serial: DISCONNECTED" if ser is None else f"Serial: {'OFFLINE' if inactive_for>TAMPER_NO_DATA_SECS else 'IDLE' if inactive_for>5 else 'ACTIVE'} ({inactive_for:.0f}s)"
    canvas.create_oval(w-46,6,w-14,34,fill=color)
    canvas.create_text(w-48-180,6,anchor="nw",text=status_text,fill="white",font=("Courier",11,"bold"))

    root.after(UPDATE_INTERVAL, update_dashboard)

# ---------------- Keyboard toggle ----------------
def toggle_highlight(event=None):
    global highlight_enabled
    highlight_enabled = not highlight_enabled

# ---------------- GUI ----------------
root=tk.Tk()
root.title("ESP32 Multi-Device Radar Dashboard")
canvas=tk.Canvas(root,bg="black")
canvas.pack(fill=tk.BOTH,expand=True)
root.bind("<h>",toggle_highlight)
threading.Thread(target=serial_reader_thread,daemon=True).start()
update_dashboard()
root.mainloop()
stop_threads=True
