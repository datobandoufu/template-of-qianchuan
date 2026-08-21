# -*- coding: utf-8 -*-
"""千川素材监控看板 - 桌面应用入口（系统托盘，无 cmd 窗口）。

功能：
- 后台启动静态文件服务（output/dashboard，绑定 0.0.0.0，供本机/局域网/内网穿透访问）；
- 系统托盘图标：左键/双击打开本机看板；右键菜单含「打开看板 / 重启服务 / 退出」；
- 单实例：若端口已被本程序占用，则只显示托盘而不重复启动服务；
- 若本项目尚未生成看板（output/dashboard/index.html 不存在），仅提示而不启动空服务。

端口：默认 8931。若与其他项目冲突，请同时修改本文件 PORT 与 启动看板.bat 中的 PORT。

打包：python -m PyInstaller --onefile --noconsole monitor/dashboard_app.py ...
生成 exe 后放在项目根目录使用（服务目录固定为 exe 同目录下的 output/dashboard）。
"""
import os
import sys
import threading
import webbrowser
import logging
from logging.handlers import RotatingFileHandler

# ---------- 路径定位 ----------
# onefile 打包后 sys.executable 为 exe 路径；开发态为脚本路径
BASE = os.path.dirname(os.path.abspath(
    sys.executable if getattr(sys, "frozen", False) else __file__))
DASH_DIR = os.path.join(BASE, "output", "dashboard")
INDEX_FILE = os.path.join(DASH_DIR, "index.html")
HOST = "0.0.0.0"
PORT = 8931
URL = f"http://127.0.0.1:{PORT}"
LOG_FILE = os.path.join(BASE, "看板服务.log")

# ---------- 日志（windowed 无控制台，全部写文件） ----------
_handler = RotatingFileHandler(LOG_FILE, maxBytes=1024 * 1024,
                               backupCount=2, encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[_handler])
log = logging.getLogger("dash")


def port_in_use(host, port):
    """主动连接探测端口是否已被占用（Windows 下 SO_REUSEADDR 语义不同，
    直接 bind 不一定失败，故用连接探测更可靠）。"""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(0.3)
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def setup_http_server():
    """启动静态文件服务线程；端口已被占用时返回 None。"""
    import http.server
    import socketserver

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=DASH_DIR, **kwargs)

        def log_message(self, fmt, *args):
            log.info("%s - %s", self.address_string(), fmt % args)

    # 注意：Windows 下不可用 allow_reuse_address（SO_REUSEADDR 语义不同，
    # 会导致端口被占用时仍绑定"成功"，破坏单实例保护）。
    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True

    if port_in_use("127.0.0.1", PORT):
        log.warning("端口 %s 已有服务在监听，不重复启动。", PORT)
        return None

    try:
        httpd = Server((HOST, PORT), QuietHandler)
    except OSError as e:
        log.warning("端口 %s 绑定失败（%s），不重复启动服务。", PORT, e)
        return None

    thread = threading.Thread(target=httpd.serve_forever, daemon=True,
                              name="httpd")
    thread.start()
    log.info("看板服务已启动: %s (目录 %s)", URL, DASH_DIR)
    return httpd


# ---------- 托盘图标 ----------
import pystray
from PIL import Image, ImageDraw

ICON_BG = (30, 91, 76)
ICON_FG = (255, 255, 255)


def make_icon():
    img = Image.new("RGB", (64, 64), ICON_BG)
    d = ImageDraw.Draw(img)
    # 画一个简易柱状图图标
    for i, h in enumerate((20, 34, 46)):
        x0 = 10 + i * 16
        d.rectangle([x0, 64 - h, x0 + 10, 62], fill=ICON_FG)
    d.ellipse([8, 6, 56, 30], outline=ICON_FG, width=4)
    return img


class App:
    def __init__(self):
        self.httpd = None
        self.started = False
        self._lock = threading.Lock()

    def ensure_started(self):
        with self._lock:
            if self.started:
                return
            self.httpd = setup_http_server()
            self.started = True

    def open_browser(self, icon=None, item=None):
        webbrowser.open(URL)
        log.info("打开本机看板 %s", URL)

    def restart(self, icon=None, item=None):
        with self._lock:
            if self.httpd is not None:
                try:
                    self.httpd.shutdown()
                    self.httpd.server_close()
                except Exception as e:
                    log.warning("关闭旧服务异常: %s", e)
                self.httpd = None
            self.started = False
        log.info("重启服务...")
        self.ensure_started()
        webbrowser.open(URL)

    def quit(self, icon=None, item=None):
        log.info("退出看板应用")
        try:
            if self.httpd is not None:
                self.httpd.shutdown()
                self.httpd.server_close()
        except Exception as e:
            log.warning("退出时关闭服务异常: %s", e)
        if icon is not None:
            icon.stop()
        os._exit(0)


def main():
    app = App()
    if not os.path.exists(INDEX_FILE):
        # 本项目尚未生成看板：不启动空服务，避免误连到别的项目
        log.warning("未找到看板数据 %s，请先运行 一键导入 生成看板后再启动。", INDEX_FILE)
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showwarning(
                "千川素材监控看板",
                "尚未生成看板数据。\n\n请先运行「一键导入.bat」导入日报数据后，再启动看板。")
            root.destroy()
        except Exception:
            pass
        return
    app.ensure_started()
    if app.httpd is None:
        # 端口被占用：仅打开浏览器，提示已有服务在运行
        log.info("端口 %s 已有服务，直接打开看板。", PORT)
        webbrowser.open(URL)

    icon = pystray.Icon(
        "material_monitor_dashboard",
        make_icon(),
        title="千川素材监控看板",
        menu=pystray.Menu(
            pystray.MenuItem("打开看板", app.open_browser, default=True),
            pystray.MenuItem("重启服务", app.restart),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", app.quit),
        ),
    )
    icon.run()


if __name__ == "__main__":
    main()
