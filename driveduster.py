#!/usr/bin/env python3
"""DriveDuster - Directory size analyzer (Windows desktop app)."""

import os
import shutil
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


def scan_children(path: Path) -> list[tuple[Path, int]]:
    """Return immediate subdirectories with recursive sizes, sorted largest first."""
    results = []
    try:
        entries = [e for e in os.scandir(path) if e.is_dir(follow_symlinks=False)]
    except (PermissionError, OSError):
        return []

    with ThreadPoolExecutor(max_workers=16) as ex:
        futures = {ex.submit(get_dir_size, Path(e.path)): e for e in entries}
        for future in as_completed(futures):
            try:
                results.append((Path(futures[future].path), future.result()))
            except Exception:
                pass

    results.sort(key=lambda x: x[1], reverse=True)
    return results


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


def find_uninstaller(path: Path) -> Path | None:
    """Return the first uninstaller executable found directly inside path, or None."""
    patterns = ["unins*.exe", "uninstall*.exe", "uninst*.exe", "*uninstall*.exe"]
    for pattern in patterns:
        for match in path.glob(pattern):
            if match.is_file():
                return match
    return None


# ── App ───────────────────────────────────────────────────────────────────────

class DriveDusterApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("DriveDuster")
        self.root.geometry("1000x640")
        self.root.minsize(640, 420)

        self.current_path = Path("C:\\")
        self._root_gen = 0
        self._expanding: set[str] = set()

        # iid is always a plain integer string ("1", "2", ...) to avoid
        # Tcl misinterpreting backslashes or special chars in Windows paths.
        self._iid_seq = 0
        self._nodes: dict[str, Path] = {}   # iid  -> Path  (dummy iids absent)

        self._build_ui()
        self._apply_style()
        self._rescan()

    def _next_iid(self) -> str:
        self._iid_seq += 1
        return str(self._iid_seq)

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

        self.path_var = tk.StringVar(value=str(self.current_path))
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

        self.tree.heading("#0",   text=" Directory",  anchor="w")
        self.tree.heading("size", text="Size",        anchor="e")
        self.tree.heading("pct",  text="% of parent", anchor="e")
        self.tree.heading("bar",  text="Usage",       anchor="w")

        self.tree.column("#0",   stretch=True, minwidth=220)
        self.tree.column("size", width=100, anchor="e", stretch=False)
        self.tree.column("pct",  width=100, anchor="e", stretch=False)
        self.tree.column("bar",  width=210, anchor="w", stretch=False)

        self.tree.tag_configure("huge",   foreground="#c0392b")
        self.tree.tag_configure("large",  foreground="#e67e22")
        self.tree.tag_configure("medium", foreground="#27ae60")
        self.tree.tag_configure("small",  foreground="#888888")
        self.tree.tag_configure("dummy",  foreground="#aaaaaa")

        vsb = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.bind("<<TreeviewOpen>>", self._on_expand)
        self.tree.bind("<Button-3>",       self._on_right_click)

        # ── Context menu ──────────────────────────────────────────
        self.ctx = tk.Menu(self.root, tearoff=0)
        self.ctx.add_command(label="Open in Explorer",      command=self._open_explorer)
        self.ctx.add_command(label="Copy path",             command=self._copy_path)
        self.ctx.add_separator()
        self.ctx.add_command(label="Uninstall application", command=self._uninstall_selected)
        self.ctx.add_command(label="Delete folder…",        command=self._delete_selected)

        # ── Status bar ────────────────────────────────────────────
        sf = ttk.Frame(self.root, padding=(6, 2, 6, 4))
        sf.pack(fill="x", side="bottom")

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(sf, textvariable=self.status_var, style="Status.TLabel").pack(side="left")

        self.progress = ttk.Progressbar(sf, mode="indeterminate", length=130)
        self.progress.pack(side="right")

    # ── Root scan ─────────────────────────────────────────────────────────────

    def _rescan(self):
        self._root_gen += 1
        gen = self._root_gen
        self._nodes.clear()
        self._expanding.clear()
        self._clear_tree()
        self.btn_scan.state(["disabled"])
        self.status_var.set(f"Scanning {self.current_path} …")
        self.progress.start(8)
        threading.Thread(
            target=self._root_worker, args=(self.current_path, gen), daemon=True
        ).start()

    def _root_worker(self, path: Path, gen: int):
        results = scan_children(path)
        if gen == self._root_gen:
            self.root.after(0, self._on_root_done, results, gen)

    def _on_root_done(self, results: list[tuple[Path, int]], gen: int):
        if gen != self._root_gen:
            return
        self.progress.stop()
        self.btn_scan.state(["!disabled"])

        total = sum(s for _, s in results)
        for p, size in results:
            self._insert_node("", p, size, total)

        n = len(results)
        self.status_var.set(
            f"{n} director{'y' if n == 1 else 'ies'}  —  Total: {format_size(total)}"
        )

    # ── Lazy expand ───────────────────────────────────────────────────────────

    def _on_expand(self, _event=None):
        iid = self.tree.focus()
        if not iid or iid not in self._nodes or iid in self._expanding:
            return

        children = self.tree.get_children(iid)
        # Sole child absent from _nodes == placeholder
        if len(children) == 1 and children[0] not in self._nodes:
            self._expanding.add(iid)
            self.tree.item(children[0], text="  Scanning…")
            path = self._nodes[iid]
            threading.Thread(
                target=self._expand_worker, args=(iid, path), daemon=True
            ).start()

    def _expand_worker(self, parent_iid: str, path: Path):
        results = scan_children(path)
        self.root.after(0, self._on_expand_done, parent_iid, results)

    def _on_expand_done(self, parent_iid: str, results: list[tuple[Path, int]]):
        self._expanding.discard(parent_iid)

        # Remove placeholder child
        for child in self.tree.get_children(parent_iid):
            if child not in self._nodes:
                self.tree.delete(child)

        total = sum(s for _, s in results)
        for p, size in results:
            self._insert_node(parent_iid, p, size, total)

    # ── Tree helpers ──────────────────────────────────────────────────────────

    def _insert_node(self, parent_iid: str, path: Path, size: int, parent_total: int):
        iid = self._next_iid()
        self._nodes[iid] = path

        pct = size / parent_total * 100 if parent_total else 0
        self.tree.insert(
            parent_iid, "end",
            iid=iid,
            text=f"  {path.name}",
            values=(format_size(size), f"{pct:.1f}%", f"  {make_bar(pct)}"),
            tags=(size_tag(size),),
        )
        # Placeholder (not in _nodes) makes the row expandable
        self.tree.insert(iid, "end", iid=self._next_iid(), text="", tags=("dummy",))

    def _clear_tree(self):
        self.tree.delete(*self.tree.get_children())

    # ── Events ────────────────────────────────────────────────────────────────

    def _on_drive_change(self, _=None):
        drive = self.drive_var.get()
        if drive:
            self.current_path = Path(drive)
            self.path_var.set(str(self.current_path))
            self._rescan()

    def _on_path_enter(self, _=None):
        p = Path(self.path_var.get().strip())
        if p.is_dir():
            self.current_path = p
            self._rescan()
        else:
            messagebox.showerror("Invalid path", f"Directory not found:\n{p}")

    def _selected_path(self) -> Path | None:
        sel = self.tree.selection()
        return self._nodes.get(sel[0]) if sel else None

    def _on_right_click(self, event):
        row = self.tree.identify_row(event.y)
        if row and row in self._nodes:
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

    # ── Delete ────────────────────────────────────────────────────────────────

    def _delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        p = self._nodes.get(iid)
        if not p:
            return

        size_str = self.tree.set(iid, "size")
        if not self._confirm_delete(p, size_str):
            return

        self.status_var.set(f"Deleting {p.name} …")
        self.progress.start(8)
        threading.Thread(target=self._delete_worker, args=(iid, p), daemon=True).start()

    def _delete_worker(self, iid: str, path: Path):
        try:
            shutil.rmtree(path)
            self.root.after(0, self._on_delete_done, iid, path, None)
        except Exception as e:
            self.root.after(0, self._on_delete_done, iid, path, str(e))

    def _on_delete_done(self, iid: str, path: Path, error: str | None):
        self.progress.stop()
        if error:
            self.status_var.set("Ready")
            messagebox.showerror("Delete failed", f"Could not delete {path.name}:\n{error}")
            return

        # Remove this node and all its descendants from _nodes, then from tree
        self._remove_subtree(iid)
        self.status_var.set(f"Deleted {path.name}")

    def _remove_subtree(self, iid: str):
        """Remove iid and all descendants from the tree and _nodes dict."""
        for child in self.tree.get_children(iid):
            self._remove_subtree(child)
        self._nodes.pop(iid, None)
        if self.tree.exists(iid):
            self.tree.delete(iid)

    def _confirm_delete(self, path: Path, size_str: str) -> bool:
        """Show a custom confirmation dialog. Returns True if user confirms."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Confirm Delete")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.focus_set()

        # Center over main window
        self.root.update_idletasks()
        x = self.root.winfo_x() + self.root.winfo_width() // 2 - 220
        y = self.root.winfo_y() + self.root.winfo_height() // 2 - 90
        dialog.geometry(f"440x180+{x}+{y}")

        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Permanently delete this folder?",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(frame, text=f"  {path.name}",
                  font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 0))
        ttk.Label(frame, text=f"  {size_str}  —  {path}",
                  font=("Segoe UI", 9), foreground="#888").pack(anchor="w")
        ttk.Label(frame, text="This cannot be undone.",
                  font=("Segoe UI", 9), foreground="#c0392b").pack(anchor="w", pady=(8, 16))

        confirmed = tk.BooleanVar(value=False)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(anchor="e")

        def on_delete():
            confirmed.set(True)
            dialog.destroy()

        # Style the delete button red via a tk.Button (ttk doesn't support bg colour easily)
        tk.Button(btn_frame, text="Delete", bg="#c0392b", fg="white",
                  activebackground="#a93226", activeforeground="white",
                  relief="flat", padx=12, pady=4,
                  font=("Segoe UI", 10), command=on_delete).pack(side="left", padx=(0, 6))
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side="left")

        dialog.wait_window()
        return confirmed.get()

    # ── Uninstall ─────────────────────────────────────────────────────────────

    def _uninstall_selected(self):
        p = self._selected_path()
        if not p:
            return

        uninstaller = find_uninstaller(p)
        if uninstaller:
            if messagebox.askyesno(
                "Uninstall",
                f"Run uninstaller for {p.name}?\n\n{uninstaller.name}",
            ):
                subprocess.Popen([str(uninstaller)])
        else:
            if messagebox.askyesno(
                "No uninstaller found",
                f"No uninstaller was found in:\n{p}\n\n"
                "Open Windows Apps & Features to uninstall manually?",
            ):
                subprocess.Popen(["explorer", "ms-settings:appsfeatures"])

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    DriveDusterApp().run()
