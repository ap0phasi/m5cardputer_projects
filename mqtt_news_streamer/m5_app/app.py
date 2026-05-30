import os, sys
import M5
from M5 import *
import asyncio
from hardware import MatrixKeyboard
import time
from umqtt.simple import MQTTClient
import network
import json

SCREEN_W         = 240
SCREEN_H         = 135
CURSOR_R         = 5
SQUARE_W         = 30
SQUARE_H         = 30
GYRO_SCALE       = 800
DEAD_ZONE        = 0.015
EMA_ALPHA        = 0.1
KEY_STEP         = 10
FRAME_MS         = 16
DOT_RADIUS       = 6
HOVER_RADIUS     = 25

MQTT_BROKER      = "broker.emqx.io"
MQTT_CLIENT_ID   = "cardputer_001"

# ── Topic config: add as many as you like ────────────────────────────────────
TOPICS = [
    {"topic": b"cardputer/corner/0", "x":  40, "y":  30},
    {"topic": b"cardputer/corner/1", "x": 200, "y":  30},
    {"topic": b"cardputer/corner/2", "x":  40, "y": 100},
    {"topic": b"testtopic/bdc",      "x": 200, "y": 100},
]
# ─────────────────────────────────────────────────────────────────────────────

WIFI_CONFIG_PATH = "/wifi_config.json"

circle0 = None
label0  = None
rect0   = None
kb      = None
mqtt    = None

circle_x      = 120
circle_y      = 67
start_ax      = 0.0
start_ay      = 0.0
smooth_ax     = 0.0
smooth_ay     = 0.0
active_topic  = -1
topic_msgs    = ["No message"] * len(TOPICS)

wifi_ssid     = ""
wifi_password = ""
input_buffer  = ""
input_mode    = False
input_prompt  = ""
input_done    = False
input_masked  = False


def clamp(val, lo, hi):
    return max(lo, min(hi, val))


def get_hovered(sq_x, sq_y):
    cx = sq_x + SQUARE_W // 2
    cy = sq_y + SQUARE_H // 2
    for i, t in enumerate(TOPICS):
        dx = cx - t["x"]
        dy = cy - t["y"]
        if (dx * dx + dy * dy) <= HOVER_RADIUS * HOVER_RADIUS:
            return i
    return -1


def draw_dots(highlight=-1):
    for i, t in enumerate(TOPICS):
        if i == highlight:
            # Bright filled dot when hovered
            M5.Lcd.fillCircle(t["x"], t["y"], DOT_RADIUS, 0x00ccff)
            M5.Lcd.drawCircle(t["x"], t["y"], DOT_RADIUS + 2, 0x00ccff)
        else:
            # Dim filled dot normally
            M5.Lcd.fillCircle(t["x"], t["y"], DOT_RADIUS, 0x555555)


def wrap_text(text, max_chars):
    """Wrap text to fit within max_chars per line."""
    words = text.split(" ")
    lines = []
    line = ""
    
    for word in words:
        # If word itself is too long, break it
        if len(word) > max_chars:
            if line:
                lines.append(line)
                line = ""
            # Break long word into chunks
            for i in range(0, len(word), max_chars - 1):
                chunk = word[i:i + max_chars - 1]
                if i + max_chars - 1 < len(word):
                    lines.append(chunk + "-")
                else:
                    line = chunk
            continue
        
        # Try to add word to current line
        test_line = (line + " " + word).strip() if line else word
        if len(test_line) <= max_chars:
            line = test_line
        else:
            if line:
                lines.append(line)
            line = word
    
    if line:
        lines.append(line)
    
    return lines


