"""
Tarih Köşesi — Masaüstü Widget
"""
import sys
import ctypes
import json
import random
import os
import re
import winreg
import tempfile
import threading
import urllib.request
import winsound
import subprocess
import pprint
from datetime import date, datetime

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QSystemTrayIcon, QMenu, QAction,
    QCheckBox, QSlider, QMessageBox, QButtonGroup, QStackedWidget
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QFont, QColor, QPainter, QPainterPath,
    QCursor, QIcon, QPixmap, QPen
)

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

APP_NAME     = "TarihKöşesi"
APP_VERSION  = "1.0.1"
WIDGET_W     = 320
WIDGET_H     = 185
SERIT_W      = 4
KUTLAMA_MOD  = 100
GORULDU_SAVE = 10

OLAYLAR_URL   = "https://raw.githubusercontent.com/flu31/tarih-kosesi-olaylar/refs/heads/main/olaylar.json"
VERSION_URL   = "https://raw.githubusercontent.com/flu31/tarih-kosesi-olaylar/main/version.json"
RELEASE_URL   = "https://github.com/flu31/tarih-kosesi-olaylar/releases/latest/download/TarihKosesi.exe"
SES_DOSYASI  = r"C:\Windows\Media\tada.wav"
IPC_FILE     = os.path.join(tempfile.gettempdir(), "tarih_kosesi_ipc.txt")

FONTLAR = {
    "varsayilan": "Segoe UI",
    "serif":      "Georgia",
    "mono":       "Consolas",
}

ARKAPLAN_ACIK = (220, 215, 205)
ARKAPLAN_KOYU = (25, 25, 35)

GECERLI = {
    "font":             set(FONTLAR.keys()),
    "kose":             {"yuvarlak", "keskin", "tek_sol", "tek_sag"},
    "opaklik":          range(20, 101),
    "baslangic":        {True, False},
    "kilitli":          {True, False},
    "baslangic_goster": {True, False},
    "serit_goster":     {True, False},
    "arkaplan_modu":    {"cag", "acik", "koyu"},
    "ses_acik":         {True, False},
}

CAGLAR = [
    {"ad": "Prehistorik", "bas": None,  "bit": -3200, "bg": (44,31,20),  "acc": "#c8a97a"},
    {"ad": "İlk Çağ",     "bas": -3200, "bit": 375,   "bg": (42,34,0),   "acc": "#f0c040"},
    {"ad": "Orta Çağ",    "bas": 375,   "bit": 1453,  "bg": (26,10,46),  "acc": "#9b6bb5"},
    {"ad": "Yeni Çağ",    "bas": 1453,  "bit": 1789,  "bg": (46,16,16),  "acc": "#c0603a"},
    {"ad": "Yakın Çağ",   "bas": 1789,  "bit": None,  "bg": (15,26,46),  "acc": "#5b8db8"},
]

KUTLAMA_RENKLER = ["#f0c040","#9b6bb5","#c0603a","#5b8db8","#c8a97a","#e07070","#70c0e0"]

TEXT_COLOR      = "#f0ece0"
TEXT_COLOR_ACIK = "#1a1510"
DIM_COLOR       = "#8a8070"
DIM_COLOR_ACIK  = "#6a6060"
LOCK_FILE       = os.path.join(tempfile.gettempdir(), "tarih_kosesi.lock")


# ── Yardımcı ─────────────────────────────────────────────────────────────────

def get_appdata():
    """Ayarlar ve indirilen olaylar.json icin APPDATA/TarihKosesi klasoru."""
    path = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "TarihKosesi")
    os.makedirs(path, exist_ok=True)
    return path


def get_bundled():
    """EXE içine gömülü dosyalar için yol (PyInstaller _MEIPASS)."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def get_base():
    """Geriye dönük uyumluluk için — ayarlar klasörünü döner."""
    return get_appdata()


def yil_to_int(s):
    if not s:
        return 1800
    m = re.search(r"\d+", s)
    if not m:
        return 1800
    n = int(m.group())
    return -n if any(t in s for t in ("MÖ", "M.Ö", "mö", "BC")) else n


def get_cag(yil_str):
    y = yil_to_int(yil_str)
    for c in CAGLAR:
        bas, bit = c["bas"], c["bit"]
        if bas is None and y < bit:
            return c
        if bit is None and y >= bas:
            return c
        if bas is not None and bit is not None and bas <= y < bit:
            return c
    return CAGLAR[-1]


def get_colors(yil_str, arkaplan_modu="cag"):
    c = get_cag(yil_str)
    if arkaplan_modu == "acik":
        return {"bg": ARKAPLAN_ACIK, "acc": c["acc"], "ad": c["ad"],
                "text": TEXT_COLOR_ACIK, "dim": DIM_COLOR_ACIK,
                "border": "#00000033"}
    elif arkaplan_modu == "koyu":
        return {"bg": ARKAPLAN_KOYU, "acc": c["acc"], "ad": c["ad"],
                "text": TEXT_COLOR, "dim": DIM_COLOR,
                "border": "#ffffff33"}
    else:
        return {"bg": c["bg"], "acc": c["acc"], "ad": c["ad"],
                "text": TEXT_COLOR, "dim": DIM_COLOR,
                "border": "#ffffff33"}


def set_autostart(enable):
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enable:
            exe = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe}"')
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print(f"Autostart hatası: {e}")


def cal_ses():
    if not os.path.exists(SES_DOSYASI):
        return
    def _cal():
        try:
            winsound.PlaySound(SES_DOSYASI, winsound.SND_FILENAME)
        except Exception as e:
            print(f"Ses hatası: {e}")
    threading.Thread(target=_cal, daemon=True).start()


def make_tray_icon(acc, bg):
    px = QPixmap(32, 32)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    r, g, b = bg
    p.setBrush(QColor(r, g, b))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(2, 2, 28, 28, 5, 5)
    p.setBrush(QColor(acc))
    p.drawRoundedRect(2, 2, 28, 9, 5, 5)
    p.drawRect(2, 7, 28, 4)
    p.setPen(QColor(acc))
    p.drawLine(8, 18, 24, 18)
    p.drawLine(8, 24, 18, 24)
    p.end()
    return QIcon(px)


def make_pin_icon(locked):
    """İğne ikonu — yuvarlak baş, ince çubuk. Kilitliyken baş dolu, açıkken boş."""
    px = QPixmap(10, 14)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    color = QColor(DIM_COLOR)
    pen = QPen(color)
    pen.setWidth(1)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)

    if locked:
        p.setBrush(color)
    else:
        p.setBrush(Qt.NoBrush)
    p.drawEllipse(2, 0, 6, 6)

    p.setBrush(color)
    p.drawLine(5, 6, 5, 13)

    p.end()
    return QIcon(px)


def best_screen(widget):
    s = QApplication.screenAt(widget.geometry().center())
    return s or QApplication.primaryScreen()


def safe_pos(x, y, w, h):
    for s in QApplication.screens():
        g = s.availableGeometry()
        if g.left() <= x < g.right() and g.top() <= y < g.bottom():
            return min(x, g.right() - w), min(y, g.bottom() - h)
    g = QApplication.primaryScreen().availableGeometry()
    return g.right() - w - 24, g.bottom() - h - 48


def check_single_instance():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE) as f:
                pid = int(f.read().strip())
            handle = ctypes.windll.kernel32.OpenProcess(0x400, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return False
        except Exception:
            pass
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    return True


def remove_lock():
    try:
        os.remove(LOCK_FILE)
    except Exception:
        pass


def gun_farki(tarih_str):
    try:
        ilk = date.fromisoformat(tarih_str)
        return (date.today() - ilk).days
    except Exception:
        return 0


def yerel_olay_sayisi():
    try:
        # Önce appdata, sonra bundle
        appdata_p = os.path.join(get_appdata(), "olaylar.json")
        bundled_p = os.path.join(get_bundled(), "olaylar.json")
        path = appdata_p if os.path.exists(appdata_p) else bundled_p
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return len([e for e in data if isinstance(e, dict)
                    and "yil" in e and "olay" in e and e["yil"] and e["olay"]])
    except Exception:
        return 0


def guncelleme_kontrol(widget):
    """GitHub'daki version.json'ı kontrol eder, yeni sürüm varsa sinyal gönderir."""
    def _kontrol():
        try:
            req = urllib.request.Request(
                VERSION_URL,
                headers={"User-Agent": "TarihKosesi/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            uzak_versiyon = data.get("version", "0.0.0")
            print(f"[GUNCELLEME] Uzak: {uzak_versiyon}, Yerel: {APP_VERSION}")
            if uzak_versiyon != APP_VERSION:
                widget.sig_guncelleme_var.emit(uzak_versiyon)
        except Exception as e:
            print(f"Sürüm kontrol hatası: {e}")
    threading.Thread(target=_kontrol, daemon=True).start()


def guncelleme_baslat(exe_yolu):
    """Updater'ı başlatıp uygulamayı kapatır."""
    updater_yolu = os.path.join(os.path.dirname(exe_yolu), "updater.exe")
    if not os.path.exists(updater_yolu):
        # Geliştirme modunda updater.py kullan
        updater_yolu = os.path.join(get_bundled(), "updater.exe")
    if not os.path.exists(updater_yolu):
        import webbrowser
        webbrowser.open("https://github.com/flu31/tarih-kosesi-olaylar/releases/latest")
        return
    subprocess.Popen([updater_yolu, exe_yolu, RELEASE_URL])
    QApplication.quit()


