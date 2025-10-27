import os
import sys
import threading
import subprocess
from pathlib import Path

import json
import zipfile
import webbrowser
import requests
import logging

import customtkinter as ctk
from tkinter import filedialog, messagebox, TclError
from PIL import Image, ImageTk

# ===== Config =====
APP_TITLE = "Open Games Launcher"
GAMES_DIR  = Path("games")
APP_ICON   = "assets/icon.ico"  # 64x64

# ===== Logging =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ===== HTTP session (fewer 403s + faster) =====
_HTTP = requests.Session()
_HTTP.headers.update({
    "User-Agent": "OpenGamesLauncher/1.0 (+local)",
    "Accept": "*/*",
})

# ===== Helpers =====
def _safe_mb(kind: str, title: str, text: str) -> None:
    """Messagebox that won't crash if Tk isn't ready yet."""
    try:
        if kind == "error":
            messagebox.showerror(title, text)
        elif kind == "warning":
            messagebox.showwarning(title, text)
        else:
            messagebox.showinfo(title, text)
    except TclError:
        logging.error("[MsgBox skipped] %s: %s", title, text)

def _is_windows_shortcut(p: Path) -> bool:
    return p.suffix.lower() in {".lnk", ".url", ".bat", ".cmd"}

def _safe_extract_zip(zf: zipfile.ZipFile, dest_dir: Path) -> None:
    """Prevent Zip-Slip; ensure paths stay within dest_dir."""
    base = dest_dir.resolve()
    for info in zf.infolist():
        rel = Path(info.filename)
        if rel.is_absolute():
            raise Exception(f"Unsafe absolute path in zip: {info.filename}")
        out = (base / rel).resolve()
        if not str(out).startswith(str(base)):
            raise Exception(f"Unsafe path traversal in zip: {info.filename}")
        if info.is_dir():
            out.mkdir(parents=True, exist_ok=True)
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(out, "wb") as dst:
                dst.write(src.read())

# ===== Data IO =====
SCHEMA_DEFAULT = {
    "id": "sample",
    "name": "Sample Game",
    "game_path": str(Path.cwd() / "SampleGame.exe"),
    "work_dir": str(Path.cwd()),
    "args": [],
    "news_url": "https://raw.githubusercontent.com/github/markup/master/README.md",
    "icon": "assets/empty_icon.png",
    "cover": "assets/empty_background.jpg",
    "update": {
        "url": "",
        "dest": str(Path.cwd() / "sample_update.zip"),
        "extract_to": str(Path.cwd())
    }
}

def _read_game_file(p: Path) -> dict:
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if "id" not in data:
            data["id"] = p.stem
        data.setdefault("name", data["id"])
        if not data.get("work_dir"):
            gp = Path(data.get("game_path", "")) if data.get("game_path") else None
            data["work_dir"] = str(gp.parent if gp and gp.exists() else Path.cwd())
        data["meta_path"] = str(p)
        return data
    except Exception as e:
        logging.warning(f"Skipping bad game file {p.name}: {e}")
        return {}

def _write_game_file(game: dict) -> Path:
    gid = (game.get("id") or game.get("name") or "game").lower().replace(" ", "_")
    p = Path(game.get("meta_path") or (GAMES_DIR / f"{gid}.json"))
    p.parent.mkdir(parents=True, exist_ok=True)
    to_save = {k: v for k, v in game.items() if k != "meta_path"}
    p.write_text(json.dumps(to_save, indent=2), encoding="utf-8")
    game["meta_path"] = str(p)
    return p

def load_games() -> list[dict]:
    GAMES_DIR.mkdir(exist_ok=True)
    games = []
    for p in sorted(GAMES_DIR.glob("*.json")):
        g = _read_game_file(p)
        if g:
            games.append(g)
    if not games:
        # seed one sample file
        sample = dict(SCHEMA_DEFAULT)
        sample["id"] = "sample"
        sample["name"] = "Sample Game"
        _write_game_file(sample)
        games.append(sample)
    return games