def show_topic_message(index):
    M5.Lcd.fillScreen(0x000000)
    msg = topic_msgs[index]

    data = None
    try:
        data = json.loads(msg)
    except:
        pass

    if data and isinstance(data, dict):
        y = 3
        for k, v in data.items():
            if y > SCREEN_H - 15:
                break
            
            # Draw key
            M5.Lcd.setTextSize(1)
            M5.Lcd.setTextColor(0xffcc00, 0x000000)
            key_str = str(k).upper()
            if len(key_str) > 38:
                key_str = key_str[:37] + "~"
            M5.Lcd.drawString(key_str, 2, y)
            y += 11
            
            # Draw value with wrapping
            M5.Lcd.setTextSize(1)
            M5.Lcd.setTextColor(0xffffff, 0x000000)
            val_str = str(v)
            val_lines = wrap_text(val_str, 38)
            
            for vline in val_lines[:3]:  # Max 3 lines per value
                if y > SCREEN_H - 12:
                    break
                M5.Lcd.drawString(vline, 6, y)
                y += 11
            
            # Draw separator
            if y < SCREEN_H - 12:
                M5.Lcd.drawLine(0, y, SCREEN_W, y, 0x333333)
                y += 4

    elif data and isinstance(data, list):
        M5.Lcd.setTextSize(1)
        M5.Lcd.setTextColor(0xffffff, 0x000000)
        y = 3
        for i, item in enumerate(data):
            if y > SCREEN_H - 12:
                break
            
            # Format list item with index
            item_str = str(item)
            prefix = "{}. ".format(i + 1)
            
            # Wrap the item text
            max_chars = 38 - len(prefix)
            item_lines = wrap_text(item_str, max_chars)
            
            # Draw first line with prefix
            if item_lines:
                M5.Lcd.drawString(prefix + item_lines[0], 2, y)
                y += 11
                
                # Draw remaining lines indented
                for line in item_lines[1:3]:  # Max 2 more lines
                    if y > SCREEN_H - 12:
                        break
                    M5.Lcd.drawString("   " + line, 2, y)
                    y += 11
            
            y += 4  # Extra spacing between items

    else:
        # Plain text message
        M5.Lcd.setTextSize(1)
        M5.Lcd.setTextColor(0xffffff, 0x000000)
        
        # Wrap text to fit screen width (38 chars for size 1)
        lines = wrap_text(msg, 38)
        
        # Calculate starting Y to center vertically
        line_height = 12
        total_height = len(lines) * line_height
        y = max(3, (SCREEN_H - total_height) // 2)
        
        for line in lines:
            if y > SCREEN_H - 12:
                break
            # Center each line horizontally
            char_width = 6  # Approximate width for text size 1
            x = max(2, (SCREEN_W - len(line) * char_width) // 2)
            M5.Lcd.drawString(line, x, y)
            y += line_height

    # Always draw dots on top so you can see where you are
    draw_dots(highlight=index)


def draw_centered_text(lines, size=2, color=0xffffff, bg=0x000000):
    M5.Lcd.fillScreen(bg)
    M5.Lcd.setTextColor(color, bg)
    M5.Lcd.setTextSize(size)
    char_w = size * 6
    char_h = size * 10
    y = max(4, (SCREEN_H - len(lines) * (char_h + 4)) // 2)
    for l in lines:
        x = max(2, (SCREEN_W - len(l) * char_w) // 2)
        M5.Lcd.drawString(l, x, y)
        y += char_h + 4


def show_input_screen():
    M5.Lcd.fillScreen(0x000000)
    M5.Lcd.setTextColor(0xffffff, 0x000000)
    M5.Lcd.setTextSize(1)
    M5.Lcd.drawString(input_prompt, 4, 8)
    M5.Lcd.drawString("ENT=confirm  DEL=backspace", 4, 20)
    M5.Lcd.setTextSize(2)
    display_buf = ("*" * len(input_buffer)) if input_masked else input_buffer
    display_buf = display_buf[-18:]
    M5.Lcd.fillRect(0, 40, SCREEN_W, 30, 0x222222)
    M5.Lcd.drawString(display_buf + "_", 4, 46)


def on_mqtt_message(topic, msg):
    global topic_msgs, active_topic
    for i, t in enumerate(TOPICS):
        if topic == t["topic"]:
            topic_msgs[i] = msg.decode("utf-8")
            if active_topic == i:
                show_topic_message(i)
            break


def kb_pressed_event(kb_0):
    global circle_x, circle_y, start_ax, start_ay
    global smooth_ax, smooth_ay, input_buffer, input_mode, input_done

    if kb is None:
        return

    key = kb.get_string()

    if input_mode:
        if key == '\n' or key == '\r':
            input_done = True
        elif key == '\x08' or key == '\x7f':
            input_buffer = input_buffer[:-1]
            show_input_screen()
        elif len(key) == 1 and ord(key) >= 32:
            input_buffer += key
            show_input_screen()
        return

    if key == '/':
        circle_x = clamp(circle_x + KEY_STEP, CURSOR_R, SCREEN_W - CURSOR_R)
    elif key == ',':
        circle_x = clamp(circle_x - KEY_STEP, CURSOR_R, SCREEN_W - CURSOR_R)
    elif key == ';':
        circle_y = clamp(circle_y - KEY_STEP, CURSOR_R, SCREEN_H - CURSOR_R)
    elif key == '.':
        circle_y = clamp(circle_y + KEY_STEP, CURSOR_R, SCREEN_H - CURSOR_R)
    elif key == '`':
        ax, _, az = Imu.getAccel()
        start_ax  = ax
        start_ay  = az
        smooth_ax = 0.0
        smooth_ay = 0.0


async def prompt_input(prompt, masked=False):
    global input_buffer, input_mode, input_done, input_prompt, input_masked
    input_buffer  = ""
    input_mode    = True
    input_done    = False
    input_prompt  = prompt
    input_masked  = masked
    show_input_screen()
    while not input_done:
        await asyncio.sleep_ms(50)
    input_mode = False
    return input_buffer


def load_wifi_config():
    try:
        with open(WIFI_CONFIG_PATH, "r") as f:
            cfg = json.load(f)
            return cfg.get("ssid", ""), cfg.get("password", "")
    except:
        return "", ""


def save_wifi_config(ssid, password):
    try:
        with open(WIFI_CONFIG_PATH, "w") as f:
            json.dump({"ssid": ssid, "password": password}, f)
    except:
        pass


async def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected() and wlan.config("essid") == ssid:
        return True
    wlan.connect(ssid, password)
    draw_centered_text(["Connecting...", ssid])
    for _ in range(40):
        if wlan.isconnected():
            return True
        await asyncio.sleep_ms(250)
    return False


async def setup_wifi():
    global wifi_ssid, wifi_password
    wifi_ssid, wifi_password = load_wifi_config()
    while True:
        if not wifi_ssid:
            wifi_ssid     = await prompt_input("WiFi SSID:")
            wifi_password = await prompt_input("Password:", masked=True)
        ok = await connect_wifi(wifi_ssid, wifi_password)
        if ok:
            save_wifi_config(wifi_ssid, wifi_password)
            draw_centered_text(["Connected!", wifi_ssid])
            await asyncio.sleep_ms(1000)
            return
        else:
            draw_centered_text(["Failed.", "Try again?"], color=0xff4444)
            await asyncio.sleep_ms(1500)
            wifi_ssid = wifi_password = ""


async def main():
    global circle0, label0, rect0, kb, mqtt
    global circle_x, circle_y
    global start_ax, start_ay, smooth_ax, smooth_ay, active_topic

    M5.begin()
    Widgets.fillScreen(0x000000)

    kb = MatrixKeyboard()
    kb.set_callback(kb_pressed_event)

    await setup_wifi()

    Widgets.fillScreen(0x000000)
    circle0 = Widgets.Circle(circle_x, circle_y, CURSOR_R, 0xffffff, 0xffffff)
    label0  = Widgets.Label("", 4, 112, 1.0, 0xffffff, 0x000000, Widgets.FONTS.Montserrat18)
    rect0   = Widgets.Rectangle(circle_x, circle_y, SQUARE_W, SQUARE_H, 0xffffff, 0xdc1414)

    label0.setText("MQTT...")
    mqtt = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER)
    mqtt.set_callback(on_mqtt_message)
    mqtt.connect()
    for t in TOPICS:
        mqtt.subscribe(t["topic"])
    label0.setText("Ready")

    ax, _, az = Imu.getAccel()
    start_ax = ax
    start_ay = az

    draw_dots()

    while True:
        M5.update()

        try:
            mqtt.check_msg()
        except Exception:
            pass

        ax, _, az = Imu.getAccel()
        raw_ax = ax - start_ax
        raw_ay = az - start_ay

        if abs(raw_ax) < DEAD_ZONE:
            raw_ax = 0.0
        if abs(raw_ay) < DEAD_ZONE:
            raw_ay = 0.0

        smooth_ax = EMA_ALPHA * raw_ax + (1 - EMA_ALPHA) * smooth_ax
        smooth_ay = EMA_ALPHA * raw_ay + (1 - EMA_ALPHA) * smooth_ay

        sq_x = clamp(circle_x - (smooth_ax * GYRO_SCALE), 0, SCREEN_W - SQUARE_W)
        sq_y = clamp(circle_y - (smooth_ay * GYRO_SCALE), 0, SCREEN_H - SQUARE_H)

        hovered = get_hovered(sq_x, sq_y)

        if hovered != active_topic:
            active_topic = hovered
            if hovered == -1:
                M5.Lcd.fillScreen(0x000000)
                draw_dots()
            else:
                show_topic_message(hovered)

        rect0.setCursor(x=round(sq_x), y=round(sq_y))
        circle0.setCursor(x=circle_x, y=circle_y)

        await asyncio.sleep_ms(FRAME_MS)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (asyncio.CancelledError, KeyboardInterrupt) as e:
        from utility import print_error_msg
        print_error_msg(e)
    except ImportError:
        print("please update to latest firmware")