def guncelle_olaylar(on_done=None, force=False):
    def _indir():
        try:
            req = urllib.request.Request(
                OLAYLAR_URL,
                headers={"User-Agent": "TarihKosesi/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            if data.startswith(b'\xef\xbb\xbf'):
                data = data[3:]
            parsed = json.loads(data.decode('utf-8'))
            if not isinstance(parsed, list) or len(parsed) == 0:
                return
            valid = [e for e in parsed if isinstance(e, dict)
                     and "yil" in e and "olay" in e and e["yil"] and e["olay"]]
            if not valid:
                return
            if not force and len(valid) == yerel_olay_sayisi():
                return
            path = os.path.join(get_appdata(), "olaylar.json")
            with open(path, "wb") as f:
                f.write(data)
            print(f"Güncelleme: {len(valid)} olay indirildi.")
            if on_done:
                QTimer.singleShot(0, lambda: on_done(valid))
        except Exception as e:
            print(f"Güncelleme hatası: {e}")
    threading.Thread(target=_indir, daemon=True).start()


def saat_basi_saniye():
    now = datetime.now()
    return 3600 - (now.minute * 60 + now.second)


def kose_path(kose, w, h, r=14):
    path = QPainterPath()
    if kose == "keskin":
        path.addRect(0, 0, w, h)
    elif kose == "tek_sol":
        path.moveTo(0, 0)
        path.lineTo(w - r, 0)
        path.quadTo(w, 0, w, r)
        path.lineTo(w, h - r)
        path.quadTo(w, h, w - r, h)
        path.lineTo(0, h)
        path.closeSubpath()
    elif kose == "tek_sag":
        path.moveTo(r, 0)
        path.lineTo(w, 0)
        path.lineTo(w, h)
        path.lineTo(r, h)
        path.quadTo(0, h, 0, h - r)
        path.lineTo(0, r)
        path.quadTo(0, 0, r, 0)
        path.closeSubpath()
    else:
        path.addRoundedRect(0, 0, w, h, r, r)
    return path


def send_debug_command(args):
    cmd_map = {
        "--next":          "next",
        "--prev":          "prev",
        "--reset-deck":    "reset-deck",
        "--reset-goruldu": "reset-goruldu",
        "--show":          "show",
        "--hide":          "hide",
        "--reload":        "reload",
        "--info":          "info",
        "--kutlama":       "kutlama",
        "--force-update":  "force-update",
        "--settings":      "settings",
        "--crash":         "crash",
        "--status":        "status",
        "--deck-size":     "deck-size",
        "--log":           "log",
    }
    cmd = None
    for i, arg in enumerate(args):
        if arg in cmd_map:
            cmd = cmd_map[arg]
            break
        elif arg == "--opacity" and i + 1 < len(args):
            cmd = f"opacity:{args[i+1]}"
            break
        elif arg == "--theme" and i + 1 < len(args):
            cmd = f"theme:{args[i+1]}"
            break
        elif arg == "--font" and i + 1 < len(args):
            cmd = f"font:{args[i+1]}"
            break
    if cmd:
        with open(IPC_FILE, "w") as f:
            f.write(cmd)
        print(f"Komut gönderildi: {cmd}")
    else:
        print("Kullanım: python widget.py [KOMUT] [DEĞER]")


# ── DataManager ───────────────────────────────────────────────────────────────

class DataManager:
    DEFAULTS = {
        "baslangic":        False,
        "opaklik":          100,
        "kilitli":          False,
        "pos_x":            None,
        "pos_y":            None,
        "font":             "varsayilan",
        "kose":             "yuvarlak",
        "goruldu":          0,
        "baslangic_goster": True,
        "serit_goster":     True,
        "arkaplan_modu":    "cag",
        "ses_acik":         True,
        "ilk_kullanim":     None,
        "mevcut_olay_idx":  None,
        "kapanma_saati":    None,
    }

    def __init__(self):
        self._base    = get_base()
        self.events   = self._load_events()
        self.settings = self._load_settings()
        self.ilk_acilis = self.settings.get("ilk_kullanim") is None
        self._ilk_kullanim_kaydet()

    def _load_events(self):
        # Önce %APPDATA%/TarihKosesi/olaylar.json (güncelleme), sonra bundle
        for path in [os.path.join(get_appdata(), "olaylar.json"),
                     os.path.join(get_bundled(), "olaylar.json")]:
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                valid = [e for e in data if isinstance(e, dict)
                         and "yil" in e and "olay" in e and e["yil"] and e["olay"]]
                if valid:
                    return valid
            except Exception:
                continue
        QMessageBox.critical(None, "Hata", "olaylar.json bulunamadi!")
        sys.exit(1)

    def _load_settings(self):
        s = dict(self.DEFAULTS)
        try:
            path = os.path.join(get_appdata(), "ayarlar.json")
            with open(path, encoding="utf-8") as f:
                s.update(json.load(f))
        except Exception:
            pass
        return self._validate(s)

    def _validate(self, s):
        result = dict(self.DEFAULTS)
        for key, default in self.DEFAULTS.items():
            val = s.get(key, default)
            gecerli = GECERLI.get(key)
            if gecerli is None:
                if key in ("ilk_kullanim", "kapanma_saati"):
                    if val is not None and not isinstance(val, str):
                        val = default
                elif key in ("pos_x", "pos_y", "mevcut_olay_idx"):
                    if val is not None and not isinstance(val, int):
                        val = default
                elif val is not None and not isinstance(val, (int, float)):
                    val = default
            elif isinstance(gecerli, set):
                if val not in gecerli:
                    val = default
            elif isinstance(gecerli, range):
                if not isinstance(val, int) or val not in gecerli:
                    val = default
            result[key] = val
        return result

    def _ilk_kullanim_kaydet(self):
        if self.settings.get("ilk_kullanim") is None:
            self.settings["ilk_kullanim"] = date.today().isoformat()
            self.save()

    def save(self):
        path = os.path.join(get_appdata(), "ayarlar.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, ensure_ascii=False, indent=2)

    def get(self, key):
        return self.settings.get(key, self.DEFAULTS.get(key))

    def set(self, key, value, autosave=True):
        self.settings[key] = value
        if autosave:
            self.save()

    def reset(self):
        goruldu      = self.settings.get("goruldu", 0)
        ilk_kullanim = self.settings.get("ilk_kullanim")
        self.settings = dict(self.DEFAULTS)
        self.settings["goruldu"]      = goruldu
        self.settings["ilk_kullanim"] = ilk_kullanim
        self.save()


# ── ChoiceButton ──────────────────────────────────────────────────────────────

class ChoiceButton(QPushButton):
    def __init__(self, label, key):
        super().__init__(label)
        self.key = key
        self.setFixedHeight(24)
        self.setFont(QFont("Segoe UI", 9))
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setCheckable(True)

    def style_active(self, acc, bg):
        r, g, b = bg
        self.setStyleSheet(f"""
            QPushButton {{
                background: {acc}; color: rgb({r},{g},{b});
                border-radius: 4px; border: none; font-weight: bold;
            }}
        """)

    def style_inactive(self, dim=DIM_COLOR):
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {dim};
                border-radius: 4px; border: 1px solid {dim}55;
            }}
            QPushButton:hover {{ background: {dim}22; }}
        """)


# ── SectionBox ────────────────────────────────────────────────────────────────

class SectionBox(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        self._lay = lay
        self._bg_color = QColor(60, 40, 20)
        self._border_color = QColor(255, 255, 255, 40)
        self._radius = 7

    def add(self, w):
        if isinstance(w, QWidget):
            self._lay.addWidget(w)
        else:
            self._lay.addLayout(w)

    def set_colors(self, c):
        r, g, b = c["bg"]
        if r + g + b < 300:
            dr = min(255, r + 45)
            dg = min(255, g + 45)
            db = min(255, b + 45)
            self._border_color = QColor(255, 255, 255, 40)
        else:
            dr = max(0, r - 40)
            dg = max(0, g - 40)
            db = max(0, b - 40)
            self._border_color = QColor(0, 0, 0, 40)
        self._bg_color = QColor(dr, dg, db)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), self._radius, self._radius)
        p.fillPath(path, self._bg_color)
        pen = QPen(self._border_color)
        pen.setWidth(1)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(0, 0, self.width()-1, self.height()-1, self._radius, self._radius)


# ── WelcomeWindow ─────────────────────────────────────────────────────────────

class WelcomeWindow(QWidget):

    def __init__(self, dm, on_close):
        super().__init__()
        self._dm       = dm
        self._on_close = on_close
        self._drag_pos = None
        self._bg_color = QColor(26, 21, 16)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(360, 380)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        inner = QWidget(self)
        inner.setAttribute(Qt.WA_TranslucentBackground)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(28, 28, 28, 24)
        lay.setSpacing(0)

        # Başlık
        title = QLabel("Tarih Köşesi'ne Hoş Geldiniz 👋")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setStyleSheet("color: #c8a97a; line-height: 1.3;")
        title.setWordWrap(True)
        lay.addWidget(title)
        lay.addSpacing(6)

        sub = QLabel("Her saat başı masaüstünüzde yeni bir tarihi olay.")
        sub.setFont(QFont("Segoe UI", 9))
        sub.setStyleSheet("color: #8a8070;")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        lay.addSpacing(20)

        # İpuçları
        tips = [
            ("🖱️  Sürükle",     "Widget'ı masaüstünde istediğin yere taşıyabilirsin."),
            ("📌  İğne butonu", "İğneye basarak widget'ı sabit bir konuma kilitleyebilirsin."),
            ("⚙️  Ayarlar",     "≡ butonuyla tema, yazı tipi ve ses ayarlarını değiştirebilirsin."),
            ("📋  Kopyala",     "Olay metnine sağ tıklayarak içeriği panoya kopyalayabilirsin."),
        ]

        for icon_title, desc in tips:
            row = QHBoxLayout()
            row.setSpacing(12)

            dot = QWidget()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet("background: #c8a97a; border-radius: 4px;")

            text_col = QVBoxLayout()
            text_col.setSpacing(1)

            t = QLabel(icon_title)
            t.setFont(QFont("Segoe UI", 9, QFont.Bold))
            t.setStyleSheet("color: #f0ece0;")

            d = QLabel(desc)
            d.setFont(QFont("Segoe UI", 8))
            d.setStyleSheet("color: #8a8070;")
            d.setWordWrap(True)

            text_col.addWidget(t)
            text_col.addWidget(d)

            row.addWidget(dot, 0, Qt.AlignTop | Qt.AlignHCenter)
            row.addLayout(text_col, 1)
            lay.addLayout(row)
            lay.addSpacing(10)

        lay.addSpacing(10)

        # Buton
        btn = QPushButton("Başla →")
        btn.setFixedHeight(38)
        btn.setFont(QFont("Segoe UI", 10, QFont.Bold))
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setStyleSheet("""
            QPushButton {
                background: #c8a97a; color: #0e0c09;
                border-radius: 4px; border: none;
            }
            QPushButton:hover { background: #e8cfa0; }
        """)
        btn.clicked.connect(self._kapat)
        lay.addWidget(btn)

        root.addWidget(inner)

    def _kapat(self):
        self.hide()
        self._on_close()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 14, 14)
        p.fillPath(path, self._bg_color)
        pen = QPen(QColor(200, 169, 122, 60))
        pen.setWidth(1)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(0, 0, self.width()-1, self.height()-1, 14, 14)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and self._drag_pos:
            self.move(e.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, _):
        self._drag_pos = None



# ── SettingsWindow ────────────────────────────────────────────────────────────

class SettingsWindow(QWidget):

    sig_guncel        = pyqtSignal()
    sig_guncelleme    = pyqtSignal(str)
    sig_hata          = pyqtSignal()

    def __init__(self, dm, on_change, get_yil):
        super().__init__()
        self._dm        = dm
        self._on_change = on_change
        self._get_yil   = get_yil
        self._drag_pos  = None
        self._groups    = []
        self._sections  = []
        self._bg_color  = QColor(44, 26, 8)
        self._border_color = QColor(255, 255, 255, 50)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(300, 380)
        self._build()
        self.sig_guncel.connect(self._guncel_slot)
        self.sig_guncelleme.connect(self._kontrol_bitti_slot)
        self.sig_hata.connect(self._guncelleme_hata)
        self.refresh_theme()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._inner = QWidget(self)
        self._inner.setAttribute(Qt.WA_TranslucentBackground)
        cl = QVBoxLayout(self._inner)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(0)

        # Başlık
        top = QHBoxLayout()
        self._t_title = QLabel("Ayarlar")
        self._t_title.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self._t_close = QPushButton("✕")
        self._t_close.setFixedSize(18, 18)
        self._t_close.setFlat(True)
        self._t_close.setCursor(QCursor(Qt.PointingHandCursor))
        self._t_close.clicked.connect(self.hide)
        top.addWidget(self._t_title)
        top.addStretch()
        top.addWidget(self._t_close)
        cl.addLayout(top)
        cl.addSpacing(8)

        # Sekmeler
        sekme_row = QHBoxLayout()
        sekme_row.setSpacing(0)
        self._sekme_btns = []
        for i, label in enumerate(["Görünüm", "Davranış", "Hakkında"]):
            btn = QPushButton(label)
            btn.setFixedHeight(24)
            btn.setFont(QFont("Segoe UI", 9))
            btn.setFlat(True)
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.clicked.connect(lambda _, idx=i: self._switch_tab(idx))
            self._sekme_btns.append(btn)
            sekme_row.addWidget(btn)
        cl.addLayout(sekme_row)
        cl.addSpacing(7)

        self._stack = QStackedWidget()
        self._stack.setAttribute(Qt.WA_TranslucentBackground)

        # ── Görünüm ──
        gorunum = QWidget()
        gorunum.setAttribute(Qt.WA_TranslucentBackground)
        glay = QVBoxLayout(gorunum)
        glay.setContentsMargins(0, 0, 0, 0)
        glay.setSpacing(6)

        s_opak = SectionBox()
        opak_row = QHBoxLayout()
        self._t_opak = QLabel("Opaklık")
        self._t_opak.setFont(QFont("Segoe UI", 10))
        self._t_opak_val = QLabel(f"%{self._dm.get('opaklik')}")
        self._t_opak_val.setFont(QFont("Segoe UI", 9))
        self._t_opak_val.setFixedWidth(32)
        self._t_opak_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        opak_row.addWidget(self._t_opak)
        opak_row.addStretch()
        opak_row.addWidget(self._t_opak_val)
        s_opak.add(opak_row)
        self._sl_opak = QSlider(Qt.Horizontal)
        self._sl_opak.setRange(20, 100)
        self._sl_opak.setValue(self._dm.get("opaklik"))
        self._sl_opak.setCursor(QCursor(Qt.PointingHandCursor))
        self._sl_opak.valueChanged.connect(self._on_opak)
        s_opak.add(self._sl_opak)
        glay.addWidget(s_opak)
        self._sections.append(s_opak)

        s_gorunum = SectionBox()
        s_gorunum.add(self._row_lbl("Köşe stili"))
        cur_kose = self._dm.get("kose")
        kose_cur = "tek_sol" if cur_kose in ("tek_sol","tek_sag") else cur_kose
        self._kose_btns = self._choice_row_w(
            [("yuvarlak","Yuvarlak"),("keskin","Keskin"),("tek_sol","Tek köşe")],
            kose_cur, self._on_kose)
        s_gorunum.add(self._kose_btns)
        s_gorunum.add(self._row_lbl("Yazı tipi"))
        self._font_btns = self._choice_row_w(
            [("varsayilan","Varsayılan"),("serif","Serif"),("mono","Mono")],
            self._dm.get("font"), self._on_font)
        s_gorunum.add(self._font_btns)
        s_gorunum.add(self._row_lbl("Tema"))
        self._arkaplan_btns = self._choice_row_w(
            [("cag","Çağ renkleri"),("acik","Açık"),("koyu","Koyu")],
            self._dm.get("arkaplan_modu"), self._on_arkaplan)
        s_gorunum.add(self._arkaplan_btns)
        self._chk_serit, _ = self._chk_row_w(
            s_gorunum, "Sol şerit", self._dm.get("serit_goster"), self._on_serit)
        glay.addWidget(s_gorunum)
        self._sections.append(s_gorunum)
        glay.addStretch()

        # ── Davranış ──
        davranis = QWidget()
        davranis.setAttribute(Qt.WA_TranslucentBackground)
        dlay = QVBoxLayout(davranis)
        dlay.setContentsMargins(0, 0, 0, 0)
        dlay.setSpacing(6)

        s_baslangic = SectionBox()
        self._chk_baslangic, _ = self._chk_row_w(
            s_baslangic, "Başlangıçta çalıştır",
            self._dm.get("baslangic"), self._on_bas)
        self._chk_goster, _ = self._chk_row_w(
            s_baslangic, "Başlangıçta görünür",
            self._dm.get("baslangic_goster"), self._on_goster)
        dlay.addWidget(s_baslangic)
        self._sections.append(s_baslangic)

        s_ses = SectionBox()
        self._chk_ses, ses_lbl = self._chk_row_w(
            s_ses, "Olay sesi", self._dm.get("ses_acik"), self._on_ses_acik)
        ses_lbl.setText("Olay sesi (sistem ses seviyesini kullanır)")
        self._btn_ses_test = QPushButton("▶ Sesi test et")
        self._btn_ses_test.setFixedHeight(24)
        self._btn_ses_test.setFont(QFont("Segoe UI", 9))
        self._btn_ses_test.setCursor(QCursor(Qt.PointingHandCursor))
        self._btn_ses_test.clicked.connect(self._ses_test)
        s_ses.add(self._btn_ses_test)
        dlay.addWidget(s_ses)
        self._sections.append(s_ses)
        dlay.addStretch()

        # ── Hakkında ──
        hakkinda = QWidget()
        hakkinda.setAttribute(Qt.WA_TranslucentBackground)
        hlay = QVBoxLayout(hakkinda)
        hlay.setContentsMargins(0, 0, 0, 0)
        hlay.setSpacing(6)

        s_istatistik = SectionBox()
        self._lbl_olay_sayisi  = QLabel("")
        self._lbl_goruldu      = QLabel("")
        self._lbl_ilk_kullanim = QLabel("")
        self._lbl_gun          = QLabel("")
        for lbl in (self._lbl_olay_sayisi, self._lbl_goruldu,
                    self._lbl_ilk_kullanim, self._lbl_gun):
            lbl.setFont(QFont("Segoe UI", 10))
            lbl.setObjectName("hakkinda_lbl")
            s_istatistik.add(lbl)
        hlay.addWidget(s_istatistik)
        self._sections.append(s_istatistik)

        s_versiyon = SectionBox()
        self._lbl_versiyon = QLabel(f"Versiyon: {APP_VERSION}")
        self._lbl_versiyon.setFont(QFont("Segoe UI", 10))
        self._lbl_versiyon.setObjectName("hakkinda_lbl")
        s_versiyon.add(self._lbl_versiyon)
        hlay.addWidget(s_versiyon)
        self._sections.append(s_versiyon)

        s_linkler = SectionBox()
        self._btn_github = QPushButton("GitHub →")
        self._btn_github.setFixedHeight(26)
        self._btn_github.setFont(QFont("Segoe UI", 9))
        self._btn_github.setCursor(QCursor(Qt.PointingHandCursor))
        self._btn_github.clicked.connect(lambda: __import__("webbrowser").open("https://github.com/flu31/tarih-kosesi-olaylar"))
        s_linkler.add(self._btn_github)
        self._btn_website = QPushButton("Web Sitesi →")
        self._btn_website.setFixedHeight(26)
        self._btn_website.setFont(QFont("Segoe UI", 9))
        self._btn_website.setCursor(QCursor(Qt.PointingHandCursor))
        self._btn_website.clicked.connect(lambda: __import__("webbrowser").open("https://flu31.github.io/tarih-kosesi-olaylar"))
        s_linkler.add(self._btn_website)
        hlay.addWidget(s_linkler)
        self._sections.append(s_linkler)

        s_guncelle = SectionBox()
        self._btn_guncelle = QPushButton("Güncelleme Kontrol Et")
        self._btn_guncelle.setFixedHeight(26)
        self._btn_guncelle.setFont(QFont("Segoe UI", 9))
        self._btn_guncelle.setCursor(QCursor(Qt.PointingHandCursor))
        self._btn_guncelle.clicked.connect(self._manuel_guncelleme_kontrol)
        s_guncelle.add(self._btn_guncelle)
        hlay.addWidget(s_guncelle)
        self._sections.append(s_guncelle)

        s_sifirla = SectionBox()
        self._btn_sifirla = QPushButton("Ayarları Sıfırla")
        self._btn_sifirla.setFixedHeight(26)
        self._btn_sifirla.setFont(QFont("Segoe UI", 9))
        self._btn_sifirla.setCursor(QCursor(Qt.PointingHandCursor))
        self._btn_sifirla.clicked.connect(self._sifirla)
        s_sifirla.add(self._btn_sifirla)
        hlay.addWidget(s_sifirla)
        self._sections.append(s_sifirla)
        hlay.addStretch()

        self._stack.addWidget(gorunum)
        self._stack.addWidget(davranis)
        self._stack.addWidget(hakkinda)

        cl.addWidget(self._stack, 1)
        root.addWidget(self._inner)

        self._current_tab = 0
        self._switch_tab(0)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 12, 12)
        p.fillPath(path, self._bg_color)
        pen = QPen(self._border_color)
        pen.setWidth(1)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(0, 0, self.width()-1, self.height()-1, 12, 12)

    def _row_lbl(self, text):
        lbl = QLabel(text)
        lbl.setFont(QFont("Segoe UI", 9))
        lbl.setObjectName("rowlbl")
        return lbl

    def _choice_row_w(self, choices, current, callback):
        container = QWidget()
        container.setAttribute(Qt.WA_TranslucentBackground)
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        group = QButtonGroup(container)
        self._groups.append(group)
        for key, label in choices:
            btn = ChoiceButton(label, key)
            btn.setChecked(key == current)
            btn.clicked.connect(lambda _, k=key, cb=callback: cb(k))
            group.addButton(btn)
            row.addWidget(btn)
        return container

    def _chk_row_w(self, section, text, checked, callback):
        row = QHBoxLayout()
        lbl = QLabel(text)
        lbl.setFont(QFont("Segoe UI", 10))
        lbl.setObjectName("rowlbl")
        chk = QCheckBox()
        chk.setCursor(QCursor(Qt.PointingHandCursor))
        chk.blockSignals(True)
        chk.setChecked(checked)
        chk.blockSignals(False)
        chk.stateChanged.connect(callback)
        row.addWidget(lbl)
        row.addStretch()
        row.addWidget(chk)
        section.add(row)
        return chk, lbl

    def _switch_tab(self, idx):
        self._current_tab = idx
        self._stack.setCurrentIndex(idx)
        if idx == 2:
            self._update_hakkinda()
        self._apply_tab_styles()

    def _apply_tab_styles(self):
        c = get_colors(self._get_yil(), self._dm.get("arkaplan_modu"))
        acc = c["acc"]
        for i, btn in enumerate(self._sekme_btns):
            if i == self._current_tab:
                btn.setStyleSheet(
                    f"color: {acc}; border-bottom: 2px solid {acc}; "
                    f"background: transparent; padding-bottom: 2px;"
                )
            else:
                btn.setStyleSheet(
                    f"color: {c['dim']}; border-bottom: 2px solid transparent; "
                    f"background: transparent; padding-bottom: 2px;"
                )

    def _update_hakkinda(self):
        goruldu     = self._dm.get("goruldu")
        olay_sayisi = len(self._dm.events)
        ilk         = self._dm.get("ilk_kullanim")
        gun         = gun_farki(ilk) if ilk else 0
        try:
            ilk_fmt = date.fromisoformat(ilk).strftime("%d %B %Y") if ilk else "—"
        except Exception:
            ilk_fmt = "—"
        gun_yazi = "Bugün başladın! 🎉" if gun == 0 else f"{gun} gündür kullanıyorsun"
        self._lbl_olay_sayisi.setText(f"📚 Olay veritabanı: {olay_sayisi}")
        self._lbl_goruldu.setText(f"👁 Toplam görülen: {goruldu}")
        self._lbl_ilk_kullanim.setText(f"📅 İlk kullanım: {ilk_fmt}")
        self._lbl_gun.setText(f"🗓 {gun_yazi}")

    def _on_opak(self, val):
        self._t_opak_val.setText(f"%{val}")
        self._dm.set("opaklik", val)
        self._on_change("opaklik")

    def _on_kose(self, key):
        if key == "tek_sol":
            mevcut = self._dm.get("kose")
            key = "tek_sag" if mevcut == "tek_sol" else "tek_sol"
        self._dm.set("kose", key)
        self._refresh_btn_styles()
        self._on_change("kose")

    def _on_font(self, key):
        self._dm.set("font", key)
        self._refresh_btn_styles()
        self._on_change("font")

    def _on_arkaplan(self, key):
        self._dm.set("arkaplan_modu", key)
        self._refresh_btn_styles()
        self.refresh_theme()
        self._on_change("arkaplan_modu")

    def _on_serit(self, state):
        self._dm.set("serit_goster", state == Qt.Checked)
        self._on_change("serit_goster")

    def _on_bas(self, state):
        val = (state == Qt.Checked)
        self._dm.set("baslangic", val)
        set_autostart(val)

    def _on_goster(self, state):
        self._dm.set("baslangic_goster", state == Qt.Checked)

    def _ses_test(self):
        """Sesi çalar, ses süresi boyunca butonu devre dışı bırakır."""
        self._btn_ses_test.setEnabled(False)
        cal_ses()
        QTimer.singleShot(3000, lambda: self._btn_ses_test.setEnabled(True))

    def _on_ses_acik(self, state):
        self._dm.set("ses_acik", state == Qt.Checked)

    def _manuel_guncelleme_kontrol(self):
        self._btn_guncelle.setEnabled(False)
        self._btn_guncelle.setText("Kontrol ediliyor...")
        # Kontrol et
        def _kontrol():
            try:
                print(f"[GUNCELLEME] Kontrol başlıyor: {VERSION_URL}")
                req = urllib.request.Request(VERSION_URL, headers={"User-Agent": "TarihKosesi/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw = resp.read().decode("utf-8")
                print(f"[GUNCELLEME] Yanıt: {raw}")
                data = json.loads(raw)
                uzak = data.get("version", "0.0.0")
                print(f"[GUNCELLEME] Uzak: {uzak}, Yerel: {APP_VERSION}")
                if uzak != APP_VERSION:
                    self.sig_guncelleme.emit(uzak)
                else:
                    self.sig_guncel.emit()
            except Exception as e:
                print(f"[GUNCELLEME] Hata: {e}")
                self.sig_hata.emit()
        threading.Thread(target=_kontrol, daemon=True).start()

    def _guncel_slot(self):
        self._btn_guncelle.setEnabled(True)
        self._btn_guncelle.setText("Güncelleme Kontrol Et")
        self.raise_()
        self.activateWindow()
        QMessageBox.information(self, "Güncelleme", f"Tarih Köşesi güncel! ({APP_VERSION})")

    def _kontrol_bitti_slot(self, yeni_versiyon):
        self._btn_guncelle.setEnabled(True)
        self._btn_guncelle.setText("Güncelleme Kontrol Et")
        cevap = QMessageBox.question(
            self, "Güncelleme Mevcut",
            f"Tarih Köşesi {yeni_versiyon} sürümü mevcut! Şimdi güncellemek ister misiniz?",
            QMessageBox.Yes | QMessageBox.No
        )
        if cevap == QMessageBox.Yes:
            exe_yolu = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)
            guncelleme_baslat(exe_yolu)

    def _guncelleme_hata(self):
        self._btn_guncelle.setEnabled(True)
        self._btn_guncelle.setText("Güncelleme Kontrol Et")
        QMessageBox.warning(self, "Hata", "Sunucuya bağlanılamadı.")

    def _sifirla(self):
        cevap = QMessageBox.question(
            self, "Ayarları Sıfırla",
            "Tüm ayarlar varsayılana dönecek.\n"
            "(Görülen olay sayısı ve ilk kullanım tarihi korunur)\n\n"
            "Devam edilsin mi?",
            QMessageBox.Yes | QMessageBox.No
        )
        if cevap == QMessageBox.Yes:
            self._dm.reset()
            self._sync_ui()
            self.refresh_theme()
            self._on_change("reset")

    def _sync_ui(self):
        for chk, val in [
            (self._chk_baslangic, "baslangic"),
            (self._chk_goster,    "baslangic_goster"),
            (self._chk_serit,     "serit_goster"),
            (self._chk_ses,       "ses_acik"),
        ]:
            chk.blockSignals(True)
            chk.setChecked(self._dm.get(val))
            chk.blockSignals(False)
        self._sl_opak.blockSignals(True)
        self._sl_opak.setValue(self._dm.get("opaklik"))
        self._t_opak_val.setText(f"%{self._dm.get('opaklik')}")
        self._sl_opak.blockSignals(False)
        self._refresh_btn_styles()

    def refresh_theme(self):
        c = get_colors(self._get_yil(), self._dm.get("arkaplan_modu"))
        r, g, b = c["bg"]
        acc = c["acc"]

        arkaplan = self._dm.get("arkaplan_modu")
        if arkaplan == "acik":
            ar, ag, ab = ARKAPLAN_ACIK
            self._bg_color = QColor(ar, ag, ab)
            self._border_color = QColor(0, 0, 0, 50)
        else:
            self._bg_color = QColor(r, g, b)
            self._border_color = QColor(255, 255, 255, 50)
        self.update()

        self._t_title.setStyleSheet(f"color: {acc};")
        self._t_close.setStyleSheet(
            f"color: {c['dim']}; border: none; background: transparent;"
        )
        for lbl in self.findChildren(QLabel, "rowlbl"):
            lbl.setStyleSheet(f"color: {c['text']}; background: transparent;")
        for lbl in self.findChildren(QLabel, "hakkinda_lbl"):
            lbl.setStyleSheet(f"color: {c['text']}; background: transparent;")
        self._t_opak.setStyleSheet(f"color: {c['text']}; background: transparent;")
        self._t_opak_val.setStyleSheet(f"color: {c['dim']}; background: transparent;")
        self._sl_opak.setStyleSheet(f"""
            QSlider::groove:horizontal {{ height: 3px; background: {c['dim']}44; border-radius: 2px; }}
            QSlider::handle:horizontal {{ width: 12px; height: 12px; margin: -5px 0; background: {acc}; border-radius: 6px; }}
            QSlider::sub-page:horizontal {{ background: {acc}; border-radius: 2px; }}
        """)
        for chk in (self._chk_baslangic, self._chk_goster, self._chk_serit, self._chk_ses):
            chk.setStyleSheet(f"color: {c['text']}; background: transparent;")
        self._btn_sifirla.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: #e07070;
                border-radius: 4px; border: 1px solid #e0707055;
            }}
            QPushButton:hover {{ background: #e0707022; }}
        """)
        link_style = f"""
            QPushButton {{
                background: transparent; color: {acc};
                border-radius: 4px; border: 1px solid {acc}55;
                text-align: left; padding-left: 4px;
            }}
            QPushButton:hover {{ background: {acc}22; }}
        """
        self._btn_github.setStyleSheet(link_style)
        self._btn_website.setStyleSheet(link_style)
        self._btn_ses_test.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {acc};
                border-radius: 4px; border: 1px solid {acc}55;
            }}
            QPushButton:hover {{ background: {acc}22; }}
        """)
        self._btn_guncelle.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {c['text']};
                border-radius: 4px; border: 1px solid {c['dim']}55;
            }}
            QPushButton:hover {{ background: {c['dim']}22; }}
            QPushButton:disabled {{ color: {c['dim']}; }}
        """)
        for sec in self._sections:
            sec.set_colors(c)
        self._refresh_btn_styles()
        self._apply_tab_styles()

    def _refresh_btn_styles(self):
        c = get_colors(self._get_yil(), self._dm.get("arkaplan_modu"))
        acc, bg, dim = c["acc"], c["bg"], c["dim"]
        kose = self._dm.get("kose")
        cur = {
            "kose":          "tek_sol" if kose in ("tek_sol","tek_sag") else kose,
            "font":          self._dm.get("font"),
            "arkaplan_modu": self._dm.get("arkaplan_modu"),
        }
        key_map = {
            "Yuvarlak":     ("kose","yuvarlak"),
            "Keskin":       ("kose","keskin"),
            "Tek köşe":     ("kose","tek_sol"),
            "Varsayılan":   ("font","varsayilan"),
            "Serif":        ("font","serif"),
            "Mono":         ("font","mono"),
            "Çağ renkleri": ("arkaplan_modu","cag"),
            "Açık":         ("arkaplan_modu","acik"),
            "Koyu":         ("arkaplan_modu","koyu"),
        }
        for btn in self.findChildren(ChoiceButton):
            mapped = key_map.get(btn.text())
            if mapped:
                grp, val = mapped
                if cur.get(grp) == val:
                    btn.style_active(acc, bg)
                else:
                    btn.style_inactive(dim)

    def open_for(self, parent_widget):
        for chk, val in [
            (self._chk_baslangic, "baslangic"),
            (self._chk_goster,    "baslangic_goster"),
            (self._chk_serit,     "serit_goster"),
            (self._chk_ses,       "ses_acik"),
        ]:
            chk.blockSignals(True)
            chk.setChecked(self._dm.get(val))
            chk.blockSignals(False)
        self._sl_opak.blockSignals(True)
        self._sl_opak.setValue(self._dm.get("opaklik"))
        self._t_opak_val.setText(f"%{self._dm.get('opaklik')}")
        self._sl_opak.blockSignals(False)
        self.refresh_theme()
        geo = best_screen(parent_widget).availableGeometry()
        self.move(
            geo.center().x() - self.width()  // 2,
            geo.center().y() - self.height() // 2,
        )
        self.show()
        self.raise_()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and self._drag_pos:
            self.move(e.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, _):
        self._drag_pos = None