def save_games(games: list[dict]) -> None:
    for g in games:
        try:
            _write_game_file(g)
        except Exception as e:
            logging.error(f"Save failed for {g.get('id','(no id)')}: {e}")

# ===== Launching =====
def launch_game(game_path, work_dir=None, args=None):
    args = args or []
    try:
        if game_path.startswith(("http://", "https://", "steam://", "epic://")):
            webbrowser.open(game_path)
            return True, "Opened URL/protocol"

        p = Path(game_path)
        if os.name == "nt" and _is_windows_shortcut(p) and not args:
            # Let Explorer resolve shortcuts / .bat / .cmd
            os.startfile(str(p))  # type: ignore[attr-defined]
            return True, "Launched via Shell"

        cwd = work_dir or p.parent
        cmd = [str(p), *args]
        subprocess.Popen(cmd, cwd=str(cwd))
        return True, "Launched"
    except Exception as e:
        return False, str(e)

# ===== Networking =====
def fetch_news(url):
    r = _HTTP.get(url, timeout=20)
    r.raise_for_status()
    return r.text

def download_update(url, dest, extract_to, progress_cb=None, status_cb=None):
    with _HTTP.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", "0") or 0)
        downloaded = 0
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                if total and progress_cb:
                    progress_cb(downloaded / total)
    if dest.lower().endswith(".zip") and extract_to:
        if status_cb:
            status_cb("Extracting…")
        with zipfile.ZipFile(dest, "r") as zf:
            _safe_extract_zip(zf, Path(extract_to))

# ===== Images =====
def load_ctk_image(path: str | None, size: tuple[int, int] | None = None):
    try:
        if not path:
            return None
        img = Image.open(path)
        if size:
            img = img.copy().resize(size, Image.LANCZOS)
        return ctk.CTkImage(light_image=img, dark_image=img, size=size if size else img.size)
    except Exception:
        return None

# ===== Special UI =====
class HoverButton(ctk.CTkButton):
    def __init__(self, master=None, **kwargs):
        # base colors
        self.normal_fg_color = kwargs.pop("fg_color", "#111418")
        self.normal_text_color = kwargs.pop("text_color", "#E8EEF3")
        # hover colors
        self.hover_fg_color = kwargs.pop("hover_fg_color", "#F6C90E")
        self.hover_text_color = kwargs.pop("hover_text_color", "#111418")

        super().__init__(
            master,
            fg_color=self.normal_fg_color,
            text_color=self.normal_text_color,
            **kwargs
        )
        # NOTE: no manual .bind() — we override CTkButton’s own hooks below

    def _on_enter(self, event=None):
        # keep CTk’s built-in behavior (cursor/relief etc.)
        super()._on_enter(event)
        self.configure(fg_color=self.hover_fg_color, text_color=self.hover_text_color)

    def _on_leave(self, event=None):
        # keep CTk’s built-in behavior
        super().__init__  # just to aid linters; no-op at runtime
        super()._on_leave(event)
        self.configure(fg_color=self.normal_fg_color, text_color=self.normal_text_color)

