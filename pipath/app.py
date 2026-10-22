"""PiPath main window: screen routing, activity states, and wiping the session."""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

from . import storage
from .content import Catalog, load_config
from .hints import HintEngine
from .ui.home import HomeScreen
from .ui.onboarding import ProfileScreen, SetupScreen, WelcomeScreen
from .ui.settings import SettingsDialog
from .ui.theme import C, setup_fonts, CODE_SIZE
from .ui.widgets import install_wheel
from .ui.workspace import FreePlayWorkspace, LessonWorkspace


class PiPathApp(tk.Tk):
    def __init__(self, scale: float = 1.0):
        super().__init__(className="PiPath")
        self.settings = load_config()
        self.catalog = Catalog()
        self._engine: HintEngine | None = None
        self.student: storage.Student | None = None
        self.screen: tk.Frame | None = None
        self.pending_profile: dict | None = None     # a new profile between "New student(s)" and "Set up"
        self._settings: SettingsDialog | None = None
        # Kept between visits, because building them is the slowest thing on a Pi 3B:
        self._home: HomeScreen | None = None
        self._lesson_ws: LessonWorkspace | None = None     # re-used for every activity
        self._free_ws: FreePlayWorkspace | None = None

        self.title(self.settings["app_name"])
        self.configure(bg=C["bg"])
        setup_fonts(self, scale)
        self.minsize(1024, 640)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(1366, sw - 40), min(800, sh - 80)
        self.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")
        if sw <= 1440:
            try:
                self.attributes("-zoomed", True)
            except tk.TclError:
                pass
        self.option_add("*Entry.relief", "flat")
        for key, value in (("background", C["bg"]), ("troughColor", "#DFDFDF"), ("activeBackground", C["face_hi"]),
                           ("relief", "raised"), ("borderWidth", 2), ("elementBorderWidth", 2),
                           ("highlightThickness", 0), ("width", 16)):
            self.option_add(f"*Scrollbar.{key}", value)    # chunky grey Windows 95 scrollbars
        install_wheel(self)                    # the mouse wheel / trackpad scrolls whatever is under it
        self.protocol("WM_DELETE_WINDOW", self.quit_app)
        self.show("welcome")

    @property
    def engine(self) -> HintEngine:
        """The Coach's error database, loaded the first time a program needs explaining."""
        if self._engine is None:
            self._engine = HintEngine()
        return self._engine

    # ------------------------------------------------------------------ routing
    def _kept(self) -> list:
        return [s for s in (self._home, self._lesson_ws, self._free_ws) if s is not None]

    def _swap(self, screen: tk.Frame) -> None:
        old = self.screen
        if old is not None and old is not screen:
            if old in self._kept():
                old.hide()            # kept for next time
            else:
                old.destroy()
        self.screen = screen
        screen.pack(fill="both", expand=True)
        if hasattr(screen, "on_show"):
            screen.on_show()

    def forget_screens(self) -> None:
        """Another student means the kept screens are made again next time."""
        kept = self._kept()
        self._home = self._lesson_ws = self._free_ws = None
        for s in kept:
            if s is not self.screen:
                s.destroy()           # the one on show goes at the next _swap

    def show(self, name: str) -> None:
        if name == "home":
            if self._home is None:
                self._home = HomeScreen(self)
            else:
                self._home.refresh()
            self._swap(self._home)
            return
        screens = {"welcome": WelcomeScreen, "profile": ProfileScreen, "setup": SetupScreen}
        self._swap(screens[name](self))

    def login(self, s: storage.Student) -> None:
        self.forget_screens()
        self.pending_profile = None
        self.student = s
        storage.touch_student(s)
        size = s.profile.get("code_size")
        if not (isinstance(size, int) and 9 <= size <= 26):
            size = CODE_SIZE["value"]          # not the last student's size
        tkfont.nametofont("code").configure(size=size)
        self.show("home")

    def logout(self) -> None:
        self.close_settings()
        self.forget_screens()
        self.student = None
        self.show("welcome")

    # ------------------------------------------------------------------ settings (the cog)
    def open_settings(self, tab: str = "help") -> None:
        if self.student is None:
            tab = "data"                       # before anyone logs in: only Save data
        self.end_tour()                        # a tour bubble can't sit on top of the dialog
        if self._settings is not None and self._settings.winfo_exists():
            self._settings.show_tab(tab)
            self._settings.lift()
            return
        self._settings = SettingsDialog(self, tab)

    def end_tour(self) -> None:
        tour = getattr(self.screen, "_tour", None)
        if tour is not None:
            tour.finish()

    def busy_with_dialog(self) -> bool:
        """Settings is open: keys like F5 shouldn't reach the screen behind."""
        guide = getattr(self.screen, "wiring_walkthrough", None)
        return ((self._settings is not None and self._settings.winfo_exists())
                or (guide is not None and guide.winfo_exists()))

    def close_settings(self) -> None:
        if self._settings is not None and self._settings.winfo_exists():
            self._settings.close()
        self._settings = None
        if self.screen is not None and hasattr(self.screen, "_ensure_wiring_gate"):
            self.screen._ensure_wiring_gate()

    def settings_changed(self, what: str) -> None:
        """A setting changed: every kept screen updates itself (help, show, names, hardware, text)."""
        for screen in dict.fromkeys(self._kept() + ([self.screen] if self.screen is not None else [])):
            if hasattr(screen, "settings_changed") and screen.winfo_exists():
                screen.settings_changed(what)

    def open_lesson(self, lesson_id: str, tour: bool = False) -> None:
        if self._lesson_ws is None:
            self._lesson_ws = LessonWorkspace(self, lesson_id, tour=tour)
        else:
            self._lesson_ws.load(lesson_id, tour=tour)
        self._swap(self._lesson_ws)

    def open_free_play(self) -> None:
        if self._free_ws is None:
            self._free_ws = FreePlayWorkspace(self)
        else:
            self._free_ws.reopen()
        self._swap(self._free_ws)

    open_free_build = open_free_play        # the old name

    def quit_app(self) -> None:
        screens = self._kept() + ([self.screen] if self.screen is not None else [])
        self._home = self._lesson_ws = self._free_ws = self.screen = None
        for s in dict.fromkeys(screens):      # each once
            s.destroy()
        self.destroy()

    # ------------------------------------------------------------------ activity state
    def project_state(self, p: dict) -> str:
        """planned | ready | in_progress | complete. Nothing is locked: students choose freely."""
        if p.get("status") != "ready":
            return "planned"
        status = self.student.lesson_status(p["id"])
        return status if status in ("complete", "in_progress") else "ready"

    # ------------------------------------------------------------------ wipe the session
    def wipe_session(self) -> None:
        """Delete every student's save data on this Pi (Settings > Save data), ready for a new group."""
        self.close_settings()
        if self.student is not None:
            self.logout()                      # stops any running program and drops the kept screens
        storage.wipe_all()
        self.pending_profile = None
        self.show("welcome")                   # without the old names on it
