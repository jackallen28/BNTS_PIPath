"""The Settings window, opened with the cog on any screen: a Windows 95 style tabbed dialog.

Tabs: Help (how much help), Show (which activities the picker shows), Students (the names),
Hardware (Simulator or Real Pi, camera), Text size, Curriculum (each activity's Victorian Curriculum
links), Save data (save a copy to Downloads, wipe the
session). Changes apply straight away; the app tells every kept screen (app.settings_changed).
Before anyone has logged in (the welcome screen) only Save data is shown.
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

from .. import storage
from ..gpio import CAMERA_KINDS, guess_camera, on_real_pi
from .onboarding import level_options, show_options
from .theme import C
from .widgets import ChoiceList, PButton, RichText, ScrollFrame, TitleBar, entry, label

TABS = [("help", "Help"), ("show", "Show"), ("students", "Students"), ("hardware", "Hardware"),
        ("text", "Text size"), ("curriculum", "Curriculum"), ("data", "Save data")]


class SettingsDialog(tk.Frame):
    def __init__(self, app, tab: str = "help"):
        super().__init__(app, bg=C["bg"], relief="raised", bd=2, highlightthickness=1,
                         highlightbackground=C["dark"], highlightcolor=C["dark"])
        self.app = app
        TitleBar(self, "Settings", height=22, close=self.close).pack(fill="x", padx=2, pady=(2, 0))
        tabs = tk.Frame(self, bg=C["bg"], padx=10)
        tabs.pack(fill="x", pady=(8, 0))
        self.tabs: dict[str, tk.Label] = {}
        for key, text in TABS if app.student is not None else [t for t in TABS if t[0] == "data"]:
            t = tk.Label(tabs, text=f"  {text}  ", font="small_bold", bg=C["bg"], fg=C["ink"], relief="raised",
                         bd=2, padx=4, pady=3, cursor="hand2")
            t.pack(side="left")
            t.bind("<Button-1>", lambda e, k=key: self.show_tab(k))
            self.tabs[key] = t
        self.page = tk.Frame(self, bg=C["bg"], relief="raised", bd=2, padx=18, pady=14, width=560, height=330)
        self.page.pack(fill="both", expand=True, padx=10)
        self.page.pack_propagate(False)
        foot = tk.Frame(self, bg=C["bg"], padx=10, pady=10)
        foot.pack(fill="x")
        label(foot, "Changes are saved straight away.", font="small", fg=C["muted"]).pack(side="left")
        PButton(foot, "Done", self.close, kind="primary").pack(side="right")
        self.place(relx=.5, rely=.5, anchor="center")
        self.lift()
        self.bind_all("<Escape>", lambda e: self.close())
        self.show_tab(tab)
        try:
            self.grab_set()           # like a real dialog: the screen behind waits until you close it
        except tk.TclError:
            pass

    def close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.unbind_all("<Escape>")
        self.destroy()
        self.app._settings = None
        screen = self.app.screen
        if screen is not None and hasattr(screen, "_ensure_wiring_gate"):
            screen._ensure_wiring_gate()

    # ---------------------------------------------------------------- tabs
    def show_tab(self, key: str) -> None:
        if key not in self.tabs:
            key = next(iter(self.tabs))
        for k, t in self.tabs.items():
            on = k == key
            t.configure(relief="sunken" if on else "raised", bg="#FFFFFF" if on else C["bg"],
                        fg=C["purple"] if on else C["ink"])
        for w in self.page.winfo_children():
            w.destroy()
        getattr(self, f"_tab_{key}")(self.page)

    def _tab_help(self, page) -> None:
        student = self.app.student
        label(page, "How much help do you want?", font="h3").pack(anchor="w")
        label(page, "Change it whenever you like. Stars still count the hints you open.", font="small",
              fg=C["muted"]).pack(anchor="w", pady=(0, 8))
        ChoiceList(page, level_options(), student.help_level, wrap=440,
                   on_change=lambda k: (student.set_help_level(k), self.app.settings_changed("help"))).pack(anchor="w")
        self.adaptive = tk.BooleanVar(value=student.profile.get("adaptive", True) is not False)
        tk.Checkbutton(page, text="Adaptive help: nudge me when I'm stuck, and suggest a new level when it's too "
                                  "easy or too hard", variable=self.adaptive, command=self._set_adaptive,
                       font="small", bg=C["bg"], activebackground=C["bg"], selectcolor="#FFFFFF",
                       wraplength=440, justify="left", anchor="w").pack(anchor="w", pady=(10, 0))

    def _set_adaptive(self) -> None:
        student = self.app.student
        student.profile["adaptive"] = bool(self.adaptive.get())
        student.save_profile()
        self.app.settings_changed("help")

    def _tab_show(self, page) -> None:
        student = self.app.student
        label(page, "What do you want to see on the activity picker?", font="h3").pack(anchor="w")
        label(page, "Everything stays open. This just keeps the list short.", font="small",
              fg=C["muted"]).pack(anchor="w", pady=(0, 8))
        ChoiceList(page, show_options(self.app.catalog), student.show, columns=2, wrap=200,
                   on_change=lambda k: (student.set_show(k), self.app.settings_changed("show"))).pack(anchor="w")

    def _tab_students(self, page) -> None:
        student = self.app.student
        label(page, "Who's working on this Pi?", font="h3").pack(anchor="w")
        label(page, f"School: {student.profile.get('school', '')}", font="small", fg=C["muted"]).pack(anchor="w",
                                                                                                    pady=(0, 8))
        self.name_entries = []
        box = tk.Frame(page, bg=C["bg"])
        box.pack(anchor="w")
        names = student.names + [""] * (storage.MAX_NAMES - len(student.names))
        for i, name in enumerate(names):
            row = tk.Frame(box, bg=C["bg"])
            row.pack(anchor="w", pady=2)
            label(row, f"Student {i + 1}", font="small_bold", width=10).pack(side="left")
            e = entry(row, width=22, font="ui")
            e.insert(0, name)
            e.pack(side="left", ipady=2)
            self.name_entries.append(e)
        self.names_msg = label(page, "Add a name to work together, or clear a box to take a name off.",
                               font="small", fg=C["muted"], wraplength=480)
        self.names_msg.pack(anchor="w", pady=(8, 6))
        PButton(page, "Save names", self._save_names, kind="secondary", font="small_bold", pady=3).pack(anchor="w")

    def _save_names(self) -> None:
        student = self.app.student
        names = [e.get() for e in self.name_entries]
        errors = storage.validate_names(names, student.profile.get("school", "x"))
        filled = [n.strip() for n in names if n.strip()]
        other = storage.find_student(filled, student.profile.get("school", "")) if not errors else None
        if other is not None and other.slug != student.slug:
            errors["name0"] = "Another profile on this Pi already has exactly those names."
        if errors:
            self.names_msg.configure(text="⚠ " + next(iter(errors.values())), fg=C["err"])
            return
        student.set_names(filled)
        self.names_msg.configure(text=f"✓ Saved: {student.first_name}", fg=C["ok"])
        self.app.settings_changed("names")

    def _tab_hardware(self, page) -> None:
        state = storage.app_state()
        real_pi = on_real_pi()
        mode = state.get("gpio_mode", "real") if real_pi else "sim"
        label(page, "Run GPIO programs on", font="h3").pack(anchor="w")
        opts = [("sim", "Simulator", "The board on the screen is your hardware.")]
        if real_pi:
            opts.append(("real", "Real Pi", "Your program drives the real GPIO pins (through the blue HAT), live."))
        ChoiceList(page, opts, mode, columns=2, wrap=220, on_change=self._set_mode).pack(anchor="w", pady=(4, 2))
        if not real_pi:
            label(page, "Real Pi appears here when PiPath runs on a Raspberry Pi.", font="small",
                  fg=C["muted"]).pack(anchor="w", pady=(0, 8))
        label(page, "Camera", font="h3").pack(anchor="w")
        cam = state.get("camera") or guess_camera()      # what the activities use until one is chosen
        cams = [("sim", "Simulated", "Pretend pictures"), ("usb", "USB", "A USB webcam"),
                ("ribbon", "Ribbon", "Pi camera on the ribbon")]
        ChoiceList(page, cams, cam if cam in CAMERA_KINDS else "sim", columns=3, wrap=140,
                   on_change=self._set_camera).pack(anchor="w", pady=(4, 0))

    def _set_mode(self, mode: str) -> None:
        storage.set_app_state(gpio_mode=mode)
        self.app.settings_changed("hardware")

    def _set_camera(self, kind: str) -> None:
        storage.set_app_state(camera=kind)
        self.app.settings_changed("hardware")

    def _tab_text(self, page) -> None:
        label(page, "Code text size", font="h3").pack(anchor="w")
        label(page, "For the code and the Output. Saved for you.", font="small", fg=C["muted"]).pack(anchor="w",
                                                                                                  pady=(0, 10))
        row = tk.Frame(page, bg=C["bg"])
        row.pack(anchor="w")
        PButton(row, "A−  Smaller", lambda: self._zoom(-1), kind="secondary").pack(side="left")
        PButton(row, "A+  Bigger", lambda: self._zoom(1), kind="secondary").pack(side="left", padx=8)
        self.size_lbl = label(row, "", font="ui_bold")
        self.size_lbl.pack(side="left", padx=10)
        sample = tk.Label(page, text='print("Hello, Pi!")', font="code", bg=C["ed_bg"], fg=C["ed_fg"],
                          relief="sunken", bd=2, padx=10, pady=8, anchor="w")
        sample.pack(anchor="w", pady=(14, 0), fill="x")
        self._show_size()

    def _zoom(self, step: int) -> None:
        f = tkfont.nametofont("code")
        size = max(9, min(26, f.cget("size") + step))
        f.configure(size=size)
        self.app.student.profile["code_size"] = size
        self.app.student.save_profile()
        self.app.settings_changed("text")
        self._show_size()

    def _show_size(self) -> None:
        self.size_lbl.configure(text=f"{tkfont.nametofont('code').cget('size')} point")

    def _tab_curriculum(self, page) -> None:
        """Each activity's Victorian Curriculum Digital Technologies links (catalog.toml `curriculum`)."""
        label(page, "Curriculum links", font="h3").pack(anchor="w")
        label(page, "Victorian Curriculum Digital Technologies, Levels 9 and 10. Pick an activity.",
              font="small", fg=C["muted"]).pack(anchor="w", pady=(0, 6))
        projects = [p for p in self.app.catalog.projects if p.get("status") == "ready"]
        row = tk.Frame(page, bg=C["bg"])
        row.pack(fill="both", expand=True)
        lb = tk.Listbox(row, font="small", width=24, relief="sunken", bd=2, activestyle="none",
                        highlightthickness=0, exportselection=False, selectbackground=C["select"],
                        selectforeground="#FFFFFF")
        sb = tk.Scrollbar(row, orient="vertical", command=lb.yview, width=12)
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side="left", fill="y")
        sb.pack(side="left", fill="y")
        for p in projects:
            lb.insert("end", p["title"])
        box = ScrollFrame(row, bg="#FFFFFF", relief="sunken", bd=2)
        box.pack(side="left", fill="both", expand=True, padx=(8, 0))
        rt = RichText(box.body, bg="#FFFFFF", font="small")
        rt.tag_configure("b", font="small_bold")
        rt.pack(fill="x", padx=8, pady=6)

        def show(_e=None):
            sel = lb.curselection()
            if not sel:
                return
            p = projects[sel[0]]
            links = p.get("curriculum") or []
            rt.render(f"**{p['title']}**\n" + ("\n".join(f"- {line}" for line in links) if links
                                              else "No curriculum links for this activity yet."))
            box.to_top()

        lb.bind("<<ListboxSelect>>", show)
        here = getattr(self.app.screen, "project", None) or {}        # opened from an activity: start there
        start = next((i for i, p in enumerate(projects) if p["id"] == here.get("id")), 0)
        if projects:
            lb.selection_set(start)
            lb.see(start)
            show()

    def _tab_data(self, page) -> None:
        info = storage.wipe_summary()
        label(page, "Save data", font="h3").pack(anchor="w")
        n = info["students"]
        label(page, "Your work saves by itself. Pick your name next time to carry on where you left off. "
                    f"This Pi has {n} profile{'s' if n != 1 else ''} saved ({info['files']} files).",
              font="small", fg=C["muted"], wraplength=500).pack(anchor="w", pady=(0, 8))

        label(page, "Save a copy", font="ui_bold").pack(anchor="w")
        row = tk.Frame(page, bg=C["bg"])
        row.pack(anchor="w", fill="x", pady=(2, 0))
        PButton(row, "Save a copy", self._save_copy, kind="secondary", font="small_bold", pady=3).pack(side="left")
        self.copy_msg = label(row, f"A zip of everyone's work, in {storage.downloads_folder()}", font="small",
                              fg=C["muted"], wraplength=370)
        self.copy_msg.pack(side="left", padx=(10, 0))

        label(page, "Wipe session", font="ui_bold", fg=C["err"]).pack(anchor="w", pady=(16, 0))
        label(page, "For a new group: deletes every profile on this Pi, with all progress, code, photos and "
                    "projects. It can't be undone, so save a copy first if you want to keep it. The Pi's "
                    "settings (Simulator / Real Pi, camera) stay.", font="small", wraplength=500).pack(anchor="w")
        row = tk.Frame(page, bg=C["bg"])
        row.pack(anchor="w", pady=(6, 0))
        label(row, "Type WIPE to confirm:", font="small").pack(side="left")
        self.wipe_word = tk.StringVar()
        self.wipe_entry = entry(row, width=8, font="ui", textvariable=self.wipe_word)
        self.wipe_entry.pack(side="left", padx=6, ipady=1)
        self.wipe_btn = PButton(row, "Wipe session", self.app.wipe_session, kind="stop", font="small_bold", pady=3)
        self.wipe_btn.pack(side="left", padx=(6, 0))
        self.wipe_btn.set_enabled(False)
        self.wipe_word.trace_add("write", lambda *_: self.wipe_btn.set_enabled(
            self.wipe_word.get().strip().upper() == "WIPE"))
        if not n and not info["exports"]:
            self.wipe_entry.configure(state="disabled")

    def _save_copy(self) -> None:
        self.copy_msg.configure(text="Saving...", fg=C["muted"])
        self.copy_msg.update_idletasks()
        try:
            out = storage.save_copy(self.app.catalog.projects)
        except OSError as e:
            self.copy_msg.configure(text=f"⚠ Couldn't save the copy: {e.strerror or e}", fg=C["err"])
            return
        self.copy_msg.configure(text=f"✓ Saved {out}", fg=C["ok"])