# ===== UI =====
class Launcher(ctk.CTk):
    def __init__(self, games):
        super().__init__()
        # window icon
        try:
            if os.name == "nt" and APP_ICON.lower().endswith(".ico"):
                self.iconbitmap(APP_ICON)
            else:
                img = Image.open(APP_ICON)
                self.iconphoto(True, ImageTk.PhotoImage(img))
        except Exception:
            pass

        self.title(APP_TITLE)
        self.geometry("1060x640")
        self.minsize(900, 560)
        self.games = games
        self.selected = 0

        # GRID: 1 (left) : 4 (right)
        self.grid_columnconfigure(0, weight=1, minsize=220)
        self.grid_columnconfigure(1, weight=4)
        self.grid_rowconfigure(0, weight=1)

        # Left panel
        self.left = ctk.CTkFrame(self)
        self.left.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.left.grid_rowconfigure(2, weight=1)

        header_left = ctk.CTkFrame(self.left)
        header_left.grid(row=0, column=0, sticky="ew", padx=6, pady=(6,4))
        ctk.CTkLabel(header_left, text=" Games", font=("Segoe UI", 13, "bold")).pack(side="left")

        btns = ctk.CTkFrame(header_left)
        btns.pack(side="right")
        HoverButton(btns, text="+", width=36, command=self.quick_add_game).pack(side="left", padx=2)
        HoverButton(btns, text="📂", width=36, command=self.open_folder).pack(side="left", padx=2)
        HoverButton(btns, text="🛠", width=36, command=self.edit_json).pack(side="left", padx=2)

        # Scrollable game list
        self.list_frame = ctk.CTkScrollableFrame(self.left, width=200)
        self.list_frame.grid(row=2, column=0, sticky="nsew", padx=6, pady=(4,6))
        self.buttons = []
        self.icon_cache = {}

        # Right panel
        self.right = ctk.CTkFrame(self)
        self.right.grid(row=0, column=1, sticky="nsew", padx=(0,8), pady=8)
        self.right.grid_columnconfigure(0, weight=1)
        self.right.grid_rowconfigure(2, weight=1)

        self.cover_label = ctk.CTkLabel(self.right, text="")
        self.cover_label.grid(row=0, column=0, sticky="ew", padx=8, pady=(8,4))

        self.news = ctk.CTkTextbox(self.right)
        self.news.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0,8))
        self._set_news("Loading news…")

        self.prog = ctk.CTkProgressBar(self.right)
        self.prog.set(0.0)
        self.prog.grid(row=3, column=0, sticky="ew", padx=8, pady=(0,6))

        controls = ctk.CTkFrame(self.right)
        controls.grid(row=4, column=0, sticky="ew", padx=8, pady=(0,8))

        self.status_lbl = ctk.CTkLabel(controls, text="")
        self.status_lbl.pack(side="left")

        HoverButton(controls, text="Play ▶",   command=self.play).pack(side="right", padx=4)
        HoverButton(controls, text="Update ⟳", command=self.download).pack(side="right", padx=4)

        self.refresh_game_list(select_index=0)
        if self.games:
            self.load_news()

    # ==== List maintenance ====
    def refresh_game_list(self, select_index=None):
        for b in self.buttons:
            b.destroy()
        self.buttons.clear()
        self.icon_cache.clear()
        for i, g in enumerate(self.games):
            icon_img = load_ctk_image(g.get("icon"), size=(20,20))
            self.icon_cache[i] = icon_img
            btn = ctk.CTkButton(
                self.list_frame,
                text=g.get("name", g.get("id", "unknown")),
                image=icon_img, compound="left", anchor="w",
                command=lambda i=i: self.on_select(i)
            )
            btn.pack(fill="x", padx=2, pady=2)
            self.buttons.append(btn)
        if self.games:
            idx = select_index if select_index is not None else min(self.selected, len(self.games)-1)
            self.on_select(idx)

    def on_select(self, idx: int):
        self.selected = idx
        for i, b in enumerate(self.buttons):
            b.configure(fg_color=("#F6C90E" if i == idx else "#111418"),
                        text_color=("#111418" if i == idx else "#E8EEF3"))
        g = self.games[idx]
        self._set_cover(g.get("cover"))
        self.set_status(f"Selected: {g.get('name')}")
        self.load_news()

    # ==== UI helpers ====
    def set_status(self, txt: str):
        self.status_lbl.configure(text=txt)

    def _set_cover(self, path: str | None):
        img = load_ctk_image(path, size=(820, 180))
        self.cover_img = img
        if img:
            self.cover_label.configure(image=img, text="")
        else:
            self.cover_label.configure(image=None, text="")

    def _set_news(self, txt: str):
        self.news.configure(state="normal")
        self.news.delete("1.0", "end")
        self.news.insert("1.0", txt)
        self.news.configure(state="disabled")

    # ==== Actions ====
    def current(self):
        if self.games:
            return self.selected, self.games[self.selected]
        return 0, None

    def play(self):
        _, g = self.current()
        if not g:
            return
        exe = g.get("game_path")
        if not exe or (not exe.startswith(("http", "steam://", "epic://")) and not Path(exe).exists()):
            _safe_mb("warning", "Missing", "game_path not found. Use + to add or edit JSON.")
            return
        ok, msg = launch_game(exe, g.get("work_dir"), g.get("args"))
        self.set_status(("OK" if ok else "FAIL") + f" — {msg}")

    def load_news(self):
        _, g = self.current()
        if not g:
            return
        url = g.get("news_url")
        if not url:
            self.set_status("No news URL.")
            return
        self.set_status("Fetching news…")
        self.prog.set(0.0)

        def job():
            try:
                text = fetch_news(url)[:20000]
                self.after(0, self._news_loaded, text)
            except Exception as e:
                self.after(0, (lambda e=e: self.set_status(f"News fetch failed: {e}")))
        threading.Thread(target=job, daemon=True).start()

    def _news_loaded(self, text: str):
        self._set_news(text)
        self.set_status("News loaded.")

    def download(self):
        _, g = self.current()
        if not g:
            return
        up = g.get("update") or {}
        url, dest, extract_to = up.get("url"), up.get("dest"), up.get("extract_to")
        if not url or not dest:
            _safe_mb("info", "Update", "Update block missing 'url' or 'dest'.")
            return
        self.prog.set(0.0)
        self.set_status("Downloading…")

        def job():
            try:
                def prog(p): self.after(0, lambda p=p: self.prog.set(float(p)))
                def stat(s): self.after(0, lambda s=s: self.set_status(s))
                download_update(url, dest, extract_to, prog, stat)
                self.after(0, lambda: self.set_status(f"Saved to {dest}"))
            except Exception as e:
                self.after(0, (lambda e=e: self.set_status(f"Download failed: {e}")))
        threading.Thread(target=job, daemon=True).start()

    def quick_add_game(self):
        path = filedialog.askopenfilename(title="Select game executable")
        if not path:
            return
        p = Path(path)
        base_id = p.stem.lower().replace(" ", "_")
        gid = base_id
        # avoid overwrite if file exists
        n = 1
        while (GAMES_DIR / f"{gid}.json").exists():
            gid = f"{base_id}_{n}"
            n += 1

        new = {
            "id": gid,
            "name": p.stem,
            "game_path": str(p),
            "work_dir": str(p.parent),
            "args": [],
            "news_url": "",
            "icon": "assets/empty_icon.png",
            "cover": "assets/empty_background.jpg",
            "update": { "url": "", "dest": "", "extract_to": str(p.parent) }
        }
        _write_game_file(new)           # write per-game file
        self.games.append(new)
        self.set_status(f"Added {new['name']}")
        self.refresh_game_list(select_index=len(self.games)-1)

    def open_folder(self):
        _, g = self.current()
        if not g:
            return
        folder = g.get("work_dir") or (Path(g.get("game_path", "")).parent if g.get("game_path") else Path.cwd())
        try:
            if os.name == "nt":
                os.startfile(str(folder))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception:
            _safe_mb("info", "Folder", str(folder))

    def edit_json(self):
        _, g = self.current()
        target: Path
        if g and g.get("meta_path") and Path(g["meta_path"]).exists():
            target = Path(g["meta_path"])
        else:
            target = GAMES_DIR  # open the folder if no file
        try:
            if target.is_dir():
                if os.name == "nt":
                    os.startfile(str(target))  # type: ignore[attr-defined]
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(target)])
                else:
                    subprocess.Popen(["xdg-open", str(target)])
            else:
                if os.name == "nt":
                    os.startfile(str(target))  # type: ignore[attr-defined]
                else:
                    webbrowser.open(target.as_uri())
        except Exception as e:
            _safe_mb("info", "JSON", f"{target}\n{e}")

# ===== Entry =====
def main():
    ctk.set_appearance_mode("System")  # Modes: "System" (standard), "Dark", "Light"
    ctk.set_default_color_theme("themes/metal.json")
    app = Launcher(load_games())
    icopath = ImageTk.PhotoImage(file=APP_ICON)
    app.iconphoto(False, icopath)
    app.mainloop()

if __name__ == "__main__":
    main()
