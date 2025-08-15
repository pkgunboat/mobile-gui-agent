from flask import Flask, request, jsonify, send_file, abort
from flask_cors import CORS
from dataclasses import dataclass
from PIL import Image
import subprocess
import logging
import time
import os

WAIT_TIME = 3
RETRY_INTERVAL = 1
LOCK_TIMEOUT = 10

# ADB_PATH = 'The Path To ADB'
ADB_PATH = "~/software/adb/platform-tools-latest-linux/platform-tools/adb"
SCREENSHOT_DIR = './screenshot'
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

app = Flask(__name__)
CORS(app)  # 启用跨域支持

@dataclass
class AndroidEnv:
    adb_path: str
    start_time: float = time.time()

    def run_command(self, command: str):
        full_command = f"{self.adb_path} {command}"
        result = subprocess.run(full_command, capture_output=True, text=True, shell=True)
        logging.info(f"Executed: {full_command}\n{result.stdout}\n{result.stderr}")
        return result

    def get_screenshot(self):
        self.run_command("shell screencap -p /sdcard/screenshot.png")
        time.sleep(0.5)
        self.run_command(f"pull /sdcard/screenshot.png {SCREENSHOT_DIR}/screenshot.png")
        time.sleep(0.5)
        self.run_command("shell rm /sdcard/screenshot.png")
        # time.sleep(0.5)SW
        image_path = f"{SCREENSHOT_DIR}/screenshot.png"
        save_path = f"{SCREENSHOT_DIR}/screenshot.jpg"
        
        image = Image.open(image_path)
        image.convert("RGB").save(save_path, "JPEG")
        os.remove(image_path)
        return save_path

    # def get_screenshot(self):
    #     self.run_command("shell rm /sdcard/screenshot.png")
    #     time.sleep(0.5)
    #     self.run_command("shell screencap -p /sdcard/screenshot.png")
    #     time.sleep(0.5)
    #     self.run_command(f"pull /sdcard/screenshot.png {SCREENSHOT_DIR}/screenshot.png")
        
    #     image_path = f"{SCREENSHOT_DIR}/screenshot.png"
    #     save_path = f"{SCREENSHOT_DIR}/screenshot.jpg"
        
    #     image = Image.open(image_path)
    #     image.convert("RGB").save(save_path, "JPEG")
    #     os.remove(image_path)
    #     return save_path
    def get_screenshot(self):
        remote_path = "/sdcard/screenshot.png"
        local_path = f"{SCREENSHOT_DIR}/screenshot.png"
        save_path = f"{SCREENSHOT_DIR}/screenshot.jpg"

        # 1. 手机上截图
        self.run_command(f"shell screencap -p {remote_path}")
        # 2. 拉到本地
        self.run_command(f"pull {remote_path} {local_path}")
        # 3. 删除手机上的截图
        self.run_command(f"shell rm {remote_path}")

        # 4. 转换为 JPG
        if os.path.exists(local_path):
            image = Image.open(local_path)
            image.convert("RGB").save(save_path, "JPEG")
            os.remove(local_path)
        else:
            raise FileNotFoundError(f"Screenshot not found: {local_path}")
        return save_path


    def tap(self, x, y):
        self.run_command(f"shell input tap {x} {y}")

    def type_text(self, text):
        text = text.replace("\\n", "_").replace("\n", "_")
        for char in text:
            if char == ' ':
                self.run_command("shell input text %s")
            elif char == '_':
                self.run_command("shell input keyevent 66")
            elif 'a' <= char <= 'z' or 'A' <= char <= 'Z' or char.isdigit():
                self.run_command(f"shell input text {char}")
            elif char in '-.,!?@\'°/:;()':
                self.run_command(f"shell input text \"{char}\"")
            else:
                self.run_command(f"shell am broadcast -a ADB_INPUT_TEXT --es msg \"{char}\"")

    def slide(self, x1, y1, x2, y2):
        self.run_command(f"shell input swipe {x1} {y1} {x2} {y2} 500")

    def back(self):
        self.run_command("shell input keyevent 4")

    def home(self):
        self.run_command("shell am start -a android.intent.action.MAIN -c android.intent.category.HOME")

    def long_press(self, x, y):
        self.run_command(f"shell input swipe {x} {y} {x} {y} 1000")
    # def back(self):
    #     self.tap(x=250, y=2300)
    #     # command = adb_path + f" shell input keyevent 4"
    #     # subprocess.run(command, capture_output=True, text=True, shell=True)
        
        
    # def home(self):
    #     self.tap(x=500, y=2300)
    # # command = adb_path + f" shell am start -a android.intent.action.MAIN -c android.intent.category.HOME"
    # # subprocess.run(command, capture_output=True, text=True, shell=True)


# 初始化设备对象（可根据实际情况管理多个设备）
android_env = AndroidEnv(adb_path=ADB_PATH)


@app.route("/ping", methods=["GET"])
def read_root():
    return {"message": "Hello, World!"}


@app.route("/screenshot", methods=["GET"])
def screenshot():
    try:
        path = android_env.get_screenshot()
        return send_file(path, mimetype="image/jpeg")
    except Exception as e:
        logging.error(str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/action", methods=["POST"])
def action_exe():
    data = request.get_json()
    try:
        action_type = data.get("type")
        if action_type == "tap":
            x, y = data["x"], data["y"]
            android_env.tap(x, y)
        elif action_type == "type":
            text = data["text"]
            android_env.type_text(text)
        elif action_type == "slide":
            x1, y1, x2, y2 = data["x1"], data["y1"], data["x2"], data["y2"]
            android_env.slide(x1, y1, x2, y2)
        elif action_type == "back":
            android_env.back()
        elif action_type == "home":
            android_env.home()
        elif action_type == "long_press":
            x, y = data["x"], data["y"]
            android_env.long_press(x, y)
        else:
            return jsonify({"error": "Unknown action type"}), 400
        return jsonify({"status": "success"})
    except Exception as e:
        logging.error(str(e))
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=False, host="0.0.0.0", port=50005)
