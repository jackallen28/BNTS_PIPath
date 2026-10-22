"""The coding workspace: guide panel + editor + output, for lessons and Free Play."""
from __future__ import annotations

import shutil
import tempfile
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path

from .. import storage
from ..content import DATA_DIR
from ..gpio import (CAMERA_KINDS, HAT_FIX, SHIM, SIM_ENV, expand_events, guess_camera, mode_env, on_real_pi,
                    wiring_check_program, wiring_parts)
from ..hints import (CheckResult, Diagnosis, ErrorInfo, code_features, evaluate_checks, gpio_lint,
                     parse_traceback, precheck)
from ..levels import INFO as LEVEL_INFO, LEVELS, can_skip, goal_text, hint_rules, offer_tour
from ..adapt import Adapter
from ..freeplay import add_part as freeplay_add, load as freeplay_load, parts_from_code as freeplay_parts
from ..freeplay import pin_warnings as freeplay_warnings, wiring_rows as freeplay_rows
from ..review import review
from ..runner import Runner
from .board import VirtualBoard
from .console import Console
from .editor import CodeEditor
from .home import stars_for
from .onboarding import Screen
from .theme import C, TIER_COLOURS
from .tour import Tour
from .widgets import (ChoiceList, CogButton, MenuBar, PButton, RichText, ScrollFrame, TitleBar, about_box, card,
                      chip, entry, label, window)
from .wiring import WiringCard
from .wiring_walkthrough import WiringWalkthrough

DEMO_FILES = DATA_DIR / "demo_files"


def short_names(names: str, limit: int = 28) -> str:
    """Four long names don't fit in the title bar: keep the start."""
    return names if len(names) <= limit else names[:limit - 1].rstrip() + "…"


def copy_sample(src: Path, folder: Path, keep: bool = False) -> None:
    """Copy a sample file or folder from data/demo_files into folder. keep: don't replace what's there."""
    dest = folder / src.name
    try:
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True,
                            copy_function=(lambda a, b: None if Path(b).exists() else shutil.copy2(a, b))
                            if keep else shutil.copy2)
        elif src.exists() and not (keep and dest.exists()):
            shutil.copy(src, dest)
    except OSError:
        pass

# Reading these in a loop (instead of using events) is the classic "busy loop" on a Pi
POLLING_FEATURES = ("attr:is_pressed", "attr:is_held", "attr:motion_detected", "attr:is_active")

SUPPORT = {
    #             badge text      colour      (hint rules: see levels.py)
    "guided": ("Guided", C["ok"], 0),
    "scaffolded": ("Some help", C["info"], 1),
    "brief": ("On your own", C["accent"], 2),
}

COACH_STYLES = {
    "idle": (C["panel_alt"], C["muted"], "COACH"),
    "err": (C["err_soft"], C["err"], "COACH · SOMETHING BROKE"),
    "warn": (C["warn_soft"], C["warn"], "COACH · ALMOST THERE"),
    "ok": (C["ok_soft"], C["ok"], "COACH · NICE WORK"),
    "info": (C["info_soft"], C["info"], "COACH"),
}


# ====================================================================== Coach card

class CoachCard(tk.Frame):
    """Shows what happened on the last run, plus tiered hints."""

    def __init__(self, master, on_hint=None):
        super().__init__(master, bg=C["panel_alt"], relief="raised", bd=2)
        self.on_hint = on_hint
        self.bar = tk.Frame(self, bg=C["muted"], width=6)
        self.bar.pack(side="left", fill="y")
        self.inner = tk.Frame(self, bg=C["panel_alt"], padx=14, pady=12)
        self.inner.pack(side="left", fill="both", expand=True)
        self.kicker = label(self.inner, "COACH", font="small_bold", fg=C["muted"])
        self.kicker.pack(anchor="w")
        self.title = label(self.inner, "", font="h3", wraplength=290)
        self.title.pack(anchor="w", pady=(2, 4))
        self.body = RichText(self.inner)
        self.body.pack(fill="x")
        # a nudge or a suggestion from the adaptive coach: a yellow note with buttons
        self.offer_box = tk.Frame(self.inner, bg=C["tooltip"], relief="solid", bd=1, padx=10, pady=8)
        self.offer_title = label(self.offer_box, "", font="ui_bold", bg=C["tooltip"])
        self.offer_title.pack(anchor="w")
        self.offer_text = RichText(self.offer_box, bg=C["tooltip"], font="small")
        self.offer_text.pack(fill="x", pady=(2, 6))
        self.offer_row = tk.Frame(self.offer_box, bg=C["tooltip"])
        self.offer_row.pack(anchor="w")
        self.offer_kind = None
        self.where = tk.Frame(self.inner)
        self.hint_box = tk.Frame(self.inner)
        self.hint_box.pack(fill="x", pady=(8, 0))
        self.hint_btn = PButton(self.inner, "Need a hint?", self._hint, kind="secondary", font="small_bold", pady=5)
        self.hint_btn.pack(anchor="w", pady=(8, 0))
        self.hint_note = label(self.inner, "", font="small", fg=C["muted"], wraplength=280)
        self.hint_note.pack(anchor="w", pady=(4, 0))
        self.hints: list[str] = []
        self.shown = 0
        self.idle()

    def _style(self, kind: str):
        bg, fg, kicker = COACH_STYLES[kind]
        for w in [self, self.inner, self.kicker, self.title, self.body, self.where, self.hint_box,
                  self.hint_note, *self.where.winfo_children()]:
            try:
                w.configure(bg=bg)
            except tk.TclError:
                pass
        self.bar.configure(bg=fg)
        self.kicker.configure(text=kicker, fg=fg)

    def _set(self, kind, title, text):
        self._style(kind)
        self.title.configure(text=title.replace("`", ""))
        self.body.render(text)
        self.where.pack_forget()
        self.clear_offer()

    def offer(self, o, on_action) -> None:
        """Show a nudge ("Need a hand?") or a level suggestion, with its buttons."""
        self.offer_kind = o.kind
        self.offer_title.configure(text=("▸ " if o.kind == "nudge" else "★ ") + o.title)
        self.offer_text.render(o.text)
        for w in self.offer_row.winfo_children():
            w.destroy()
        for text, action in o.actions:
            PButton(self.offer_row, text, lambda a=action: on_action(a),
                    kind="primary" if action != "dismiss" and not self.offer_row.winfo_children() else "secondary",
                    font="small_bold", padx=8, pady=2).pack(side="left", padx=(0, 6))
        self.offer_box.pack(fill="x", pady=(8, 0), after=self.body)

    def clear_offer(self) -> None:
        self.offer_kind = None
        self.offer_box.pack_forget()

    def idle(self, text: str | None = None):
        self._set("idle", "I'm here to help",
                  text or "When you press **Run**, I'll check your work. If something breaks, I'll explain it here and point to the line.")
        self.set_hints([], None)

    def message(self, kind: str, title: str, text: str):
        self._set(kind, title, text)

    def diagnosis(self, d: Diagnosis, level: str = "beginner"):
        """Beginner: the plain explanation. Moderate: plus the deeper "why". Advanced (they've used
        Python before): Python's own words first, then the technical explanation."""
        text = d.explain
        if level == "advanced":
            said = f"Python says: `{d.error_type}: {d.message}`\n\n" if d.message and d.error_type[:6] != "PiPath" else ""
            text = said + (d.tech or d.explain)
        elif level == "moderate" and d.tech:
            text = f"{d.explain}\n\n**Under the bonnet:** {d.tech}"
        self._set("err", d.title, text)
        for w in self.where.winfo_children():
            w.destroy()
        if d.line:
            bg = COACH_STYLES["err"][0]
            self.where.configure(bg=bg)
            label(self.where, f"Line {d.line}", font="small_bold", fg=C["err"], bg=bg).pack(side="left")
            if d.code_line:
                tk.Label(self.where, text=f"  {d.code_line[:60]}  ", font="code_ui", bg=C["ed_bg"],
                         fg=C["err"], padx=4, relief="sunken", bd=2).pack(side="left", padx=8)
            self.where.pack(anchor="w", fill="x", pady=(8, 0), before=self.hint_box)

    # ---- hints
    def set_hints(self, hints: list[str], locked_msg: str | None, already_shown: int = 0):
        self.hints = hints
        self.shown = min(already_shown, len(hints))
        for w in self.hint_box.winfo_children():
            w.destroy()
        for i in range(self.shown):
            self._render_hint(i)
        self._update_btn(locked_msg)

    def _render_hint(self, i: int):
        bg = self.inner.cget("bg")
        row = tk.Frame(self.hint_box, bg=bg)
        row.pack(fill="x", pady=(4, 0))
        tk.Label(row, text=f"Hint {i + 1}", font="small_bold", fg="#FFFFFF", bg=C["purple"], padx=6,
                 relief="raised", bd=2).pack(side="left", anchor="n")
        rt = RichText(row, bg=bg)
        rt.pack(side="left", fill="x", expand=True, padx=(8, 0))
        rt.render(self.hints[i])

    def _update_btn(self, locked_msg: str | None):
        if not self.hints:
            self.hint_btn.pack_forget()
            self.hint_note.configure(text="")
            return
        self.hint_btn.pack(anchor="w", pady=(8, 0), before=self.hint_note)
        if locked_msg:
            self.hint_btn.configure(text="Hint locked")
            self.hint_btn.set_enabled(False)
            self.hint_note.configure(text=locked_msg)
        elif self.shown >= len(self.hints):
            self.hint_btn.configure(text="No more hints")
            self.hint_btn.set_enabled(False)
            self.hint_note.configure(text="Still stuck? Ask a classmate to read it with you, then your teacher.")
        else:
            nth = ["first", "second", "third"][self.shown] if self.shown < 3 else "next"
            self.hint_btn.configure(text=f"Show {nth} hint  ({self.shown + 1} of {len(self.hints)})")
            self.hint_btn.set_enabled(True)
            self.hint_note.configure(text="Hints start small. Try each one before asking for the next.")

    def _hint(self):
        if self.shown < len(self.hints):
            self._render_hint(self.shown)
            self.shown += 1
            self._update_btn(None)
            if self.on_hint:
                self.on_hint(self.shown)


# ====================================================================== Base workspace

