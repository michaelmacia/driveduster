#!/usr/bin/env python3
"""DriveDuster - Directory size analyzer (Windows desktop app)."""

import os
import string
import subprocess
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tkinter import messagebox, ttk


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_dir_size(path: Path) -> int:
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += get_dir_size(Path(entry.path))
            except (PermissionError, OSError):
                pass
    except (PermissionError, OSError):
        pass
    return total


def format_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def available_drives() -> list[str]:
    return [f"{l}:\\" for l in string.ascii_uppercase if os.path.exists(f"{l}:\\")]


def make_bar(pct: float, width: int = 24) -> str:
    filled = int(width * pct / 100)
    return "█" * filled + "░" * (width - filled)


def size_tag(size: int) -> str:
    gb = size / (1024 ** 3)
    if gb >= 10:  return "huge"
    if gb >= 1:   return "large"
    if gb >= 0.1: return "medium"
    return "small"


# ── App ───────────────────────────────────────────────────────────────────────

class DriveDusterApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("DriveDuster")
        self.root.geometry("1000x620")
        self.root.minsize(640, 420)

        self.current_path = Path("C:\\")
        self.history: list[Path] = []
        self.scan_results: list[tuple[Path, int]] = []
        self._scanning = False
        self._cancel = False
        self._sort_col = "size"
        self._sort_desc = True

        self._build_ui()
        self._apply_style()
        self.navigate_to(self.current_path, add_history=False)

    # ── UI construction ───────────────────────────────────────────────────────

    def _apply_style(self):
        s = ttk.Style()
        try:
            s.theme_use("vista")
        except tk.TclError:
            s.theme_use("clam")

        s.configure("Treeview", rowheight=26, font=("Segoe UI", 10))
        s.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        s.configure("Status.TLabel", font=("Segoe UI", 9), foreground="#555555")
        s.configure("Path.TEntry", font=("Segoe UI", 10))

    def _build_ui(self):
        # ── Toolbar ───────────────────────────────────────────────
        bar = ttk.Frame(self.root, padding=(6, 5, 6, 5))
        bar.pack(fill="x")

        ttk.Label(bar, text="Drive:").pack(side="left", padx=(0, 3))
        self.drive_var = tk.StringVar()
        drives = available_drives()
        self.drive_combo = ttk.Combobox(
            bar, textvariable=self.drive_var,
            values=drives, width=7, state="readonly",
        )
        self.drive_combo.pack(side="left", padx=(0, 6))
        if drives:
            self.drive_var.set(drives[0])
        self.drive_combo.bind("<<ComboboxSelected>>", self._on_drive_change)

        self.btn_back = ttk.Button(bar, text="◀", width=3, command=self._go_back)
        self.btn_back.pack(side="left", padx=(0, 2))
        self.btn_back.state(["disabled"])

        self.btn_up = ttk.Button(bar, text="▲", width=3, command=self._go_up)
        self.btn_up.pack(side="left", padx=(0, 8))

        self.path_var = tk.StringVar()
        path_entry = ttk.Entry(bar, textvariable=self.path_var)
        path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        path_entry.bind("<Return>", self._on_path_enter)

        self.btn_scan = ttk.Button(bar, text="⟳ Scan", width=8, command=self._rescan)
        self.btn_scan.pack(side="left")

        # ── Treeview ──────────────────────────────────────────────
        body = ttk.Frame(self.root, padding=(6, 0, 6, 0))
        body.pack(fill="both", expand=True)

        cols = ("size", "pct", "bar")
        self.tree = ttk.Treeview(body, columns=cols, selectmode="browse")

        self.tree.heading("#0",    text=" Directory",  anchor="w",
                          command=lambda: self._sort("name"))
        self.tree.heading("size",  text="Size",        anchor="e",
                          command=lambda: self._sort("size"))
        self.tree.heading("pct",   text="% of total",  anchor="e",
                          command=lambda: self._sort("pct"))
        self.tree.heading("bar",   text="Usage",       anchor="w")

        self.tree.column("#0",   stretch=True, minwidth=220)
        self.tree.column("size", width=100, anchor="e", stretch=False)
        self.tree.column("pct",  width=90,  anchor="e", stretch=False)
        self.tree.column("bar",  width=210, anchor="w", stretch=False)

        self.tree.tag_configure("huge",   foreground="#c0392b")
        self.tree.tag_configure("large",  foreground="#e67e22")
        self.tree.tag_configure("medium", foreground="#27ae60")
        self.tree.tag_configure("small",  foreground="#888888")

        vsb = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.bind("<Double-1>",    self._on_double_click)
        self.tree.bind("<Return>",      self._on_double_click)
        self.tree.bind("<Button-3>",    self._on_right_click)
        self.tree.bind("<BackSpace>",   lambda _: self._go_back())

        # ── Context menu ──────────────────────────────────────────
        self.ctx = tk.Menu(self.root, tearoff=0)
        self.ctx.add_command(label="Open in Explorer",  command=self._open_explorer)
        self.ctx.add_command(label="Drill into folder", command=self._drill_selected)
        self.ctx.add_separator()
        self.ctx.add_command(label="Copy path",         command=self._copy_path)

        # ── Status bar ────────────────────────────────────────────
        sf = ttk.Frame(self.root, padding=(6, 2, 6, 4))
        sf.pack(fill="x", side="bottom")

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(sf, textvariable=self.status_var, style="Status.TLabel").pack(side="left")

        self.progress = ttk.Progressbar(sf, mode="indeterminate", length=130)
        self.progress.pack(side="right")

    # ── Navigation ────────────────────────────────────────────────────────────

    def navigate_to(self, path: Path, add_history: bool = True):
        if add_history and path != self.current_path:
            self.history.append(self.current_path)
        self.current_path = path
        self.path_var.set(str(path))
        self.btn_back.state(["!disabled"] if self.history else ["disabled"])
        self._start_scan()

    def _go_back(self):
        if self.history:
            self.navigate_to(self.history.pop(), add_history=False)
            self.btn_back.state(["!disabled"] if self.history else ["disabled"])

    def _go_up(self):
        parent = self.current_path.parent
        if parent != self.current_path:
            self.navigate_to(parent)

    def _rescan(self):
        self.navigate_to(self.current_path, add_history=False)

    def _on_drive_change(self, _=None):
        drive = self.drive_var.get()
        if drive:
            self.navigate_to(Path(drive))

    def _on_path_enter(self, _=None):
        p = Path(self.path_var.get().strip())
        if p.is_dir():
            self.navigate_to(p)
        else:
            messagebox.showerror("Invalid path", f"Directory not found:\n{p}")

    # ── Scanning ──────────────────────────────────────────────────────────────

    def _start_scan(self):
        if self._scanning:
            self._cancel = True
        self._scanning = True
        self._cancel = False
        self._clear_tree()
        self.btn_scan.state(["disabled"])
        self.status_var.set(f"Scanning {self.current_path} …")
        self.progress.start(8)
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        path = self.current_path
        results: list[tuple[Path, int]] = []

        try:
            entries = [e for e in os.scandir(path) if e.is_dir(follow_symlinks=False)]
        except (PermissionError, OSError):
            entries = []

        with ThreadPoolExecutor(max_workers=16) as ex:
            futures = {ex.submit(get_dir_size, Path(e.path)): e for e in entries}
            for future in as_completed(futures):
                if self._cancel:
                    return
                entry = futures[future]
                try:
                    size = future.result()
                    results.append((Path(entry.path), size))
                    self.root.after(0, self.status_var.set, f"Scanning … {entry.name}")
                except Exception:
                    pass

        results.sort(key=lambda x: x[1], reverse=True)
        self.root.after(0, self._on_scan_done, results)

    def _on_scan_done(self, results: list[tuple[Path, int]]):
        self._scanning = False
        self.progress.stop()
        self.btn_scan.state(["!disabled"])
        self.scan_results = results
        self._populate_tree()

    def _populate_tree(self):
        self._clear_tree()
        results = self.scan_results
        total = sum(s for _, s in results)

        for p, size in results:
            pct = size / total * 100 if total else 0
            self.tree.insert(
                "", "end",
                iid=str(p),
                text=f"  {p.name}",
                values=(format_size(size), f"{pct:.1f}%", f"  {make_bar(pct)}"),
                tags=(size_tag(size),),
            )

        n = len(results)
        self.status_var.set(
            f"{n} director{'y' if n == 1 else 'ies'}  —  Total: {format_size(total)}"
        )

    def _clear_tree(self):
        self.tree.delete(*self.tree.get_children())

    # ── Sorting ───────────────────────────────────────────────────────────────

    def _sort(self, col: str):
        if self._sort_col == col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col = col
            self._sort_desc = True

        lookup = {str(p): s for p, s in self.scan_results}

        if col in ("size", "pct"):
            key = lambda iid: lookup.get(iid, 0)
        else:
            key = lambda iid: Path(iid).name.lower()

        items = sorted(self.tree.get_children(), key=key, reverse=self._sort_desc)
        for i, iid in enumerate(items):
            self.tree.move(iid, "", i)

    # ── Tree events ───────────────────────────────────────────────────────────

    def _selected_path(self) -> Path | None:
        sel = self.tree.selection()
        return Path(sel[0]) if sel else None

    def _drill_selected(self):
        p = self._selected_path()
        if p and p.is_dir():
            self.navigate_to(p)

    def _on_double_click(self, _=None):
        self._drill_selected()

    def _on_right_click(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self.ctx.post(event.x_root, event.y_root)

    def _open_explorer(self):
        p = self._selected_path()
        if p:
            subprocess.Popen(["explorer", str(p)])

    def _copy_path(self):
        p = self._selected_path()
        if p:
            self.root.clipboard_clear()
            self.root.clipboard_append(str(p))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    DriveDusterApp().run()