# ── HistoryWidget ─────────────────────────────────────────────────────────────

class HistoryWidget(QWidget):

    sig_guncelleme_var = pyqtSignal(str)

    def __init__(self, dm):
        super().__init__()
        self._dm              = dm
        self._deck            = []
        self._drag_pos        = None
        self._locked          = dm.get("kilitli")
        self._current_yil     = "1800"
        self._current_olay    = ""
        self._current_idx     = None
        self._kutlama_aktif   = False
        self._kutlama_idx     = 0
        self._secs_left       = saat_basi_saniye()
        self._last_hour       = datetime.now().hour
        self._pin_yapildi     = False
        self._gizli_kullanici = not dm.get("baslangic_goster")

        self.sig_guncelleme_var.connect(self._on_guncelleme_var)
        self._init_window()
        self._build_ui()
        self._settings_win = SettingsWindow(
            dm, self._on_settings_changed, lambda: self._current_yil
        )
        self._init_tray()
        self._init_timers()
        self._restore_or_next()

        # İlk açılışta hoş geldin penceresi
        if dm.ilk_acilis:
            QTimer.singleShot(500, self._show_welcome)

    def _init_window(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(WIDGET_W, WIDGET_H)

        px, py = self._dm.get("pos_x"), self._dm.get("pos_y")
        if px is not None and py is not None:
            px, py = safe_pos(px, py, WIDGET_W, WIDGET_H)
        else:
            g = QApplication.primaryScreen().availableGeometry()
            px, py = g.right() - WIDGET_W - 24, g.bottom() - WIDGET_H - 48
        self.move(px, py)

    def showEvent(self, e):
        super().showEvent(e)
        if not self._pin_yapildi:
            self._pin_yapildi = True
            QTimer.singleShot(150, self._pin_to_desktop)
        else:
            # Her show'da GWL_HWNDPARENT yenile
            QTimer.singleShot(150, self._pin_to_desktop)

    def _pin_to_desktop(self):
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32

            # WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE ayarla
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_APPWINDOW  = 0x00040000
            GWL_EXSTYLE      = -20
            mevcut = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                (mevcut | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW
            )

            # Progman'a WorkerW oluşturmasını söyle
            progman = user32.FindWindowW("Progman", None)
            user32.SendMessageTimeoutW(progman, 0x052C, 0, 0, 0, 1000, None)

            # GWL_HWNDPARENT ile Progman'ı owner olarak set et
            # SetParent'tan farklı — render sistemi bozulmuyor
            GWL_HWNDPARENT = -8
            user32.SetWindowLongPtrW(hwnd, GWL_HWNDPARENT, progman)

            # HWND_BOTTOM'a koy
            HWND_BOTTOM = 1
            user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, 0x0002|0x0001|0x0010)

            print(f"[PIN] GWL_HWNDPARENT Progman'a set edildi: {progman:#x}")
        except Exception as e:
            print(f"Pin hatası: {e}")

    def _build_ui(self):
        fn    = FONTLAR.get(self._dm.get("font"), "Segoe UI")
        serit = self._dm.get("serit_goster")

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(
            (SERIT_W + 14) if serit else 14, 12, 14, 10
        )
        self._lay.setSpacing(3)

        top = QHBoxLayout()
        top.setSpacing(4)
        self._w_title = QLabel("📅 Tarih Köşesi")
        self._w_title.setFont(QFont(fn, 9, QFont.Bold))

        self._w_settings = QPushButton("≡")
        self._w_settings.setFixedSize(18, 18)
        self._w_settings.setFlat(True)
        self._w_settings.setCursor(QCursor(Qt.PointingHandCursor))
        self._w_settings.setToolTip("Ayarlar")
        self._w_settings.clicked.connect(self._open_settings)

        self._w_lock = QPushButton()
        self._w_lock.setFixedSize(18, 18)
        self._w_lock.setFlat(True)
        self._w_lock.setCursor(QCursor(Qt.PointingHandCursor))
        self._w_lock.clicked.connect(self._toggle_lock)
        self._update_lock_icon()

        self._w_close = QPushButton("✕")
        self._w_close.setFixedSize(18, 18)
        self._w_close.setFlat(True)
        self._w_close.setCursor(QCursor(Qt.PointingHandCursor))
        self._w_close.clicked.connect(self._kapat_kullanici)

        top.addWidget(self._w_title)
        top.addStretch()
        top.addWidget(self._w_settings)
        top.addWidget(self._w_lock)
        top.addWidget(self._w_close)

        self._w_cag = QLabel("")
        self._w_cag.setFont(QFont(fn, 7, QFont.Bold))

        self._w_yil = QLabel("")
        self._w_yil.setFont(QFont(fn, 11, QFont.Bold))

        self._w_olay = QLabel("")
        self._w_olay.setFont(QFont(fn, 9))
        self._w_olay.setWordWrap(True)
        self._w_olay.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._w_olay.setContextMenuPolicy(Qt.CustomContextMenu)
        self._w_olay.customContextMenuRequested.connect(self._olay_context_menu)


        bot = QHBoxLayout()
        self._w_timer = QLabel("")
        self._w_timer.setFont(QFont(fn, 8))
        self._w_goruldu = QLabel(f"👁 {self._dm.get('goruldu')}")
        self._w_goruldu.setFont(QFont(fn, 8))

        self._w_next = QPushButton("→ Sıradaki olay")
        self._w_next.setFlat(True)
        self._w_next.setFont(QFont(fn, 8))
        self._w_next.setCursor(QCursor(Qt.ArrowCursor))
        self._w_next.clicked.connect(lambda: None)

        bot.addWidget(self._w_timer)
        bot.addSpacing(6)
        bot.addWidget(self._w_goruldu)
        bot.addStretch()
        bot.addWidget(self._w_next)

        self._lay.addLayout(top)
        self._lay.addWidget(self._w_cag)
        self._lay.addWidget(self._w_yil)
        self._lay.addWidget(self._w_olay, 1)
        self._lay.addLayout(bot)

    def _show_welcome(self):
        geo = best_screen(self).availableGeometry()
        self._welcome_win = WelcomeWindow(self._dm, lambda: None)
        self._welcome_win.move(
            geo.center().x() - self._welcome_win.width() // 2,
            geo.center().y() - self._welcome_win.height() // 2,
        )
        self._welcome_win.show()

    def _kapat_kullanici(self):
        self._gizli_kullanici = True
        self.hide()

    def _update_lock_icon(self):
        icon = make_pin_icon(self._locked)
        self._w_lock.setIcon(icon)
        self._w_lock.setIconSize(self._w_lock.size())
        self._w_lock.setStyleSheet("border: none; background: transparent;")
        self._w_lock.setToolTip("Kilidi aç" if self._locked else "Konumu kilitle")

    def _olay_context_menu(self, pos):
        menu = QMenu(self)
        act = QAction("Olayı kopyala", self)
        act.triggered.connect(self._copy_olay)
        menu.addAction(act)
        menu.exec_(self._w_olay.mapToGlobal(pos))

    def _copy_olay(self):
        QApplication.clipboard().setText(f"{self._current_yil}: {self._current_olay}")

    def _get_c(self):
        return get_colors(self._current_yil, self._dm.get("arkaplan_modu"))

    def _apply_theme(self):
        c   = self._get_c()
        acc = c["acc"]
        fn  = FONTLAR.get(self._dm.get("font"), "Segoe UI")
        dim_style = f"color: {c['dim']}; font-size: 11px; border: none; background: transparent;"

        self._w_title.setStyleSheet(f"color: {acc};")
        self._w_title.setFont(QFont(fn, 9, QFont.Bold))
        self._w_cag.setStyleSheet(f"color: {c['dim']}; letter-spacing: 1px;")
        self._w_cag.setFont(QFont(fn, 7, QFont.Bold))
        self._w_yil.setStyleSheet(f"color: {acc};")
        self._w_yil.setFont(QFont(fn, 11, QFont.Bold))
        self._w_olay.setStyleSheet(f"color: {c['text']};")
        self._w_olay.setFont(QFont(fn, 9))
        self._w_timer.setStyleSheet(f"color: {c['dim']};")
        self._w_timer.setFont(QFont(fn, 8))
        self._w_goruldu.setStyleSheet(f"color: {c['dim']};")
        self._w_goruldu.setFont(QFont(fn, 8))
        self._w_settings.setStyleSheet(dim_style)
        self._w_close.setStyleSheet(dim_style)
        self._w_next.setStyleSheet(f"color: {c['dim']}; border: none; background: transparent;")
        self._w_next.setFont(QFont(fn, 8))
        self._update_lock_icon()
        self.setWindowOpacity(self._dm.get("opaklik") / 100.0)
        if hasattr(self, "_tray"):
            self._tray.setIcon(make_tray_icon(acc, c["bg"]))
        self.update()

    def _update_display(self, yil, olay):
        self._current_yil  = yil
        self._current_olay = olay
        c = self._get_c()
        self._w_cag.setText(c["ad"].upper())
        self._w_yil.setText(yil)
        self._w_olay.setText(olay)
        self._w_goruldu.setText(f"👁 {self._dm.get('goruldu')}")
        self._update_next_tooltip()

    def _update_next_tooltip(self):
        if self._deck:
            sonraki = self._deck[-1]["yil"]
            self._w_next.setToolTip(f"Sıradaki olay: {sonraki}")
            self._w_next.setText(f"→ {sonraki}")
        else:
            self._w_next.setToolTip("")
            self._w_next.setText("→")

    def _restore_or_next(self):
        idx          = self._dm.get("mevcut_olay_idx")
        kapanma_saat = self._dm.get("kapanma_saati")
        simdi_saat   = datetime.now().strftime("%Y-%m-%d %H")

        if kapanma_saat and kapanma_saat != simdi_saat:
            self._next_event()
            return

        if idx is not None and 0 <= idx < len(self._dm.events):
            event = self._dm.events[idx]
            self._current_idx = idx
            self._deck = [e for i, e in enumerate(self._dm.events) if i != idx]
            random.shuffle(self._deck)
            self._update_display(event["yil"], event["olay"])
            self._apply_theme()
        else:
            self._next_event()

    def _next_event(self, play_sound=False):
        if not self._deck:
            self._deck = list(self._dm.events)
            random.shuffle(self._deck)
        event = self._deck.pop()

        try:
            self._current_idx = self._dm.events.index(event)
        except ValueError:
            self._current_idx = None

        goruldu  = self._dm.get("goruldu") + 1
        autosave = (goruldu % GORULDU_SAVE == 0)
        self._dm.set("goruldu", goruldu, autosave=autosave)

        self._update_display(event["yil"], event["olay"])

        if goruldu % KUTLAMA_MOD == 0:
            if self._kutlama_aktif:
                self._kutlama_timer.stop()
                self._kutlama_aktif = False
            self._start_kutlama()
        else:
            self._apply_theme()

        if play_sound and self._dm.get("ses_acik"):
            cal_ses()

        if hasattr(self, "_settings_win") and self._settings_win.isVisible():
            if self._settings_win._current_tab == 2:
                self._settings_win._update_hakkinda()
            self._settings_win.refresh_theme()

    def _prev_event(self):
        if not self._dm.events:
            return
        if self._current_idx is not None:
            prev_idx = (self._current_idx - 1) % len(self._dm.events)
        else:
            prev_idx = len(self._dm.events) - 1
        event = self._dm.events[prev_idx]
        self._current_idx = prev_idx
        self._update_display(event["yil"], event["olay"])
        self._apply_theme()

    def _start_kutlama(self):
        self._kutlama_aktif = True
        self._kutlama_idx   = 0
        self._kutlama_timer.start(120)

    def _kutlama_tick(self):
        self._kutlama_idx += 1
        renk = KUTLAMA_RENKLER[self._kutlama_idx % len(KUTLAMA_RENKLER)]
        self._w_goruldu.setStyleSheet(f"color: {renk}; font-weight: bold;")
        if self._kutlama_idx >= 14:
            self._kutlama_timer.stop()
            self._kutlama_aktif = False
            self._apply_theme()

    def _init_timers(self):
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._on_tick)
        self._tick_timer.start(1000)

        self._kutlama_timer = QTimer(self)
        self._kutlama_timer.timeout.connect(self._kutlama_tick)

        # DEBUG: IPC devre dışı (yayın modu)
        # self._ipc_timer = QTimer(self)
        # self._ipc_timer.timeout.connect(self._check_ipc)
        # self._ipc_timer.start(500)

        self._desktop_timer = QTimer(self)
        self._desktop_timer.timeout.connect(self._desktop_check)
        self._desktop_timer.start(1000)

    def _desktop_check(self):
        """GWL_HWNDPARENT sayesinde masaüstüne gömülü — bu sadece HWND_BOTTOM'da tutar."""
        if self._gizli_kullanici:
            return
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.SetWindowPos(hwnd, 1, 0, 0, 0, 0, 0x0002|0x0001|0x0010)
        except Exception:
            pass

    def _on_tick(self):
        now  = datetime.now()
        hour = now.hour
        self._secs_left = 3600 - (now.minute * 60 + now.second)

        if hour != self._last_hour:
            self._last_hour = hour
            self._next_event(play_sound=True)
            return

        m, s = divmod(self._secs_left, 60)
        self._w_timer.setText(f"{m}:{s:02d}")

    def _check_ipc(self):
        if not os.path.exists(IPC_FILE):
            return
        try:
            with open(IPC_FILE) as f:
                cmd = f.read().strip()
            os.remove(IPC_FILE)
            self._handle_debug_cmd(cmd)
        except Exception:
            pass

    def _handle_debug_cmd(self, cmd):
        print(f"[DEBUG] Komut: {cmd}")
        if cmd == "next":
            self._next_event(play_sound=False)
        elif cmd == "prev":
            self._prev_event()
        elif cmd == "reset-deck":
            self._deck = list(self._dm.events)
            random.shuffle(self._deck)
            self._update_next_tooltip()
            print(f"[DEBUG] Deste karıştırıldı. {len(self._deck)} olay.")
        elif cmd == "reset-goruldu":
            self._dm.set("goruldu", 0)
            self._w_goruldu.setText("👁 0")
            print("[DEBUG] Görülen sayacı sıfırlandı.")
        elif cmd == "show":
            self._gizli_kullanici = False
            self.show()
            self.raise_()
        elif cmd == "hide":
            self._gizli_kullanici = True
            self.hide()
        elif cmd == "reload":
            self._dm.events = self._dm._load_events()
            self._deck = list(self._dm.events)
            random.shuffle(self._deck)
            self._current_idx = None
            self._update_next_tooltip()
            print(f"[DEBUG] Yeniden yüklendi. {len(self._dm.events)} olay.")
        elif cmd == "info":
            print(f"[DEBUG] {self._current_yil} — {self._current_olay[:50]}")
            print(f"[DEBUG] Destede: {len(self._deck)} | Görülen: {self._dm.get('goruldu')} | Saat: {self._secs_left}s")
        elif cmd == "status":
            pprint.pprint({
                "olay_yil":   self._current_yil,
                "olay":       self._current_olay[:60],
                "deck_kalan": len(self._deck),
                "goruldu":    self._dm.get("goruldu"),
                "saat_basi":  self._secs_left,
                "kilitli":    self._locked,
                "gorunum":    self.isVisible(),
                "font":       self._dm.get("font"),
                "tema":       self._dm.get("arkaplan_modu"),
            })
        elif cmd == "deck-size":
            print(f"[DEBUG] Destede {len(self._deck)} olay.")
        elif cmd == "log":
            print("[DEBUG] Log henüz aktif değil.")
        elif cmd == "kutlama":
            self._start_kutlama()
        elif cmd == "force-update":
            guncelle_olaylar(on_done=self._on_events_updated, force=True)
            print("[DEBUG] Zorla güncelleme başlatıldı.")
        elif cmd == "settings":
            self._open_settings()
        elif cmd == "crash":
            raise RuntimeError("[DEBUG] Kasıtlı hata.")
        elif cmd.startswith("opacity:"):
            try:
                val = max(20, min(100, int(cmd.split(":")[1])))
                self._dm.set("opaklik", val)
                self.setWindowOpacity(val / 100.0)
                print(f"[DEBUG] Opaklık: %{val}")
            except Exception as e:
                print(f"[DEBUG] Hata: {e}")
        elif cmd.startswith("theme:"):
            theme = cmd.split(":")[1]
            if theme in {"cag", "acik", "koyu"}:
                self._dm.set("arkaplan_modu", theme)
                self._apply_theme()
        elif cmd.startswith("font:"):
            font = cmd.split(":")[1]
            if font in FONTLAR:
                self._dm.set("font", font)
                self._on_settings_changed("font")
        else:
            print(f"[DEBUG] Bilinmeyen: {cmd}")

    def _on_guncelleme_var(self, yeni_versiyon):
        """Yeni sürüm varsa kullanıcıya sorar."""
        cevap = QMessageBox.question(
            None,
            "Güncelleme Mevcut",
            f"Tarih Köşesi {yeni_versiyon} surumu mevcut! Su an {APP_VERSION} kullaniyorsunuz. Guncellemek ister misiniz?",
            QMessageBox.Yes | QMessageBox.No
        )
        if cevap == QMessageBox.Yes:
            exe_yolu = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)
            guncelleme_baslat(exe_yolu)

    def _on_events_updated(self, new_events):
        self._dm.events = new_events
        self._deck = list(new_events)
        random.shuffle(self._deck)
        self._current_idx = None
        self._update_next_tooltip()

    def _init_tray(self):
        c = self._get_c()
        self._tray = QSystemTrayIcon(make_tray_icon(c["acc"], c["bg"]), self)
        self._tray.setToolTip("Tarih Köşesi")
        menu = QMenu()
        for label, slot in [
            ("Göster / Gizle", self._toggle_visible),
            (None, None),
            ("≡  Ayarlar",     self._open_settings),
            (None, None),
            ("Çıkış",          self._quit),
        ]:
            if label is None:
                menu.addSeparator()
            else:
                a = QAction(label, self)
                a.triggered.connect(slot)
                menu.addAction(a)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(
            lambda r: self._toggle_visible() if r == QSystemTrayIcon.Trigger else None
        )
        self._tray.show()

    def _quit(self):
        cevap = QMessageBox.question(
            None, "Çıkış",
            "Tarih Köşesi'nden çıkmak istediğinize emin misiniz?",
            QMessageBox.Yes | QMessageBox.No
        )
        if cevap == QMessageBox.Yes:
            self._dm.set("mevcut_olay_idx", self._current_idx, autosave=False)
            self._dm.set("kapanma_saati", datetime.now().strftime("%Y-%m-%d %H"), autosave=False)
            self._dm.save()
            remove_lock()
            QApplication.quit()

    def _toggle_visible(self):
        if self.isVisible():
            self._gizli_kullanici = True
            self.hide()
        else:
            self._gizli_kullanici = False
            self.show()
            self._pin_yapildi = False
            QTimer.singleShot(150, self._pin_to_desktop)

    def _open_settings(self):
        self._settings_win.open_for(self)

    def _on_settings_changed(self, changed_key):
        if changed_key == "font":
            fn = FONTLAR.get(self._dm.get("font"), "Segoe UI")
            for w, size, bold in [
                (self._w_title, 9, True), (self._w_cag, 7, True),
                (self._w_yil, 11, True), (self._w_olay, 9, False),
                (self._w_timer, 8, False), (self._w_goruldu, 8, False),
                (self._w_next, 8, False),
            ]:
                w.setFont(QFont(fn, size, QFont.Bold if bold else QFont.Normal))
        elif changed_key == "opaklik":
            self.setWindowOpacity(self._dm.get("opaklik") / 100.0)
            return
        elif changed_key == "serit_goster":
            serit = self._dm.get("serit_goster")
            self._lay.setContentsMargins(
                (SERIT_W + 14) if serit else 14, 12, 14, 10
            )
        elif changed_key == "reset":
            fn    = FONTLAR.get(self._dm.get("font"), "Segoe UI")
            serit = self._dm.get("serit_goster")
            self._lay.setContentsMargins(
                (SERIT_W + 14) if serit else 14, 12, 14, 10
            )
            for w, size, bold in [
                (self._w_title, 9, True), (self._w_cag, 7, True),
                (self._w_yil, 11, True), (self._w_olay, 9, False),
                (self._w_timer, 8, False), (self._w_goruldu, 8, False),
                (self._w_next, 8, False),
            ]:
                w.setFont(QFont(fn, size, QFont.Bold if bold else QFont.Normal))
        self._apply_theme()
        self._settings_win.refresh_theme()

    def _toggle_lock(self):
        self._locked = not self._locked
        self._dm.set("kilitli", self._locked)
        self._update_lock_icon()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c    = self._get_c()
        r, g, b = c["bg"]
        acc  = c["acc"]
        kose = self._dm.get("kose")
        w, h = self.width(), self.height()
        p.fillPath(kose_path(kose, w, h), QColor(r, g, b))
        if self._dm.get("serit_goster"):
            serit = QPainterPath()
            if kose == "yuvarlak":
                serit.addRoundedRect(0, 0, SERIT_W, h, 3, 3)
            else:
                serit.addRect(0, 0, SERIT_W, h)
            p.fillPath(serit, QColor(acc))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and not self._locked:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if not (e.buttons() == Qt.LeftButton and self._drag_pos and not self._locked):
            return
        new_pos = e.globalPos() - self._drag_pos
        geo = best_screen(self).availableGeometry()
        x = max(geo.left(), min(new_pos.x(), geo.right()  - WIDGET_W))
        y = max(geo.top(),  min(new_pos.y(), geo.bottom() - WIDGET_H))
        self.move(x, y)

    def mouseReleaseEvent(self, _):
        if self._drag_pos:
            self._dm.set("pos_x", self.x())
            self._dm.set("pos_y", self.y())
        self._drag_pos = None

    def closeEvent(self, e):
        e.ignore()
        self._gizli_kullanici = True
        self.hide()


# ── Giriş ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Önceki güncelleme kalıntılarını temizle
    try:
        if getattr(sys, "frozen", False):
            bak = sys.executable + ".bak"
            if os.path.exists(bak):
                os.remove(bak)
    except Exception:
        pass

    if not check_single_instance():
        QMessageBox.information(None, "Tarih Köşesi",
            "Tarih Köşesi zaten çalışıyor!\nSistem tepsisine bakın.")
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    dm = DataManager()
    w  = HistoryWidget(dm)

    guncelle_olaylar(on_done=w._on_events_updated)
    guncelleme_kontrol(w)

    if dm.get("baslangic_goster"):
        w.show()

    ret = app.exec_()
    remove_lock()
    sys.exit(ret)