class Workspace(Screen):
    """Top bar, guide panel (left), editor, Output and (for GPIO) the board.

    The app keeps workspaces between visits and re-uses them: making ~100 widgets again
    every time an activity opened was the slowest thing on a Pi 3B. hide() parks one,
    on_show() wakes it up, and set_gpio() switches the board on or off for an activity.
    """
    left_width = 420

    def __init__(self, app, title: str = "", subtitle: str = ""):
        super().__init__(app)
        self.runner = Runner(app.settings["busy_loop_seconds"], app.settings["max_output_lines"])
        self._poll_job = None
        self._busy = False                     # a run is under way (from launch until it's been checked)
        self._tour = None
        self._save_job = None
        self._closed_streams = 0
        self._exit_code = None
        self._run_started = time.time()        # when the last run began (file checks only count newer files)
        self._special: str | None = None      # None (a normal run), "demo" or "wiring"
        self._special_jobs: list = []
        self._special_dir: str | None = None
        self._demo_input: list[str] = []      # answers "Watch the goal" types in, one at a time
        self._type_job = None
        self._typed = 0
        self._echo_tip = False
        self._out_tail = "\n"                 # last character the program printed
        self._last_out = 0.0
        self._warm_job = None
        self._keys_bound = False
        self.gpio = False                     # set by set_gpio()
        self.real_pi = on_real_pi()
        saved = storage.app_state().get("gpio_mode", "real")
        self.mode = saved if self.real_pi and saved in ("sim", "real") else "sim"
        cam = storage.app_state().get("camera")
        self.camera = cam if cam in CAMERA_KINDS else guess_camera()
        self.sim_object = "face"
        self.mode_box: tk.Frame | None = None

        # ---- top bar: a retro title bar, the school logo in the corner
        bar = self.topbar = TitleBar(self, title, height=56, logo=True, font="h3", sub=subtitle)
        bar.pack(fill="x")
        self.home_btn = bar.add_right(PButton(bar, "◂ Activities", self.go_home, kind="secondary",
                                              font="small_bold", pady=3))
        self.cog_btn = bar.add_right(CogButton(bar, lambda: app.open_settings()), pad=8)
        self.help_btn = bar.add_right(PButton(bar, "? Tour", self.start_tour, kind="secondary", font="small_bold",
                                              pady=3), pad=8)
        self.names_lbl = bar.add_right(tk.Label(bar, text=short_names(app.student.first_name), font="small_bold", fg="#FFFFFF",
                                                bg=C["title_b"]), pad=12)
        self.menubar = MenuBar(self, [("File", self._menu_file), ("Edit", self._menu_edit), ("Run", self._menu_run),
                                      ("View", self._menu_view), ("Help", self._menu_help)])
        self.menubar.pack(fill="x")

        # ---- body
        self.pane = tk.PanedWindow(self, orient="horizontal", sashwidth=7, bg=C["bg"], bd=0, sashrelief="raised")
        self.pane.pack(fill="both", expand=True)
        self.left = tk.Frame(self.pane, bg=C["bg"])
        right = tk.Frame(self.pane, bg=C["bg"])
        self.pane.add(self.left, minsize=320, width=self.left_width)
        self.pane.add(right, minsize=420)

        # toolbar above the editor
        tb = self.toolbar = tk.Frame(right, bg=C["bg"], padx=8, pady=5, relief="raised", bd=2)
        tb.pack(fill="x")
        self.run_btn = PButton(tb, "▶  Run", self.run, kind="go", font="ui_bold", padx=18)
        self.run_btn.pack(side="left")
        self.stop_btn = PButton(tb, "■  Stop", self.stop, kind="stop", font="small_bold")
        self.stop_btn.pack(side="left", padx=8)
        self.stop_btn.set_enabled(False)
        label(tb, "F5", font="small", fg=C["muted"]).pack(side="left")
        self.file_lbl = tk.Label(tb, text="", font="code_ui", fg=C["ink"], bg="#FFFFFF", relief="sunken", bd=2,
                                 padx=6)
        self.file_lbl.pack(side="left", padx=12)
        PButton(tb, "A+", lambda: self.zoom_code(1), kind="dark", font="small_bold", padx=8, pady=2).pack(side="right")
        PButton(tb, "A−", lambda: self.zoom_code(-1), kind="dark", font="small_bold", padx=8, pady=2).pack(side="right", padx=4)
        self.save_lbl = label(tb, "", font="small", fg=C["muted"])
        self.save_lbl.pack(side="right", padx=12)

        vpane = self.vpane = tk.PanedWindow(right, orient="vertical", sashwidth=7, bg=C["bg"], bd=0,
                                            sashrelief="raised")
        vpane.pack(fill="both", expand=True)
        self.editor = CodeEditor(vpane, on_change=self._changed)
        vpane.add(self.editor, minsize=160, stretch="always")
        self.board: VirtualBoard | None = None       # made the first time an activity needs it
        self.board_shown = False
        self.bottom = tk.PanedWindow(vpane, orient="horizontal", sashwidth=7, bg=C["bg"], bd=0, sashrelief="raised")
        self.console = Console(self.bottom, on_send=self._send_input)
        self.bottom.add(self.console, minsize=220, stretch="always")
        self._bottom_h = 230
        vpane.add(self.bottom, minsize=150, height=self._bottom_h, stretch="never")

    # ---------------------------------------------------------------- the menu bar
    def _menu_file(self) -> list:
        return [("Save", "Ctrl+S", self.save_now, True),
                ("Open my folder", "", self.open_folder, True),
                None,
                ("Back to activities", "", self.go_home, True)]

    def _menu_edit(self) -> list:
        ed = self.editor
        return [("Undo", "Ctrl+Z", ed.undo, True), ("Redo", "Ctrl+Y", ed.redo, True), None,
                ("Cut", "Ctrl+X", ed.cut, True), ("Copy", "Ctrl+C", ed.copy, True),
                ("Paste", "Ctrl+V", ed.paste, True), ("Select all", "Ctrl+A", ed.select_all, True), None,
                ("Find...", "Ctrl+F", lambda: ed.find_bar.open("find"), True),
                ("Replace...", "Ctrl+H", lambda: ed.find_bar.open("replace"), True),
                ("Go to line...", "Ctrl+G", lambda: ed.find_bar.open("line"), True),
                ("Comment / uncomment", "Ctrl+/", ed.toggle_comment, True)]

    def review_code(self) -> None:
        """Run > Review my code: tips on how the code is written (no AI: pipath/review.py)."""
        tips = review(self.editor.get_code())
        if not tips:
            self.coach.message("ok", "Code review", "Nothing to flag. Your code is tidy: clear names, no repeats, "
                                                    "and nothing unchecked that I can spot. Nice work!")
        else:
            self.coach.message("info", "Code review", "Your code works the way you wrote it. These are ways to "
                               "make it *better* code, the kind of thing a programmer checks before sharing:\n\n" +
                               "\n".join(f"- **{t.title}** ({t.idea}): {t.text}" for t in tips))
        if hasattr(self, "guide"):
            self.guide.scroll_to(self.coach)

    def _menu_run(self) -> list:
        items = [("Run", "F5", self.run, self.run_btn.enabled), ("Stop", "Shift+F5", self.stop, self.runner.running),
                 ("Review my code", "", self.review_code, True)]
        if self.can_watch_goal():
            items.append(("Watch the goal", "", self.watch_goal, not self.runner.running))
        if self.gpio:
            items += [None, ("Check my wiring", "", self.check_wiring, bool(getattr(self, "parts", None))),
                      ("● Simulator" if self.mode == "sim" else "   Simulator", "", lambda: self.set_mode("sim"), True),
                      ("● Real Pi" if self.mode == "real" else "   Real Pi", "", lambda: self.set_mode("real"),
                       self.real_pi)]
        return items

    def _menu_view(self) -> list:
        return [("Bigger code text", "Ctrl+=", lambda: self.zoom_code(1), True),
                ("Smaller code text", "Ctrl+−", lambda: self.zoom_code(-1), True), None,
                ("Settings...", "", self.app.open_settings, True)]

    def _menu_help(self) -> list:
        return [("Take the tour", "", self.start_tour, True), None,
                ("About PiPath", "", lambda: about_box(self.app), True)]

    def can_watch_goal(self) -> bool:
        return False

    def open_folder(self) -> None:
        """Open the student's work folder in the file manager (photos, logs, the party folder...)."""
        folder = self.code_path().parent
        folder.mkdir(parents=True, exist_ok=True)
        if shutil.which("xdg-open"):
            import subprocess
            subprocess.Popen(["xdg-open", str(folder)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            self.console.write(f"Opening your folder: {folder}\n", "info")
        else:
            self.console.write(f"Your work is saved in: {folder}\n", "info")

    def set_gpio(self, on: bool, camera: bool = False) -> None:
        """GPIO / camera activities (and Free Play) get the Simulator / Real Pi switch and the board."""
        self.gpio = on
        if on:
            if self.mode_box is None:
                self._mode_switch(self.toolbar)
            else:
                self.mode_box.pack(side="left", padx=(6, 0), after=self.stop_btn)
            if self.board is None:
                self.board = VirtualBoard(self.bottom, on_press=self._board_press, on_release=self._board_release,
                                          on_goal=self.watch_goal, on_object=self._pick_object,
                                          on_camera=self.next_camera, on_distance=self._board_distance)
            self.board.reset()
            self.board.set_mode(self.mode)
            if camera:
                self.board.enable_camera(self.camera, self.sim_object)
            else:
                self.board.disable_camera()
            if not self.real_pi:
                self.board.set_status("Simulator only (not a Pi)")
        else:
            if self.mode_box is not None:
                self.mode_box.pack_forget()
            self.hide_board()
        height = 270 if on else 230
        if height != self._bottom_h:
            self._bottom_h = height
            self.vpane.paneconfigure(self.bottom, height=height)

    # ---------------------------------------------------------------- settings (the cog)
    def zoom_code(self, step: int) -> None:
        self.editor.zoom(step)
        self.app.student.profile["code_size"] = tkfont.nametofont("code").cget("size")
        self.app.student.save_profile()

    def settings_changed(self, what: str) -> None:
        """Settings changed something: names, hardware (Simulator / Real Pi, camera) or text size."""
        if what == "names":
            self.names_lbl.configure(text=short_names(self.app.student.first_name))
            self.topbar._layout()
        elif what == "hardware":
            state = storage.app_state()
            mode = state.get("gpio_mode", "real")
            mode = mode if self.real_pi and mode in ("sim", "real") else "sim"
            if mode != self.mode:
                if self.runner.running:
                    self._abandon_run()        # switching pins mid-run: stop without checking
                self.mode = mode
                if self.mode_box is not None:
                    self._paint_mode()
                if self.board:
                    self.board.set_mode(mode)
            cam = state.get("camera")
            if cam in CAMERA_KINDS and cam != self.camera:
                if self.uses_camera() and self.runner.running:
                    self._abandon_run()        # the program was using the old camera
                self.camera = cam
                if self.board:
                    self.board.set_camera_kind(cam)
                self._schedule_warm()
        elif what == "text":
            self.editor._set_tabs()
            self.editor._draw_gutter()

    # ---------------------------------------------------------------- showing, hiding, leaving
    def on_show(self) -> None:
        """The app has just put this screen on show (new, or kept from last time)."""
        if not self._keys_bound:
            self._keys_bound = True
            for seq, fn in (("<F5>", self.run), ("<Shift-F5>", self.stop), ("<Control-s>", self.save_now)):
                self.bind_all(seq, lambda e, f=fn: (None if self.app.busy_with_dialog() else f(), "break")[1])
        self._schedule_warm(900)        # once the screen is up

    def hide(self) -> None:
        """Leaving for the activity picker: tidy up and wait, out of sight, for next time."""
        self.park()
        self._unbind_keys()
        self.pack_forget()

    def park(self) -> None:
        """Stop everything this screen is doing: the program, timers, the spare runner. Saves the code."""
        self._abandon_run()
        if self._warm_job:
            self.after_cancel(self._warm_job)
            self._warm_job = None
        self.runner.close()
        self._save_pending()
        if self._tour is not None:
            self._tour.finish()
            self._tour = None

    def _abandon_run(self) -> None:
        """Stop a program (or a demo) without checking it: the student has moved on."""
        self._cancel_special_jobs()
        if self._poll_job:
            self.after_cancel(self._poll_job)
            self._poll_job = None
        was_running = self.runner.running
        if was_running:
            self.runner.stop("abandoned")
        self._busy = False
        if self._special:
            self._special = None
            if self.board:
                self.board.set_mode(self.mode)
        self._clean_special_dir()
        self.run_btn.set_enabled(True)
        self.stop_btn.set_enabled(False)
        self.console.set_input_enabled(False)
        if self.board:
            self.board.reset()
            self.board.set_live(False)
        if was_running:
            self._schedule_warm()

    def _save_pending(self) -> None:
        if self._save_job:
            self.after_cancel(self._save_job)
            self.save_now()

    def _unbind_keys(self) -> None:
        if self._keys_bound:
            self._keys_bound = False
            for seq in ("<F5>", "<Shift-F5>", "<Control-s>"):
                self.unbind_all(seq)

    def destroy(self):
        self._unbind_keys()
        self.park()
        super().destroy()

    # ---------------------------------------------------------------- saving
    def code_path(self) -> Path:
        raise NotImplementedError

    def _changed(self):
        if getattr(self, "adapter", None) is not None:
            self.adapter.on_edit(time.monotonic())
        if self._save_job is None:
            self.save_lbl.configure(text="Editing…")
        else:
            self.after_cancel(self._save_job)
        self._save_job = self.after(1200, self.save_now)

    def save_now(self):
        self._save_job = None
        storage.write_text(self.code_path(), self.editor.get_code())
        self.save_lbl.configure(text="Saved ✓")

    def go_home(self):
        self.save_now()
        self.app.show("home")

    # ---------------------------------------------------------------- running
    def run(self):
        if self._busy or self.runner.running or not self.run_btn.enabled:
            return
        code = self.editor.get_code()
        self.save_now()
        self.editor.clear_marks()
        self._run_started = time.time()
        if not code.strip():
            self.console.clear()
            self.console.write("Your file is empty. Type some code first (or press Watch the goal to see "
                               "what it should do).\n", "info")
            return
        problem = precheck(code, self.current_starter())
        if problem:
            self.console.clear()
            self.console.write("Not run yet: there are blanks (___) to fill in first.\n", "info")
            self.after_run(code, problem, crashed=True, stdout="")
            return
        self.console.clear()
        self.console.write(f"▶ Running {self.code_path().name}" +
                           (" on the real pins" if self.gpio and self.mode == "real" else
                            " in the Simulator" if self.gpio else "") + "\n", "info")
        if self.gpio:
            for w in gpio_lint(code):
                self.console.write(f"⚠ Coach tip: {w}\n", "warn")
        if self.stop_is_finish():
            self.console.write("This program keeps running. Test it, then press ■ Stop to check your work.\n", "info")
        self._launch(code, self.code_path(), self.extra_env())

    def _send_input(self, text: str) -> None:
        self.runner.send_input(text)
        if self.runner.running:
            self.console.set_status("running…", C["go"])

    def _launch(self, code: str, path: Path, env: dict, status: str = "running…"):
        if self._poll_job:                 # never two poll loops at once
            self.after_cancel(self._poll_job)
            self._poll_job = None
        self._busy = True
        self.console.set_status(status, C["go"])
        self.run_btn.set_enabled(False)
        self.stop_btn.set_enabled(True)
        self.console.set_input_enabled(True)
        self._closed_streams = 0
        self._exit_code = None
        self._run_code = code
        self._run_started = time.time()
        self._out_tail, self._last_out = "\n", time.monotonic()
        self._echo_tip = False
        if self.board:
            self.board.reset()
        # every program runs through the shim: it reports pins, photos and input() to the app
        self.runner.start(path, path.parent, env, shim=SHIM)
        if self.board and self.gpio:
            if env.get("GPIOZERO_PIN_FACTORY") == "mock":
                for pin, cm in self.board.sim_distance.items():     # where the slider is now
                    self.runner.send_command(f"distance {pin} {cm}")
            else:
                self.board.set_live(True)
        self._poll()

    def extra_env(self) -> dict:
        if not self.gpio:
            return {}
        return dict(mode_env(self.mode), **self.camera_env())

    def camera_env(self, sim: bool = False) -> dict:
        return {"PIPATH_CAMERA": "sim" if sim else self.camera, "PIPATH_CAMERA_OBJECT": self.sim_object}

    def uses_camera(self) -> bool:
        return False

    # ---------------------------------------------------------------- warm start
    def preload(self) -> list[str]:
        """Modules the spare runner loads before it's needed (slow to import on a Pi 3B)."""
        if not self.gpio:
            return []
        mods = ["gpiozero", "gpiozero.pins.mock"]
        if self.real_pi:
            mods.append("gpiozero.pins.lgpio")
        if self.uses_camera():
            mods.append("pipath_camera")
            if self.camera == "ribbon":
                mods.append("picamera2")
        return mods

    def _schedule_warm(self, delay: int = 400):
        if self.app.screen is not self:        # out of sight: no spare process (saves memory on a Pi 3B)
            return
        if self._warm_job is None:
            self._warm_job = self.after(delay, self.warm_up)

    def warm_up(self):
        """Have a spare runner waiting with gpiozero loaded, so the next Run starts straight away."""
        self._warm_job = None
        if not self.runner.running:
            self.runner.warm_up(SHIM, self.preload())

    # ---------------------------------------------------------------- camera
    def next_camera(self):
        """Cycle Simulated -> USB -> Ribbon. Saved for this Pi (it's the Pi's hardware, not the student's)."""
        kinds = list(CAMERA_KINDS)
        if self.runner.running:
            self._abandon_run()
        self.camera = kinds[(kinds.index(self.camera) + 1) % len(kinds)]
        storage.set_app_state(camera=self.camera)
        if self.board:
            self.board.set_camera_kind(self.camera)
        self._schedule_warm()
        self.app.settings_changed("hardware")
        self.console.write(f"Camera: {CAMERA_KINDS[self.camera]}. " + {
            "sim": "Pretend pictures. Pick what the camera sees on the board.\n",
            "usb": "Plug a USB webcam into the Pi.\n",
            "ribbon": "A Raspberry Pi camera on the ribbon cable.\n"}[self.camera], "info")

    def _pick_object(self, key: str):
        self.sim_object = key
        if self.board:
            self.board.set_camera_object(key)
        if self.runner.running:
            self.runner.send_command(f"show {key}")

    def current_starter(self) -> str:
        return ""

    def uses_gpio(self) -> bool:
        return False

    def stop_is_finish(self) -> bool:
        """True when pressing Stop is the normal way to end (programs that run until stopped)."""
        return False

    # ---------------------------------------------------------------- Simulator / Real Pi
    def _mode_switch(self, tb):
        box = self.mode_box = tk.Frame(tb, bg=C["bg"])
        box.pack(side="left", padx=(6, 0), after=self.stop_btn)   # before the file name, so it never gets squeezed out
        label(box, "Run on:", font="small", fg=C["muted"]).pack(side="left", padx=(0, 6))
        self.sim_btn = PButton(box, "Simulator", lambda: self.set_mode("sim"), kind="dark", font="small_bold", padx=10, pady=3)
        self.sim_btn.pack(side="left")
        self.real_btn = PButton(box, "Real Pi", lambda: self.set_mode("real"), kind="dark", font="small_bold", padx=10, pady=3)
        self.real_btn.pack(side="left", padx=(2, 0))
        self._paint_mode()

    def _paint_mode(self):
        """The chosen one looks pressed in (sunken), like a Windows 95 toggle."""
        for btn, key in ((self.sim_btn, "sim"), (self.real_btn, "real")):
            btn.set_kind("primary" if self.mode == key else "dark")
        self.real_btn.set_enabled(self.real_pi)

    def set_mode(self, mode: str):
        if mode == self.mode or (mode == "real" and not self.real_pi):
            return
        if self.runner.running:
            self._abandon_run()
        self.mode = mode
        storage.set_app_state(gpio_mode=mode)
        self._paint_mode()
        if self.board:
            self.board.set_mode(mode)
        self.console.write("Switched to " + ("the Simulator: the board on screen is your hardware.\n" if mode == "sim"
                                             else "the Real Pi: your program drives the real GPIO pins, live, "
                                                  "and the board shows what they're doing.\n"), "info")
        self.app.settings_changed("hardware")        # the other kept screens follow

    def show_board(self):
        if self.board is None:
            return
        width = 480 if self.uses_camera() else 400
        if not self.board_shown:
            self.bottom.add(self.board, minsize=260, width=width, stretch="never")
            self.board_shown = True
            self._board_w = width
        elif width != getattr(self, "_board_w", width):
            self.bottom.paneconfigure(self.board, width=width)
            self._board_w = width

    def hide_board(self):
        if self.board_shown:
            self.bottom.forget(self.board)
            self.board_shown = False

    def _board_press(self, pin: int):
        if self.runner.running:
            self.runner.send_command(f"press {pin}")
        else:
            self.board.set_status("Press Run first, then press the button")

    def _board_release(self, pin: int):
        self.runner.send_command(f"release {pin}")

    def _board_distance(self, pin: int, cm: float):
        if self.runner.running:
            self.runner.send_command(f"distance {pin} {cm}")

    def _on_gpio(self, msg: dict):
        guide = getattr(self, "wiring_walkthrough", None)
        if guide is not None and self._special == "wiring-guide":
            guide.message(msg)
            return
        t = msg.get("t")
        if t == "devices":
            if msg["devices"]:
                self.show_board()
            self.board.set_devices(msg["devices"])
        elif t == "pins":
            self.board.set_values(msg["pins"])
        elif t == "photo":
            self.show_board()
            if self.board.camera is None:
                self.board.enable_camera(self.camera, self.sim_object)
            if msg.get("grid"):
                caption = "What the computer sees"
            else:
                caption = Path(msg.get("path", "")).name or "Photo"
            self.board.show_photo(msg.get("preview", ""), caption)

    # ---------------------------------------------------------------- demo and wiring-check runs
    def run_special(self, kind: str, code: str, env: dict, intro: str, seconds: float | None = None,
                    events: list | None = None, stdin: str = "", files: list | None = None):
        """Run code that isn't the student's (the goal demo, or a wiring check) in a temp folder."""
        if self._busy or self.runner.running:
            return
        self.save_now()
        self._clean_special_dir()
        self._special = kind
        self._special_dir = tempfile.mkdtemp(prefix="pipath_")
        path = Path(self._special_dir) / ("goal.py" if kind == "demo" else "wiring_check.py")
        path.write_text(code, encoding="utf-8")
        for rel in files or []:       # sample data the demo needs, from data/demo_files/
            copy_sample(DEMO_FILES / rel, Path(self._special_dir))
        self.editor.clear_marks()
        self.console.clear()
        self.console.write(intro + "\n", "info")
        if kind == "demo" and self.board:
            self.board.set_mode("sim")
        self._launch(code, path, env, status="playing the goal…" if kind == "demo" else "checking wiring…")
        self._demo_input = stdin.splitlines()
        self._typed = 0
        self._echo_tip = False
        for when, command in expand_events(events):
            self._special_jobs.append(self.after(int(when * 1000), lambda c=command: self._demo_command(c)))
        if seconds:
            self._special_jobs.append(self.after(int(seconds * 1000), lambda: self.runner.stop("special")))

    def _demo_command(self, command: str):
        self.runner.send_command(command)
        words = command.split()
        if words[0] == "show" and self.board:
            self.board.set_camera_object(words[1])   # the picker follows the demo
        elif words[0] == "stat" and len(words) == 3:
            self.console.write(f"(Watch the goal pretends: {words[1]} = {words[2]})\n", "info")
        elif words[0] == "distance" and self.board and len(words) == 3:
            self.board.set_distance(int(words[1]), float(words[2]))      # so does the slider

    def _maybe_type_demo(self):
        """Watch the goal: type the next answer when the program is waiting at a prompt."""
        if not self._demo_input or self._type_job is not None or not self.runner.running:
            return
        quiet = time.monotonic() - self._last_out
        if (self._out_tail != "\n" and quiet > 0.05) or quiet > 1.5:
            self._type_job = self.after(350 if self._typed < 5 else 60, self._type_demo)

    def _type_demo(self):
        self._type_job = None
        if not self._demo_input or not self.runner.running:
            return
        line = self._demo_input.pop(0)
        self._typed += 1
        self.console.write(line + "\n", "in")      # shown as if someone typed it
        self._out_tail, self._last_out = "\n", time.monotonic()
        self.runner.send_input(line)

    def _cancel_special_jobs(self):
        self._demo_input = []
        if self._type_job is not None:
            self.after_cancel(self._type_job)
            self._type_job = None
        for job in self._special_jobs:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        self._special_jobs = []

    def _clean_special_dir(self):
        if self._special_dir:
            shutil.rmtree(self._special_dir, ignore_errors=True)
            self._special_dir = None

    def watch_goal(self):
        pass

    def special_finished(self, kind: str, stdout: str, stderr: str):
        pass

    def stop(self):
        if self.runner.running:
            self.runner.stop("user")

    def _poll(self):
        out, errs, pins = [], [], None
        for ev in self.runner.poll():
            kind = ev[0]
            if kind == "out":
                out.append(ev[1])
            elif kind == "err":
                errs.append(ev[1])
            elif kind == "gpio":
                t = ev[1].get("t")
                if t == "pins":
                    pins = ev[1]          # only the newest pin states need drawing
                elif t == "input":
                    self._asked_input()
                elif self.board:
                    self._on_gpio(ev[1])
            elif kind == "closed":
                self._closed_streams += 1
            elif kind == "exit":
                self._exit_code = ev[1]
        if out:
            text = "".join(out)
            if self._special == "wiring-guide" and getattr(self, "wiring_walkthrough", None) is not None:
                self.wiring_walkthrough.append_output(text)
            else:
                self.console.write(text)
            self._out_tail, self._last_out = text[-1], time.monotonic()
        if errs:
            self._show_stderr("".join(errs))
        if pins is not None and self.board:
            self._on_gpio(pins)
        if self._demo_input:
            self._maybe_type_demo()
        if self._exit_code is not None and self._closed_streams >= 2:
            self._poll_job = None
            self._finished()
        else:
            self._poll_job = self.after(40, self._poll)

    def _show_stderr(self, text: str) -> None:
        if self._special == "wiring-guide":
            # The runner retains diagnostics for validation; generated source stays hidden.
            return
        """Errors and warnings show as they happen, in red (like Thonny), without long folder names."""
        folder = (self._special_dir + "/") if self._special and self._special_dir else str(self.code_path().parent) + "/"
        self.console.write(text.replace(folder, ""), "err")
        self._out_tail, self._last_out = "\n", time.monotonic()
        if "DistanceSensorNoEcho" in text and not self._echo_tip:
            self._echo_tip = True
            self.console.write("⚠ Coach tip: the distance sensor didn't answer. Check TRIG, ECHO (through its two "
                               "resistors), 5V and GND. " + HAT_FIX + "\n", "warn")

    def _asked_input(self) -> None:
        """The program is waiting in input()."""
        if self._special == "demo":
            if self._demo_input and self._type_job is None:
                self._type_job = self.after(350 if self._typed < 5 else 60, self._type_demo)
        else:
            self.console.waiting_for_answer()

    def _finished(self):
        self._busy = False
        self._schedule_warm()
        if self.board:
            self.board.set_live(False)
        self.run_btn.set_enabled(True)
        self.stop_btn.set_enabled(False)
        self.console.set_input_enabled(False)
        code, reason, rc = self._run_code, self.runner.stop_reason, self._exit_code
        stderr = self.runner.stderr
        if self.board:
            self.board.set_values({})       # like real hardware: when a program ends, its pins switch off
        if self._special:
            kind, self._special = self._special, None
            self._cancel_special_jobs()
            if self.board:
                self.board.set_mode(self.mode)
            self.console.set_status("")
            if kind == "wiring-guide":
                guide = getattr(self, "wiring_walkthrough", None)
                if guide is not None:
                    guide.finished(self.runner.stdout, stderr, rc, reason)
            elif reason == "user":               # stopped part-way: don't report it as finished
                self.console.write("\n■ Stopped.\n", "info")
            else:
                self.special_finished(kind, self.runner.stdout, stderr)
            self._clean_special_dir()
            return
        folder = str(self.code_path().parent) + "/"
        if reason == "user":
            if self.stop_is_finish() and not (rc not in (0, None, -15) and stderr.strip()):
                self.console.write("\n■ Stopped. Checking your work…\n", "info")
                self.console.set_status("stopped")
                self.after_run(code, None, False, self.runner.stdout)
                return
            self.console.write("\n■ Stopped.\n", "info")
            self.console.set_status("stopped")
            self.editor.focus()
            return
        err: ErrorInfo | None = None
        if reason in ("runaway_output", "runaway_busy"):
            msg = "output" if reason == "runaway_output" else "busy"
            if msg == "busy" and self.gpio and any(code_features(code).get(f) for f in POLLING_FEATURES):
                msg = "busy_gpio"
            err = ErrorInfo("PiPathRunaway", msg)
            self.console.write("\n■ PiPath stopped your program: it looked like a never-ending loop.\n", "err")
        elif rc != 0:
            err = parse_traceback(stderr, str(self.code_path()), code)
            if err is None and not (rc == 1 and "File \"" not in stderr):
                err = ErrorInfo("Crash", f"exit code {rc}", None)
            # (rc 1 with no traceback is sys.exit("Bye"): the program chose to stop, so it finished)
        crashed = err is not None
        if crashed:
            self.console.set_status("error", C["err"])
        else:
            self.console.write("\n✓ Program finished.\n", "info")
            self.console.set_status("finished", C["go"])
        self.after_run(code, err, crashed, self.runner.stdout)
        if self.focus_get() is None or not isinstance(self.focus_get(), tk.Entry):
            self.editor.focus()            # back to the code, ready for the next change

    def after_run(self, code: str, err: ErrorInfo | None, crashed: bool, stdout: str):
        raise NotImplementedError

    # ---------------------------------------------------------------- tour
    def tour_steps(self) -> list[dict]:
        return []

    def start_tour(self):
        if self._tour is not None:             # one tour at a time
            self._tour.finish()
        offer = getattr(self, "_tour_offer", None)
        if offer is not None and offer.winfo_exists():
            offer.destroy()
        self._touring = True
        self._tour = Tour(self.app, self.tour_steps(), on_done=self._tour_finished)
        self._tour.start()

    def _tour_finished(self):
        self._tour = None
        if self.app.student is not None:
            self.tour_done()

    def tour_done(self):
        pass


# ====================================================================== Lesson workspace

class LessonWorkspace(Workspace):
    """An activity: intro (with the step plan) → steps (instructions, checklist, Coach) → outro.

    One LessonWorkspace is made and then re-used for every activity (load() swaps the activity
    in). The step panel's widgets are made once and updated for each step. Destroying and
    remaking them every time made opening activities and changing steps slow on a Pi 3B.
    """

    def __init__(self, app, lesson_id: str, tour: bool = False):
        self.lesson = None
        super().__init__(app)
        # non-GPIO activities have no board to put it on, so Watch the goal goes in the toolbar
        self.goal_btn = PButton(self.toolbar, "Watch the goal  ▶", self.watch_goal, kind="dark",
                                font="small_bold", padx=10, pady=3)
        self.intro_view = self.outro_view = self.wiring_card = None
        self._build_left()
        self.load(lesson_id, tour)

    def load(self, lesson_id: str, tour: bool = False) -> None:
        """Show an activity (the first one, or the next one the student picks)."""
        app = self.app
        if self.lesson is not None:
            self.park()
        self.project = app.catalog.project(lesson_id)
        self.lesson = app.catalog.lesson(lesson_id)
        self.steps = self.lesson["steps"]
        self.lp = app.student.lesson(lesson_id)
        tier = next(t for t in app.catalog.tiers if t["id"] == self.project["tier"])
        self.tier_title = tier["title"]
        self.tier_colour = TIER_COLOURS.get(self.project["tier"], C["accent"])
        self.topbar.set_text(self.lesson["title"], f"{tier['title']} activity  ·  {self.project['subtitle']}")
        self.file_lbl.configure(text=self.lesson["file_name"])
        self.level = app.student.help_level
        self._wiring_approved = set()
        self._wiring_pending = None
        self.wiring_walkthrough = None

        # per-step state
        self.view = None
        self.step_i = max(0, min(self.lp.get("step", 0), len(self.steps) - 1))
        self.attempts = 0
        self.step_runs = 0
        self.hint_ctx = None
        self.revealed: dict = dict(self.lp.get("hints_seen") or {})    # hints opened, kept across visits
        profile = app.student.profile
        self.adapter = Adapter(self.level, profile.get("adapt"), enabled=profile.get("adaptive", True) is not False)
        self._unlocked = False               # a nudge's "Show me a hint" opened the hints early
        self.confirmed: set[int] = set()      # "I saw it happen" boxes ticked this step
        self._last_eval = None                # (code, stdout, crashed, started) of the last run, for re-checking
        self.show_full = False                # Advanced: has the student opened the full explanation?
        self.parts = wiring_parts(self.lesson) if self.lesson.get("requires_gpio") else []

        # this activity's own panels (the rest of the screen is kept)
        for v in (self.intro_view, self.outro_view, self.wiring_card):
            if v is not None:
                v.destroy()
        self.intro_view = self.outro_view = self.wiring_card = None
        if self.lesson.get("requires_gpio"):
            self.wiring_card = WiringCard(self.g, self.lesson, self.project, self.parts, open_=False,
                                          on_check=self.check_wiring)
        self.step_lbl.configure(fg=self.tier_colour)
        self.set_gpio(self.uses_gpio(), self.uses_camera())
        if self.gpio:
            self.board.set_parts(self.parts)
            self.show_board()

        code = app.student.read_lesson_code(self.lesson["file_name"])
        self.editor.set_code(code if code is not None else "")
        for rel in self.lesson.get("files", []):      # sample files the activity uses (never overwritten)
            copy_sample(DEMO_FILES / rel, self.code_path().parent, keep=True)
        self.save_lbl.configure(text="Saved ✓")
        self.console.clear()
        self.console.set_status("")

        if self.lp["status"] == "complete" and not tour:
            self.show_outro()
        elif self.lp["status"] == "new":
            self.show_intro()
        else:
            self.enter_step(self.step_i)

        self._ensure_wiring_gate()
        if tour and self.wiring_walkthrough is None:
            self.after(350, self.start_tour)

    def park(self) -> None:
        super().park()
        self._close_wiring_gate()
        if getattr(self, "_adapt_job", None):
            self.after_cancel(self._adapt_job)
            self._adapt_job = None
        offer = getattr(self, "_tour_offer", None)
        if offer is not None and offer.winfo_exists():
            offer.destroy()

    def code_path(self) -> Path:
        return self.app.student.lesson_code_path(self.lesson["file_name"])

    def current_starter(self) -> str:
        return self.steps[self.step_i].get("starter", "") if self.view == "step" else ""

    def uses_gpio(self) -> bool:
        return bool(self.lesson and (self.lesson.get("requires_gpio") or self.lesson.get("requires_camera")))

    def uses_camera(self) -> bool:
        return bool(self.lesson and self.lesson.get("requires_camera"))

    def stop_is_finish(self) -> bool:
        return self.view == "step" and self.steps[self.step_i].get("run_mode") == "until_stopped"

    def run(self):
        if self._ensure_wiring_gate():
            return
        if self.view == "step":            # the intro and the finish screen have nothing to run
            super().run()

    def wiring_context(self):
        return (self.lesson["id"], self.mode, self.camera if self.uses_camera() else None)

    def _ensure_wiring_gate(self, continuation=None):
        if self.level != "beginner" or not self.uses_gpio():
            return False
        context = self.wiring_context()
        if context in getattr(self, "_wiring_approved", set()):
            return False
        if continuation is not None:
            self._wiring_pending = continuation
        guide = getattr(self, "wiring_walkthrough", None)
        if guide is None:
            settings = getattr(self.app, "_settings", None)
            if settings is not None and settings.winfo_exists():
                return True
            self.run_btn.set_enabled(False)
            self.wiring_walkthrough = WiringWalkthrough(self, self._wiring_done, self.go_home)
        elif guide.context != context:
            self._abandon_run()
            guide.reset_context()
        return True

    def _close_wiring_gate(self):
        guide = getattr(self, "wiring_walkthrough", None)
        self.wiring_walkthrough = None
        if guide is not None:
            guide.destroy()

    def _wiring_done(self, context):
        guide = self.wiring_walkthrough
        if guide is None or not guide.session.ready or context != self.wiring_context():
            return
        self._wiring_approved.add(context)
        pending, self._wiring_pending = self._wiring_pending, None
        self._close_wiring_gate()
        self.console.clear()
        self.run_btn.set_enabled(self.view == "step")
        if pending is not None:
            pending()

    # ---------------------------------------------------------------- help level
    def cycle_level(self):
        """Beginner → Moderate → Advanced. Saved for this student (Settings does this too)."""
        self.app.student.set_help_level(LEVELS[(LEVELS.index(self.level) + 1) % len(LEVELS)])
        self.settings_changed("help")

    def settings_changed(self, what: str) -> None:
        super().settings_changed(what)
        if what == "help" and self.lesson is not None:
            new = self.app.student.help_level
            self.adapter.level = new
            self.adapter.enabled = self.app.student.profile.get("adaptive", True) is not False
            if new != self.level:
                self.level = new
                if self.view == "intro":
                    self.show_intro()
                if self.view == "step":
                    self._render_step(keep_coach=True)
                    self.coach.message("info", f"Help: {LEVEL_INFO[self.level][0]}", LEVEL_INFO[self.level][1])

        if what in ("hardware", "help") and self.lesson is not None:
            if what == "hardware":
                self._wiring_approved.clear()
            if self.level == "beginner":
                self._ensure_wiring_gate()
            else:
                if self.wiring_walkthrough is not None:
                    self._abandon_run()
                    self._close_wiring_gate()

    # ---------------------------------------------------------------- left panel
    def _build_left(self):
        self.guide = ScrollFrame(self.left, bg=C["bg"])
        self.wheel_default = self.guide.canvas    # the wheel scrolls the instructions wherever the mouse is
        self.guide.pack(fill="both", expand=True)
        self.g = tk.Frame(self.guide.body, bg=C["bg"], padx=18, pady=14)
        self.g.pack(fill="both", expand=True)

        self.foot = tk.Frame(self.left, bg=C["bg"], relief="raised", bd=2, padx=12, pady=8)
        self.foot.pack(fill="x", side="bottom")
        self.back_btn = PButton(self.foot, "◂ Back", self.prev_step, kind="secondary", font="small_bold")
        self.back_btn.pack(side="left")
        self.next_btn = PButton(self.foot, "Next step  ▸", self.next_step, kind="secondary")
        self.next_btn.pack(side="right")
        self.skip_btn = PButton(self.foot, "Skip  ▸", self.skip_step, kind="secondary", font="small_bold")

        self.foot_note = label(self.foot, "", font="small", fg=C["muted"])
        self.foot_note.pack(side="right", padx=10)
        self._build_step_view()

    def _show_view(self, name: str, wiring_open: bool | None = None):
        """Show one of the intro / step / outro panels (they're kept, not rebuilt)."""
        self.view = name
        views = {"intro": self.intro_view, "step": self.step_view, "outro": self.outro_view}
        for v in views.values():
            if v is not None:
                v.pack_forget()
        target = views[name]
        target.pack(fill="x")
        if self.wiring_card is not None:
            if name == "outro":
                self.wiring_card.pack_forget()
            else:
                self.wiring_card.pack(fill="x", pady=(0, 14), before=target)
                if wiring_open is not None:
                    self.wiring_card.set_open(wiring_open)
        self.guide.to_top()

    def _build_step_view(self):
        v = self.step_view = tk.Frame(self.g, bg=C["bg"])
        row = tk.Frame(v, bg=C["bg"])
        row.pack(fill="x", pady=(0, 12))
        self.step_lbl = label(row, "", font="small_bold")
        self.step_lbl.pack(side="left")
        # one dot per step (drawn, so a different activity doesn't need new widgets)
        self.dots = tk.Canvas(row, height=12, width=1, bg=C["bg"], highlightthickness=0, bd=0)
        self.dots.pack(side="right")
        self.dots.bind("<Button-1>", self._dots_clicked)
        self.dots.tag_bind("open", "<Enter>", lambda e: self.dots.configure(cursor="hand2"))
        self.dots.tag_bind("open", "<Leave>", lambda e: self.dots.configure(cursor=""))
        self._dot_spans: list[tuple[int, int]] = []
        top = tk.Frame(v, bg=C["bg"])
        top.pack(fill="x")
        self.step_badge = tk.Label(top, text="", font="small_bold", fg="#FFFFFF", padx=4, pady=1)
        self.step_badge.pack(side="right", anchor="n", pady=4)          # packed first: it always gets its room
        self.step_title = label(top, "", font="h2", wraplength=250)
        self.step_title.pack(side="left", anchor="w")
        self.instructions = RichText(v)
        self.instructions.pack(fill="x", pady=(8, 0))
        self.explain_link = label(v, "", font="small_bold", fg=C["info"], cursor="hand2")
        self.explain_link.bind("<Button-1>", lambda e: self._toggle_explanation())
        self.checklist_frame = card(v, padx=14, pady=10)
        self.checklist_frame.pack(fill="x", pady=(14, 0))
        label(self.checklist_frame, "YOUR CHECKLIST", font="small_bold", fg=C["muted"],
              bg=C["panel"]).pack(anchor="w", pady=(0, 4))
        self.check_box = tk.Frame(self.checklist_frame, bg=C["panel"])
        self.check_box.pack(fill="x")
        self.check_rows: list = []            # (icon, text) for this step's checks
        self._row_pool: list = []             # rows are kept and re-used from step to step
        self._confirm_rows: set[int] = set()
        self.coach = CoachCard(v, on_hint=self._hint_used)
        self.coach.pack(fill="x", pady=(14, 0))

    def _dots_clicked(self, e):
        for j, (x0, x1) in enumerate(self._dot_spans):
            if x0 - 2 <= e.x <= x1 + 2:
                self._dot_clicked(j)
                return

    def _dot_clicked(self, j: int):
        if j in self.lp["steps_done"] or j in self.lp["steps_started"]:
            self.enter_step(j)

    def _paint_dots(self):
        done = set(self.lp["steps_done"])
        started = set(self.lp["steps_started"])
        skipped = set(self.lp.get("steps_skipped", []))
        cv = self.dots
        cv.delete("all")
        self._dot_spans = []
        x = 0
        for i in range(len(self.steps)):
            w = 22 if i == self.step_i else 10
            col = (self.tier_colour if i == self.step_i else C["ok"] if i in done
                   else C["faint"] if i in skipped else C["line"])
            tags = ("open",) if i in done or i in started else ()
            cv.create_rectangle(x, 1, x + w, 11, fill=col, outline="", tags=tags)
            self._dot_spans.append((x, x + w))
            x += w + 4
        cv.configure(width=max(1, x - 4))

    # ---------------------------------------------------------------- intro / outro
    def show_intro(self):
        if self.intro_view is None:
            self._build_intro_view()
        advanced = self.level == "advanced" and len(self.steps) > 1
        self._show_view("intro", wiring_open=not advanced)
        if self.board:
            self.board.show_goal_button(False)
        self._show_toolbar_goal(False)
        self.back_btn.set_enabled(False)
        self.skip_btn.pack_forget()
        if advanced:                       # used Python before: skipping ahead is one click away
            self._jump_row.pack(fill="x", pady=(0, 12), after=self._intro_title)
        else:
            self._jump_row.pack_forget()
        self.next_btn.configure(text="Start step 1  ▸")
        self.next_btn.set_kind("primary")
        self.next_btn.set_enabled(True)
        self.next_btn.command = self.start_lesson
        self.foot_note.configure(text="")
        self.run_btn.set_enabled(False)
        if not self.editor.get_code().strip():
            self.editor.set_code("# Your code will appear here when you start step 1\n")
            self.editor.highlight()

    def _build_intro_view(self):
        v = self.intro_view = tk.Frame(self.g, bg=C["bg"])
        chip(v, self.tier_title.upper() + " ACTIVITY", "#FFFFFF", self.tier_colour).pack(anchor="w")
        self._intro_title = label(v, self.lesson["title"], font="h1")
        self._intro_title.pack(anchor="w", pady=(8, 10))
        self._jump_row = tk.Frame(v, bg=C["tooltip"], relief="solid", bd=1, padx=10, pady=8)
        label(self._jump_row, "Used Python before? Skip the practice steps and build the finished project.",
              font="small", wraplength=330).pack(anchor="w")
        PButton(self._jump_row, "Jump to the challenge  ▸", self.jump_to_challenge, kind="primary",
                font="small_bold", pady=3).pack(anchor="w", pady=(6, 0))
        rt = RichText(v, font="ui")
        rt.pack(fill="x")
        rt.render(self.lesson["intro"])
        meta = card(v, padx=12, pady=10)
        meta.pack(fill="x", pady=(16, 0))
        label(meta, f"{len(self.steps)} steps  ·  about {self.project['minutes']} minutes",
              font="small_bold", bg=C["panel"]).pack(anchor="w")
        label(meta, "You'll learn: " + ", ".join(self.project["concepts"]), font="small", fg=C["muted"],
              bg=C["panel"], wraplength=340).pack(anchor="w", pady=(2, 0))
        plan = card(v, padx=12, pady=10)
        plan.pack(fill="x", pady=(12, 0))
        steps_md = "\n".join(f"{i + 1}. {st['title']}  *({SUPPORT.get(st['support'], SUPPORT['scaffolded'])[0].lower()})*"
                             for i, st in enumerate(self.steps))
        rt = RichText(plan, bg=C["panel"], font="small")
        rt.tag_configure("b", font="small_bold")
        rt.pack(fill="x")
        rt.render("**THE PLAN: STEP BY STEP**\nEach step has a checklist and builds on the one before, from the "
                  "first part to the finished project.\n" + steps_md)
        # the curriculum links are in Settings > Curriculum

    def jump_to_challenge(self):
        """Advanced: start at the last step. The step before it's example answer goes in the editor when the
        challenge builds on it, and the steps in between count as skipped (faint dots), not done."""
        self.app.student.mark_started(self.lesson["id"])
        last = len(self.steps) - 1
        skipped = self.lp.setdefault("steps_skipped", [])
        for i in range(last):
            if i not in self.lp["steps_done"] and i not in skipped:
                skipped.append(i)
        carry = self.steps[last - 1].get("demo") if self.steps[last].get("starter_mode", "keep") != "replace" else None
        self.run_btn.set_enabled(True)
        self.enter_step(last, carry_code=carry)
        self.coach.message("info", "Straight to the challenge",
                           "The example code from the step before is in the editor, so you have something to build on. "
                           "Your own code is saved in backups. Stuck? Go **Back** to any step.")

    def start_lesson(self):
        self.app.student.mark_started(self.lesson["id"])
        self.run_btn.set_enabled(True)
        self.enter_step(0)

    def show_outro(self):
        if self.outro_view is not None:
            self.outro_view.destroy()
        v = self.outro_view = tk.Frame(self.g, bg=C["bg"])
        self.editor.clear_marks()
        if self.board:
            self.board.show_goal_button(False)
        self._show_toolbar_goal(False)
        st = stars_for(self.app, self.lp.get("hints_used", 0))
        win, box = window(v, "Activity complete!", padx=18, pady=14, bg="#FFFFFF")
        win.pack(fill="x")
        label(box, self.lesson["title"], font="h1", fg=C["purple"], bg="#FFFFFF").pack(anchor="w", pady=(0, 4))
        label(box, "★" * st + "☆" * (3 - st), font="glyph", fg="#E0A000", bg="#FFFFFF").pack(anchor="w")
        msg = {3: "Independence stars: you barely needed any hints!",
               2: "Independence stars: you used a few hints and got there.",
               1: "You finished! Next time, try one more run before opening a hint."}[st]
        label(box, msg, fg=C["ink"], bg="#FFFFFF", wraplength=340).pack(anchor="w", pady=(4, 0))
        hints = self.lp.get("hints_used", 0)
        label(box, f"{self.lp.get('runs', 0)} runs  ·  {self.lp.get('errors', 0)} bugs found  ·  "
                   f"{hints} hint{'' if hints == 1 else 's'}", font="small", fg=C["muted"],
              bg="#FFFFFF").pack(anchor="w", pady=(8, 0))
        rt = RichText(v)
        rt.pack(fill="x", pady=(16, 0))
        rt.render(self.lesson["outro"])
        stretch = self.project.get("stretch") or []
        if stretch:
            lv, lbox = window(v, "Level up  (Year 9-10)", padx=14, pady=10)
            lv.pack(fill="x", pady=(14, 0))
            rt = RichText(lbox)
            rt.pack(fill="x")
            rt.render("Already know your way around Python? Take this project further:\n" +
                      "\n".join(f"- {s}" for s in stretch) +
                      "\n\nUse **Run > Review my code** to check how your code is written, not just whether it works.")
        self._show_view("outro")
        self.skip_btn.pack_forget()
        self.back_btn.set_enabled(True)
        self.back_btn.command = lambda: self.enter_step(0)
        self.back_btn.configure(text="Review steps")
        self.next_btn.configure(text="Back to activities  ▸")
        self.next_btn.command = self.go_home
        self.next_btn.set_kind("primary")
        self.next_btn.set_enabled(True)
        self.foot_note.configure(text="")

    # ---------------------------------------------------------------- steps
    def enter_step(self, i: int, carry_code: str | None = None):
        """Go to step i. carry_code: code to start from (a skipped step's example answer)."""
        if self._ensure_wiring_gate(lambda: self.enter_step(i, carry_code)):
            return
        self._abandon_run()                # a program from the last step isn't checked against this one
        self._save_pending()               # so a backup has the newest code
        student = self.app.student
        step = self.steps[i]
        first_time = i not in self.lp["steps_started"]
        if carry_code is not None:
            student.backup_lesson_code(self.lesson["file_name"], i + 1)
            self.editor.set_code(carry_code)
        if first_time:
            starter = step.get("starter")
            mode = step.get("starter_mode", "keep")
            if starter and mode == "replace":
                student.backup_lesson_code(self.lesson["file_name"], i + 1)
                self.editor.set_code(starter)
            elif starter and mode == "append":
                self.editor.append_code(starter)
            self.lp["steps_started"].append(i)
        if first_time or carry_code is not None:
            self.save_now()
        self.step_i = i
        self.lp["step"] = i
        student.save_progress()
        self.attempts = 0
        self.step_runs = 0
        self.confirmed = set()
        self._last_eval = None
        self._unlocked = False
        self.adapter.start_step(time.monotonic(), already_done=i in self.lp["steps_done"])
        if getattr(self, "_adapt_job", None):
            self.after_cancel(self._adapt_job)
        self._adapt_job = self.after(30_000, self._adapt_tick)
        self.show_full = False
        self.hint_ctx = ("step", i)
        if self.board:
            self.board.show_goal_button(bool(step.get("demo")))
        self._show_toolbar_goal(bool(step.get("demo")))
        self._show_view("step", wiring_open=i == 0 and i not in self.lp["steps_done"])
        self._render_step()
        self.console.clear()
        self.console.set_status("")
        self.editor.focus()
        self._maybe_offer_tour()

    def _show_toolbar_goal(self, on: bool):
        if on and not self.gpio:
            self.goal_btn.pack(side="left", padx=(10, 0), after=self.file_lbl)
        else:
            self.goal_btn.pack_forget()

    def _maybe_offer_tour(self):
        """First time in a step: offer the tour, but don't force it (Advanced never sees it)."""
        if (self.app.student.profile.get("tour_done") or getattr(self, "_tour_offered", False)
                or not offer_tour(self.level)):
            return
        self._tour_offered = True
        self.after(300, self._offer_tour)

    def _offer_tour(self):
        if (getattr(self, "_touring", False) or self.app.student.profile.get("tour_done")
                or not self.winfo_ismapped()):
            return
        ov, body = window(self, "First time here?", padx=20, pady=14)
        self._tour_offer = ov
        ov.place(relx=.5, rely=.42, anchor="center")
        label(body, "Want a quick look around the workspace? It takes about 30 seconds.",
              wraplength=340).pack(anchor="w", pady=(0, 14))
        row = tk.Frame(body, bg=C["bg"])
        row.pack(fill="x")

        def skip():
            ov.destroy()
            self.tour_done()

        def go():
            ov.destroy()
            self.start_tour()

        PButton(row, "No thanks, I'll explore", skip, kind="secondary", font="small_bold").pack(side="left")
        PButton(row, "Show me around  ▸", go, kind="primary").pack(side="right", padx=(16, 0))

    def _render_step(self, keep_coach: bool = False):
        """Fill the (already built) step panel with this step's content."""
        step = self.steps[self.step_i]
        self.step_lbl.configure(text=f"STEP {self.step_i + 1} OF {len(self.steps)}")
        self._paint_dots()
        badge, colour, _ = SUPPORT.get(step["support"], SUPPORT["scaffolded"])
        self.step_title.configure(text=step["title"])
        self.step_badge.configure(text=f" {badge.upper()} ", bg=colour)
        self._render_instructions()

        done = self.step_i in self.lp["steps_done"]
        checks = step["checks"]
        self.check_rows = []
        self._confirm_rows = set()
        for idx, c in enumerate(checks):
            row, icon, txt = self._check_row(idx)
            if c["type"] == "confirm" and not done:
                # a box the student ticks when they have seen it happen (on screen or on the breadboard)
                self._confirm_rows.add(idx)
                icon.configure(text="", font="small_bold", fg=C["ok"], bg=C["panel_alt"], highlightthickness=2,
                               highlightbackground=C["faint"], cursor="hand2")
                txt.configure(text=c.get("label", c["type"]) + "\n(tick this when you've seen it happen)",
                              cursor="hand2")
            else:
                icon.configure(text="✓" if done else "○", font="ui_bold", fg=C["ok"] if done else C["faint"],
                               bg=C["panel"], highlightthickness=0, cursor="")
                txt.configure(text=c.get("label", c["type"]), cursor="")
            row.pack(fill="x", pady=2)
            self.check_rows.append((icon, txt))
        for row, _icon, _txt in self._row_pool[len(checks):]:
            row.pack_forget()

        for idx in self.confirmed & self._confirm_rows:      # re-drawn (a new help level): keep the ticks
            self.check_rows[idx][0].configure(text="✓", highlightbackground=C["ok"])
        if not keep_coach:
            if done:
                self.coach.message("ok", "Step complete", step.get("success", "Well done!"))
            elif self.step_i in self.lp.get("steps_skipped", []) and self.level == "advanced":
                self.coach.idle("You skipped this step earlier. Have a go now, or press **Next step**.")
            else:
                self.coach.idle()
        self._refresh_hints()
        self._update_footer()

    def _check_row(self, idx: int):
        """Checklist row number idx: (frame, icon, text). Made the first time a step needs it."""
        while len(self._row_pool) <= idx:
            k = len(self._row_pool)
            row = tk.Frame(self.check_box, bg=C["panel"])
            icon = tk.Label(row, text="", width=2, bg=C["panel"])
            icon.pack(side="left", padx=(3, 7), pady=2)
            txt = label(row, "", bg=C["panel"], wraplength=290)
            txt.pack(side="left", fill="x")
            for w in (icon, txt):
                w.bind("<Button-1>", lambda e, k=k: k in self._confirm_rows and self._toggle_confirm(k))
            self._row_pool.append((row, icon, txt))
        return self._row_pool[idx]

    def _render_instructions(self):
        step = self.steps[self.step_i]
        goal = goal_text(step) if self.level == "advanced" else None
        if goal and not self.show_full:
            self.instructions.render(goal)
            self.explain_link.configure(text="▸ Show the full explanation")
            self.explain_link.pack(anchor="w", pady=(6, 0), after=self.instructions)
        elif goal:
            self.instructions.render(step["text"])
            self.explain_link.configure(text="▾ Just show the goal")
            self.explain_link.pack(anchor="w", pady=(6, 0), after=self.instructions)
        else:
            self.instructions.render(step["text"])
            self.explain_link.pack_forget()

    def _toggle_explanation(self):
        self.show_full = not self.show_full
        self._render_instructions()

    def _update_footer(self):
        done = self.step_i in self.lp["steps_done"]
        last = self.step_i == len(self.steps) - 1
        self.back_btn.configure(text="◂ Back")
        self.back_btn.command = self.prev_step
        self.back_btn.set_enabled(self.step_i > 0)
        self.next_btn.command = self.next_step
        self.next_btn.configure(text="Finish activity  ★" if last else "Next step  ▸")
        self.next_btn.set_kind("primary" if done else "secondary")
        self.next_btn.set_enabled(done)
        skip = can_skip(self.level) and not done and not last
        if skip:
            self.skip_btn.pack(side="right", before=self.next_btn, padx=(0, 6))
        else:
            self.skip_btn.pack_forget()
        self.foot_note.configure(text="" if done or skip else "Tick all boxes")

    def prev_step(self):
        if self.step_i > 0:
            self.enter_step(self.step_i - 1)

    def next_step(self):
        if self.step_i == len(self.steps) - 1:
            self.app.student.mark_complete(self.lesson["id"])
            self.show_outro()
        else:
            self.enter_step(self.step_i + 1)

    def skip_step(self):
        """Advanced only: move on without finishing this step. The step's example answer is put in
        the editor (your code is saved in backups/), so the next step has what it builds on."""
        if not can_skip(self.level) or self.step_i >= len(self.steps) - 1 or self.runner.running:
            return
        i = self.step_i
        skipped = self.lp.setdefault("steps_skipped", [])
        if i not in skipped:
            skipped.append(i)
        nxt = self.steps[i + 1]
        demo = self.steps[i].get("demo")
        carry = demo.strip("\n") + "\n" if demo and nxt.get("starter_mode", "keep") != "replace" else None
        self.enter_step(i + 1, carry_code=carry)
        self.coach.message("info", "Step skipped",
                           "No problem. " + ("The example code for the step you skipped is in the editor, so this "
                                             "step has what it builds on. Your own code is saved in backups. "
                                             if carry else "") + "You can go back to it any time.")

    # ---------------------------------------------------------------- hints
    def _hint_limits(self) -> tuple[int, int]:
        return hint_rules(self.level, self.steps[self.step_i]["support"])

    def _refresh_hints(self, diag: Diagnosis | None = None):
        unlock_after, max_err = self._hint_limits()
        if diag is not None:
            self.hint_ctx = ("err", self.step_i, diag.entry_id)
            hints, locked = diag.hints[:max_err], None
        else:
            self.hint_ctx = ("step", self.step_i)
            hints = self.steps[self.step_i].get("hints", [])
            if self.level == "advanced":
                hints = hints[:max_err]          # never the near-answer
            left = unlock_after - self.attempts
            locked = None
            if left > 0 and not self._unlocked and not self.adapter.hints_early(
                    time.monotonic()):
                locked = ("Have a go first: hints unlock after you press Run." if left == 1 and self.attempts == 0
                          else f"Hints unlock after {left} more tr{'y' if left == 1 else 'ies'}. You can do this!")
        self.coach.set_hints(hints, locked, self.revealed.get(self._hint_key(), 0))

    def _hint_key(self) -> str:
        return ":".join(str(x) for x in self.hint_ctx)

    def _hint_used(self, shown: int):
        key = self._hint_key()
        new = shown > self.revealed.get(key, 0)
        if new:
            self.adapter.on_hint()
        self.revealed[key] = max(shown, self.revealed.get(key, 0))
        self.lp["hints_seen"] = self.revealed
        if new and self.step_i not in self.lp["steps_done"]:      # looking back at a finished step is free
            self.lp["hints_used"] = self.lp.get("hints_used", 0) + 1
        self.app.student.save_progress()
        self.guide.scroll_to(self.coach)

    # ---------------------------------------------------------------- after a run
    def after_run(self, code, err, crashed, stdout):
        if self.view != "step":
            return
        step = self.steps[self.step_i]
        is_precheck = err is not None and err.type == "PiPathBlanks"
        if not is_precheck:
            self.step_runs += 1
            self.lp["runs"] = self.lp.get("runs", 0) + 1
        diag = None
        if err is not None:
            diag = self.app.engine.diagnose(err, step)
            if not is_precheck:
                self.lp["errors"] = self.lp.get("errors", 0) + 1
            self.editor.mark_error_line(diag.line)

        self._last_eval = (code, stdout, crashed, self._run_started)
        done = self.step_i in self.lp["steps_done"]          # already ticked off: no need to tick again
        results = evaluate_checks(step["checks"], code, stdout, crashed, self.step_runs,
                                  None if done else self.confirmed,
                                  folder=self.code_path().parent, since=self._run_started)
        self._show_results(results)
        passed = all(r.passed for r in results)
        waiting = [r for r in results if not r.passed]

        now = time.monotonic()
        if passed:
            self._complete_step()
        elif not diag and all(r.type == "confirm" for r in waiting):
            self.adapter.after_run(now, True)          # the code works; only the tick boxes are left
            # the code did everything the checks can see; now the student confirms what happened
            self.coach.message("info", "Did you see it happen?",
                               "Your code passed the checks. Now watch the board" +
                               (" or your breadboard" if self.mode == "real" else "") +
                               " and tick the box when you see it:\n\n" +
                               "\n".join(f"- **{r.label}**" for r in waiting) +
                               "\n\nNot quite right? Change your code and press **Run** again.")
            self.coach.set_hints([], None)
        else:
            self.attempts += 1
            if diag:
                self.coach.diagnosis(diag, self.level)
                self._refresh_hints(diag)
            else:
                first = next(r for r in results if not r.passed and r.type != "confirm")
                self.coach.message("warn", "Your program ran, but…",
                                   f"**Not ticked yet:** {first.label}\n\n" + (first.fail or "Read the step instructions again and compare them with your code."))
                self._refresh_hints()
            if not is_precheck:
                failing = next((r.label for r in results if not r.passed and r.type != "confirm"), None)
                self._show_offer(self.adapter.after_run(now, False, diag.entry_id if diag else None, failing))
                if self.adapter.hints_early(now) and not diag:
                    self._refresh_hints()          # stuck: hints open up early
        self.app.student.save_progress()
        self._update_footer()
        self._paint_dots()
        self.guide.scroll_to(self.coach)

    def _complete_step(self):
        step = self.steps[self.step_i]
        if self.step_i not in self.lp["steps_done"]:
            self.lp["steps_done"].append(self.step_i)
        if self.step_i == len(self.steps) - 1:
            after = "\n\nThat was the last step. Press **Finish activity** to see your stars."
        else:
            after = (f"\n\n**Next up:** {self.steps[self.step_i + 1]['title']}. "
                     "Press **Next step** when you're ready.")
        review_text = ""
        if self.level != "beginner":           # Year 9-10: how well is it written, not just does it work?
            tips = review(self._last_eval[0] if self._last_eval else self.editor.get_code(), max_tips=2)
            if tips:
                review_text = "\n\n**Code review** (optional, to level up):\n" + "\n".join(
                    f"- **{t.title}** ({t.idea}): {t.text}" for t in tips)
        self.coach.message("ok", "Step complete!", step.get("success", "Well done!") + review_text + after)
        self.coach.set_hints([], None)
        self.console.set_status("✓ step complete", C["ok"])
        offer = self.adapter.step_done(time.monotonic())
        self.app.student.profile["adapt"] = self.adapter.state()
        self.app.student.save_profile()
        self._show_offer(offer)

    # ---------------------------------------------------------------- adaptive coaching
    def _show_offer(self, offer) -> None:
        if offer is not None:
            self.coach.offer(offer, self._offer_action)
            self.guide.scroll_to(self.coach)

    def _offer_action(self, action: str) -> None:
        self.coach.clear_offer()
        if action == "hint":
            self._unlocked = True
            self._refresh_hints()
            if self.coach.hints and self.coach.shown < len(self.coach.hints):
                self.coach._hint()
            elif self.can_watch_goal():
                self.watch_goal()
        elif action == "goal" and self.can_watch_goal():
            self.watch_goal()
        elif action == "full":
            if not self.show_full and goal_text(self.steps[self.step_i]) and self.level == "advanced":
                self._toggle_explanation()
            self.guide.canvas.yview_moveto(0)
        elif action.startswith("level:"):
            level = action.split(":", 1)[1]
            self.app.student.set_help_level(level)
            self.app.settings_changed("help")
            self.coach.message("info", f"Help level: {LEVEL_INFO[level][0]}",
                               LEVEL_INFO[level][1] + " Change it any time with the **Settings** cog.")

    def _adapt_tick(self) -> None:
        """Every 30 seconds on a step: is the student stuck and quiet? (A cheap check: no widgets.)"""
        self._adapt_job = None
        if self.view != "step" or self.lesson is None:
            return
        now = time.monotonic()
        if self.coach.offer_kind is None and not self.runner.running:
            self._show_offer(self.adapter.tick(now))
        if self.adapter.hints_early(now) and self.coach.hint_btn.cget("text") == "Hint locked":
            self._refresh_hints()
        self._adapt_job = self.after(30_000, self._adapt_tick)

    def _show_results(self, results: list[CheckResult]):
        for (icon, _txt), r in zip(self.check_rows, results):
            if r.type == "confirm" and str(icon.cget("highlightthickness")) != "0":
                icon.configure(text="✓" if r.passed else "", highlightbackground=C["ok"] if r.passed else C["warn"])
            else:
                icon.configure(text="✓" if r.passed else "✗", fg=C["ok"] if r.passed else C["err"])

    def _toggle_confirm(self, idx: int):
        if self.view != "step" or self.step_i in self.lp["steps_done"]:
            return
        if self.step_runs == 0:
            self.coach.message("info", "Run it first",
                               "Press **Run** and watch what happens. Then tick the box if you saw it.")
            return
        self.confirmed ^= {idx}
        icon = self.check_rows[idx][0]
        ticked = idx in self.confirmed
        icon.configure(text="✓" if ticked else "", highlightbackground=C["ok"] if ticked else C["faint"])
        if self._last_eval and ticked:
            code, stdout, crashed, started = self._last_eval
            step = self.steps[self.step_i]
            results = evaluate_checks(step["checks"], code, stdout, crashed, self.step_runs, self.confirmed,
                                      folder=self.code_path().parent, since=started)
            if all(r.passed for r in results):
                self._show_results(results)
                self._complete_step()
                self.app.student.save_progress()
                self._update_footer()
                self._paint_dots()
                self.guide.scroll_to(self.coach)

    # ---------------------------------------------------------------- goal demo + wiring check
    def watch_goal(self):
        if self._ensure_wiring_gate():
            return
        if self.view != "step":
            return
        step = self.steps[self.step_i]
        if not step.get("demo"):
            return
        env = dict(SIM_ENV, **self.camera_env(sim=True)) if self.gpio else {}
        env["PIPATH_DEMO"] = "1"           # pipath_computer shows what it would open, and opens nothing
        self.run_special("demo", step["demo"], env,
                         "▶ Watch the goal: this is what your program should do. (Your code isn't changed.)",
                         seconds=step.get("demo_seconds"), events=step.get("demo_events"),
                         stdin=step.get("demo_input", ""), files=step.get("demo_files"))

    def can_watch_goal(self) -> bool:
        return self.view == "step" and bool(self.steps[self.step_i].get("demo"))

    def check_wiring(self):
        if not self.parts or self.runner.running or self._busy:
            return
        where = "on the Simulator board" if self.mode == "sim" else "on your breadboard"
        self.run_special("wiring", wiring_check_program(self.parts), self.extra_env(),
                         f"▶ Checking your wiring {where}. Follow the instructions below.")

    def special_finished(self, kind: str, stdout: str, stderr: str):
        if kind == "demo":
            self.console.write("\n■ That's the goal! Now make your code do the same, then press Run.\n", "info")
        elif kind == "wiring":
            if self.wiring_card:
                self.wiring_card.mark_from_output(stdout)
            bad = [l for l in stdout.splitlines() if l.startswith("✗")]
            if bad:
                text = ("Some parts didn't respond:\n\n" + "\n".join(f"- {l[2:]}" for l in bad) +
                        "\n\n" + HAT_FIX.replace("try again", "press **Check my wiring** again"))
                self.console.write("\n⚠ Some parts didn't respond. Check those wires.\n", "warn")
                if self.view == "step":
                    self.coach.message("warn", "Check those wires", text)
            elif stdout.strip():
                self.console.write("\n✓ Wiring check finished. Did each LED blink and the buzzer beep?\n", "info")
                if self.view == "step":
                    self.coach.message("info", "Wiring check finished",
                                       "Every button and sensor answered. Did each LED blink and the buzzer beep? "
                                       "If one didn't, check its long leg (+) goes to the GPIO pin and the resistor is in.")

    # ---------------------------------------------------------------- tour
    def tour_steps(self):
        if self.view != "step":
            # the tour needs the checklist on screen
            self.app.student.mark_started(self.lesson["id"])
            self.enter_step(self.step_i)
        self.update_idletasks()
        return [
            {"widget": None, "side": "center", "title": "This is your workspace",
             "text": "Everything you need is on one screen. Let's take a 30-second look around."},
            {"widget": self.instructions, "side": "right", "title": "Read the step",
             "text": "Each activity is split into small **steps**. The instructions for the current step are here, on the left."},
            {"widget": self.checklist_frame, "side": "right", "title": "Your checklist",
             "text": "This is what the step wants your program to do. Every time you press Run, the boxes get ticked ✓ or crossed ✗."},
            {"widget": self.editor, "side": "inside", "title": "The editor",
             "text": "This is where you type your Python code. Colours help you spot different parts, and **Tab** indents a line."},
            {"widget": self.run_btn, "side": "bottom", "title": "Run it",
             "text": "Press **Run** (or **F5**) to try your code. Run often. It's the fastest way to find out what's happening."},
            {"widget": self.console, "side": "top", "title": "Output",
             "text": "Whatever your program prints shows up here. When your program asks a question, type your answer in the box at the bottom and press **Enter**."},
        ] + ([
            {"widget": self.sim_btn.master, "side": "bottom", "title": "Simulator or Real Pi?",
             "text": "**Simulator** runs your code on the pretend board. **Real Pi** uses the real GPIO pins and your breadboard. Try the Simulator first, then the real thing!"},
            {"widget": self.board, "side": "top", "title": "The board",
             "text": "Your LEDs, buttons and sensors live here. Click and hold a button to press it. **Watch the goal** shows what the finished step should do."},
        ] if self.gpio else []) + [
            {"widget": self.coach, "side": "right", "title": "The Coach",
             "text": "If your code breaks, the Coach explains why in plain English and shows which line. Hints start small. Try one at a time."},
            {"widget": self.cog_btn, "side": "bottom", "title": "Settings",
             "text": "Change things any time: how much help you get (**Beginner**, **Moderate** or **Advanced**), what the activity picker shows, your names, **Simulator** or **Real Pi**, and the code text size."},
            {"widget": self.home_btn, "side": "bottom", "title": "Saving",
             "text": "Your code **saves automatically**. Use **Activities** to pick something else anytime. Press **? Tour** to see this again."},
        ]

    def tour_done(self):
        self._touring = False
        p = self.app.student.profile
        if not p.get("tour_done"):
            p["tour_done"] = True
            self.app.student.save_profile()
            if self.view == "step" and self.step_i not in self.lp["steps_done"]:
                self.coach.message("info", f"Ready, {self.app.student.first_name}?",
                                   "Read the step, then press the green **Run** button and see what happens.")


# ====================================================================== Free Play

CHEATSHEET = """
## Python cheat sheet
```
print("Hello")          # show
name = input("Name? ")  # ask
age = int(input("Age? "))

if age >= 13:
    print("Teen")
elif age > 9:
    print("Tween")
else:
    print("Kid")

while age < 18:         # repeat
    age = age + 1

for i in range(5):      # 5 times
    print(i)

import random
n = random.randint(1, 6)

from time import sleep
sleep(1)                # wait 1s
```
"""


class FreePlayWorkspace(Workspace):
    """Free Play: the sandbox. No steps or checklists. Two kinds of help, the student's choice:
    "Guide me" (the Coach explains errors, nudges when stuck, suggests ideas to level up, and helps
    wire up the hardware the code uses) or "On my own" (errors are explained, nothing else).
    The left panel: help mode, the Coach, Add a part, My wiring, projects, starter ideas, cheat sheet."""
    left_width = 380

    def __init__(self, app):
        name = app.settings.get("free_play_name", "Free Play")
        super().__init__(app, name, "Your sandbox: build anything you like, with code and hardware.")
        self.set_gpio(True)       # the board appears as soon as a program makes an LED, Button...
        self.student = app.student
        self.current: Path | None = None
        self.view = "free"
        self.library = freeplay_load()
        self.parts: list[dict] = []
        self._parts_sig = None
        self._wiring_job = None
        self._tips_shown: set = set()
        self.wiring_card: WiringCard | None = None
        profile = app.student.profile
        self.help_mode = profile.get("free_play_mode", "guided")
        self.adapter = Adapter(app.student.help_level, None, enabled=self.help_mode == "guided", context="free")

        sf = self.guide = ScrollFrame(self.left, bg=C["bg"])
        self.wheel_default = sf.canvas
        sf.pack(fill="both", expand=True)
        g = tk.Frame(sf.body, bg=C["bg"], padx=16, pady=14)
        g.pack(fill="both", expand=True)

        label(g, "How much help do you want here?", font="small_bold").pack(anchor="w")
        self.mode_choice = ChoiceList(g, [("guided", "Guide me", "Tips, nudges and wiring help as I build"),
                                          ("solo", "On my own", "Only explain errors when my code breaks")],
                                      self.help_mode, on_change=self.set_help_mode, wrap=300)
        self.mode_choice.pack(anchor="w", pady=(2, 8))

        self.coach = CoachCard(g)
        self.coach.pack(fill="x", pady=(4, 0))

        # ---- the parts library
        label(g, "Add a part", font="h3").pack(anchor="w", pady=(14, 2))
        label(g, "Puts working code where your cursor is, with pins from the pin plan.", font="small",
              fg=C["muted"], wraplength=330).pack(anchor="w")
        for title, kinds, cols in (("Hardware", ("led", "button", "buzzer", "distance", "rgbled", "bar", "camera"), 3),
                                   ("Code", ("software",), 2)):
            label(g, title.upper(), font="small_bold", fg=C["muted"]).pack(anchor="w", pady=(6, 2))
            box = tk.Frame(g, bg=C["bg"])
            box.pack(anchor="w")
            items = [p for p in self.library["parts"] if p.get("kind") in kinds]
            for i, part in enumerate(items):
                PButton(box, part["title"], lambda pt=part: self.add_part(pt), kind="secondary", font="small_bold",
                        padx=8, pady=2).grid(row=i // cols, column=i % cols, sticky="we", padx=(0, 4), pady=2)

        # ---- wiring for whatever the code uses
        label(g, "My wiring", font="h3").pack(anchor="w", pady=(14, 2))
        self.wiring_note = label(g, "", font="small", fg=C["muted"], wraplength=330)
        self.wiring_note.pack(anchor="w")
        self.wiring_box = tk.Frame(g, bg=C["bg"])
        self.wiring_box.pack(fill="x", pady=(4, 0))

        # ---- projects
        label(g, "My projects", font="h3").pack(anchor="w", pady=(14, 0))
        new = card(g, padx=12, pady=10)
        new.pack(fill="x", pady=(6, 0))
        label(new, "New project name", font="small_bold", bg=C["panel"]).pack(anchor="w")
        row = tk.Frame(new, bg=C["panel"])
        row.pack(fill="x", pady=(4, 0))
        self.new_entry = entry(row, width=20, font="ui")
        self.new_entry.pack(side="left", fill="x", expand=True, ipady=2)
        self.new_entry.bind("<Return>", lambda e: self.new_project())
        PButton(row, "Create", self.new_project, kind="primary", font="small_bold", pady=3).pack(side="left", padx=(6, 0))
        self.new_msg = label(new, "", font="small", fg=C["err"], bg=C["panel"])
        self.new_msg.pack(anchor="w")
        self.list_frame = tk.Frame(g, bg=C["bg"])
        self.list_frame.pack(fill="x", pady=(8, 0))

        # ---- starter ideas
        label(g, "Need an idea?", font="h3").pack(anchor="w", pady=(14, 2))
        ideas = card(g, padx=8, pady=6)
        ideas.pack(fill="x")
        for idea in self.library["ideas"]:
            r = tk.Frame(ideas, bg=C["panel"], cursor="hand2", pady=3)
            r.pack(fill="x")
            t = label(r, idea["title"] + ("   ▶ needs parts" if idea.get("hardware") else ""), font="small_bold",
                      bg=C["panel"], fg=C["select"])
            t.pack(anchor="w")
            b = label(r, idea["blurb"], font="small", fg=C["muted"], bg=C["panel"], wraplength=320)
            b.pack(anchor="w")
            for w in (r, t, b):
                w.bind("<Button-1>", lambda e, i=idea: self.start_idea(i))

        rt = RichText(g)
        rt.pack(fill="x", pady=(16, 0))
        rt.render(CHEATSHEET)

        projects = self.student.list_projects()
        if projects:
            self.open_project(projects[0])
        else:
            self._create("my first project")

    # ---------------------------------------------------------------- basics
    def code_path(self) -> Path:
        return self.current

    def uses_gpio(self) -> bool:
        return True

    def reopen(self):
        """Back again (the screen was kept): the same project, a clear Output."""
        self.console.clear()
        self.console.set_status("")
        self._refresh_list()
        self._update_wiring()                  # only rebuilt if the parts changed

    def _welcome(self) -> None:
        if self.help_mode == "guided":
            self.coach.idle("Build anything! Add a part from the list below, start from an idea, or just type. "
                            "When something breaks I'll explain it, and if you get stuck I'll give you a nudge.")
        else:
            self.coach.idle("You're on your own here. If your code crashes, I'll still explain what went wrong.")

    def set_help_mode(self, mode: str) -> None:
        self.help_mode = mode
        self.student.profile["free_play_mode"] = mode
        self.student.save_profile()
        self.adapter.enabled = mode == "guided"
        self._welcome()

    def settings_changed(self, what: str) -> None:
        super().settings_changed(what)
        if what == "help":
            self.adapter.level = self.app.student.help_level

    def _changed(self):
        super()._changed()
        if self._wiring_job is not None:
            self.after_cancel(self._wiring_job)
        self._wiring_job = self.after(1500, self._update_wiring)     # after typing stops

    # ---------------------------------------------------------------- parts and wiring
    def add_part(self, part: dict) -> None:
        t = self.editor.text
        code = self.editor.get_code()
        pos = len(t.get("1.0", "insert"))
        new, tip, cursor = freeplay_add(code, part, pos)
        t.edit_separator()                 # one Ctrl+Z takes the whole part out again
        t.delete("1.0", "end")
        t.insert("1.0", new)
        t.edit_separator()
        self.editor.highlight()
        t.mark_set("insert", f"1.0+{cursor}c")
        t.see("insert")
        self.editor.focus()
        self._changed()
        if self._wiring_job is not None:       # the code shows first; the wiring card follows a moment later
            self.after_cancel(self._wiring_job)
        self._wiring_job = self.after(60, self._update_wiring)
        warns = freeplay_warnings(freeplay_parts(new))
        self.coach.message("info", f"Added: {part['title']}",
                           tip + ("\n\n⚠ " + "\n\n⚠ ".join(warns) if warns else "") +
                           "\n\nPress **Run** to try it" + (" in the Simulator first." if self.gpio and part.get("kind") != "software"
                                                            else "."))
        self.guide.scroll_to(self.coach)

    def park(self) -> None:
        super().park()
        if self._wiring_job is not None:
            self.after_cancel(self._wiring_job)
            self._wiring_job = None

    def _update_wiring(self, force: bool = False) -> None:
        """Show how to wire what the code uses (only re-built when the parts change)."""
        self._wiring_job = None
        if self.current is None:
            return
        code = self.editor.get_code()
        try:
            compile(code, "<free play>", "exec", dont_inherit=True)
            parts = freeplay_parts(code)
        except (SyntaxError, ValueError):
            if not force:
                return                 # half-typed code: keep the wiring as it was until it parses again
            parts = []
        sig = repr(parts)
        if sig == self._parts_sig and not force:
            return
        self._parts_sig = sig
        self.parts = parts
        was_open = self.wiring_card.is_open if self.wiring_card is not None else True
        if self.wiring_card is not None:
            self.wiring_card.destroy()
            self.wiring_card = None
        if not parts:
            self.wiring_note.configure(text="Your code doesn't use any GPIO parts yet. Add an LED or a button above, "
                                            "or write gpiozero code, and the wiring shows up here.")
            return
        self.wiring_note.configure(text="Made from your code. Take the blue HAT off before you change wires!")
        lesson = {"wiring": freeplay_rows(parts)}
        self.wiring_card = WiringCard(self.wiring_box, lesson, {"parts": []}, parts, open_=was_open,
                                      on_check=self.check_wiring)
        self.wiring_card.pack(fill="x")
        if self.board:
            self.board.set_parts(parts)
            if not self.board_shown:
                self.show_board()

    def check_wiring(self):
        if not self.parts or self.runner.running or self._busy:
            return
        where = "on the Simulator board" if self.mode == "sim" else "on your breadboard"
        self.run_special("wiring", wiring_check_program(self.parts), self.extra_env(),
                         f"▶ Checking your wiring {where}. Follow the instructions below.")

    def special_finished(self, kind: str, stdout: str, stderr: str):
        if kind != "wiring":
            return
        if self.wiring_card:
            self.wiring_card.mark_from_output(stdout)
        bad = [l for l in stdout.splitlines() if l.startswith("✗")]
        if bad:
            self.coach.message("warn", "Check those wires", "Some parts didn't respond:\n\n" +
                               "\n".join(f"- {l[2:]}" for l in bad) + "\n\n" +
                               HAT_FIX.replace("try again", "press **Check my wiring** again"))
        elif stdout.strip():
            self.coach.message("info", "Wiring check finished",
                               "Every button and sensor answered. Did each LED blink and the buzzer beep?")

    # ---------------------------------------------------------------- projects and ideas
    def _refresh_list(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        for p in self.student.list_projects():
            active = p == self.current
            row = tk.Frame(self.list_frame, bg=C["select"] if active else C["panel"], padx=10, pady=4,
                           relief="sunken" if active else "flat", bd=1, cursor="hand2")
            row.pack(fill="x", pady=1)
            fg = "#FFFFFF" if active else C["ink"]
            lb = label(row, p.stem.replace("_", " "), font="ui_bold" if active else "ui", bg=row.cget("bg"), fg=fg)
            lb.pack(side="left")
            label(row, p.name, font="code_ui", fg=fg if active else C["muted"], bg=row.cget("bg")).pack(side="right")
            for w in (row, lb):
                w.bind("<Button-1>", lambda e, path=p: self.open_project(path))

    def open_project(self, path: Path):
        self._abandon_run()                # the running program belongs to the old project
        if self.current:
            if self._save_job:
                self.after_cancel(self._save_job)
            self.save_now()
        self.current = path
        self.editor.set_code(path.read_text(encoding="utf-8"))
        self.file_lbl.configure(text=path.name)
        self.save_lbl.configure(text="Saved ✓")
        self.console.clear()
        self.console.set_status("")
        self._welcome()
        self._tips_shown = set()
        self.adapter.start_step(time.monotonic())
        self._refresh_list()
        self._update_wiring(force=True)

    def new_project(self):
        name = self.new_entry.get()
        msg = storage.validate_project_name(name)
        if not msg and self.student.project_path(name).exists():
            msg = "You already have a project with that name."
        self.new_msg.configure(text=msg or "")
        if msg:
            return
        self.new_entry.delete(0, "end")
        self._create(name)

    def _create(self, name: str, code: str | None = None):
        path = self.student.project_path(name)
        storage.write_text(path, code if code is not None else
                           f"# {name}\n# by {self.student.first_name}\n\nprint(\"Let's build something!\")\n")
        self.open_project(path)

    def start_idea(self, idea: dict) -> None:
        """A new project from a starter idea (never over the top of an existing one)."""
        base, n = idea["title"].lower().replace("-", " "), 1
        name = base
        while self.student.project_path(name).exists():
            n += 1
            name = f"{base} {n}"
        self._create(name, f"# {idea['title']}: {idea['blurb']}\n" + idea["code"].lstrip("\n"))
        self.coach.message("info", f"Starter: {idea['title']}",
                           "Here's a working starter. Press **Run** to try it, then make it your own: change the "
                           "words, the timings, add a part." +
                           ("\n\nIt uses hardware: see **My wiring** below for how to hook it up, and try it in the "
                            "**Simulator** first." if idea.get("hardware") else ""))

    # ---------------------------------------------------------------- after a run: the guide
    def after_run(self, code, err, crashed, stdout):
        now = time.monotonic()
        self._update_wiring()
        guided = self.help_mode == "guided"
        if err is not None:
            d = self.app.engine.diagnose(err)
            self.editor.mark_error_line(d.line)
            self.coach.diagnosis(d, self.app.student.help_level)
            self.coach.set_hints(d.hints, None)
            if guided:
                offer = self.adapter.after_run(now, False, d.entry_id)
                if offer is not None:
                    self.coach.offer(offer, self._offer_action)
            self.guide.scroll_to(self.coach)
            return
        self.adapter.after_run(now, True)
        self.adapter.start_step(now)       # it works again: a fresh start for the "stuck" counters
        if not guided:
            self.coach.message("ok", "It ran!", "No errors.")
            self.coach.set_hints([], None)
            return
        notes = ["No errors."]
        warns = freeplay_warnings(self.parts)
        if warns:
            notes += [f"⚠ {w}" for w in warns]
        elif self.parts and self.mode == "sim":
            notes.append(f"Your program uses {len(self.parts)} GPIO part{'s' if len(self.parts) != 1 else ''}. "
                         "When it works on the Simulator, wire it up (see **My wiring**) and switch to **Real Pi**.")
        tips = [t for t in review(code, max_tips=3) if t.title not in self._tips_shown]
        if tips:
            t = tips[0]
            self._tips_shown.add(t.title)
            notes.append(f"**Idea to level up: {t.title}** ({t.idea}). {t.text}")
        self.coach.message("ok", "It ran!", "\n\n".join(notes))
        self.coach.set_hints([], None)

    def _offer_action(self, action: str) -> None:
        self.coach.clear_offer()
        if action == "hint" and self.coach.hints and self.coach.shown < len(self.coach.hints):
            self.coach._hint()

    def tour_steps(self):
        return [
            {"widget": self.mode_choice, "side": "right", "title": "Your sandbox",
             "text": "No steps here. Choose **Guide me** for tips and nudges, or **On my own**."},
            {"widget": self.editor, "side": "inside", "title": "Build anything",
             "text": "Type your own code, add a part from the list on the left, or start from an idea."},
            {"widget": self.coach, "side": "right", "title": "The Coach is still here",
             "text": "If your code crashes, the Coach explains the error and offers hints."},
        ]


FreeBuildWorkspace = FreePlayWorkspace        # the old name
