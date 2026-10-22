"""Drive the real app under a virtual screen and save screenshots of each main screen.

    xvfb-run -s "-screen 0 1366x768x24" python3 tests/gui_smoke.py /tmp/shots
    PIPATH_SMOKE_SIZE=1024x640 xvfb-run -s "-screen 0 1024x640x24" python3 tests/gui_smoke.py /tmp/small

Not part of the unittest suite (needs Tk, Xvfb and ImageMagick's `import`).
Each scene is (name, action): the action runs, the app settles, then a screenshot is taken.
A crash in any action fails the run with a traceback.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import tkinter as tk
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["PIPATH_HOME"] = tempfile.mkdtemp(prefix="pipath_smoke_")
os.environ.setdefault("PIPATH_FORCE_SIM", "1")
os.environ["PIPATH_DOWNLOADS"] = tempfile.mkdtemp(prefix="pipath_downloads_")

from pipath import storage  # noqa: E402
from pipath.app import PiPathApp
from pipath.ui.widgets import PButton, PopupMenu, about_box  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "shots")
OUT.mkdir(parents=True, exist_ok=True)
SETTLE_MS = 900


def type_into(entry, text):
    entry.delete(0, "end")
    entry.insert(0, text)


def find(widget, cls, text=None):
    """The first widget of a class (and with this text) inside widget."""
    for w in widget.winfo_children():
        if isinstance(w, cls) and (text is None or str(w.cget("text")) == text):
            return w
        found = find(w, cls, text)
        if found is not None:
            return found
    return None


def click(widget, text):
    button = find(widget, PButton, text)
    assert button is not None and button.enabled, f"no enabled button {text!r}"
    button.command()


def check_wheel(app, canvas, over, *events, moves=True):
    """Scroll like a web page: with the mouse over `over` (anywhere on the screen), the wheel moves
    `canvas` (or, moves=False, leaves it alone: the editor scrolls itself)."""
    x, y = over.winfo_rootx() + 20, over.winfo_rooty() + 20
    app.event_generate("<Motion>", warp=True, x=x - app.winfo_rootx(), y=y - app.winfo_rooty())
    app.update()
    for seq, kw in events:
        before = canvas.yview()[0]
        over.event_generate(seq, x=5, y=5, rootx=x, rooty=y, **kw)
        app.update()
        moved = canvas.yview()[0] != before
        assert moved == moves, f"{seq} {kw} over {over.winfo_class()}: moved={moved}"
    canvas.yview_moveto(0)


def check_copy():
    assert list(Path(os.environ["PIPATH_DOWNLOADS"]).glob("PiPath_save_*.zip")), "no copy in Downloads"


def check_wiped():
    assert storage.list_students() == [], "students left after the wipe"
    assert not (storage.APP_HOME / "students").exists()


def scenes(app):
    def profile():
        app.show("profile")
        type_into(app.screen.entries["first_name"], "Sam")
        app.screen._add_name("Alex")
        type_into(app.screen.entries["school"], "Bayside Secondary College")

    def submit():
        app.screen.submit()           # -> step 2: help level + what to show

    def setup_choose():
        app.screen.level.set("moderate")

    def setup_finish():
        app.screen.finish()

    def settings(tab):
        def go():
            app.open_settings(tab)
        return go

    def close_settings():
        app.close_settings()

    def slide_distance(cm):
        def go():
            app.screen._board_distance(26, cm)
            app.screen.board.set_distance(26, cm)
        return go

    def duplicate():
        app.show("profile")
        type_into(app.screen.entries["first_name"], "sam")
        app.screen._add_name("alex")
        type_into(app.screen.entries["school"], "bayside secondary college")
        app.screen.submit()

    def welcome_back():
        app.logout()

    def login_again():
        app.login(storage.list_students()[0])

    def filter_advanced():
        app.screen.set_filter("advanced")

    def open_lesson(lid):
        def go():
            app.screen.set_filter("all") if hasattr(app.screen, "set_filter") else None
            app.open_lesson(lid)
        return go

    def start_lesson():
        app.screen.start_lesson()

    def press_run():
        app.screen.run()

    def free_build():
        app.open_free_build()

    def skip_tour():
        offer = getattr(app.screen, "_tour_offer", None)
        if offer is not None and offer.winfo_exists():
            offer.destroy()
        app.screen.tour_done()

    def set_code(code):
        def go():
            app.screen.editor.set_code(code)
        return go

    def press(pin):
        def go():
            app.screen._board_press(pin)
        return go

    def release(pin):
        def go():
            app.screen._board_release(pin)
        return go

    def tick_confirms():
        for i, c in enumerate(app.screen.steps[app.screen.step_i]["checks"]):
            if c["type"] == "confirm":
                app.screen._toggle_confirm(i)

    def stop():
        app.screen.stop()

    def goal():
        app.screen.watch_goal()

    def to_step(i):
        def go():
            app.screen.enter_step(i)
        return go

    def check_wiring():
        app.screen.check_wiring()

    def set_level(level):
        def go():
            if hasattr(app.screen, "set_level"):
                app.screen.set_level(level)
            else:
                while app.screen.level != level:
                    app.screen.cycle_level()
        return go

    return [
        ("01_welcome_first_run", lambda: None),
        ("02_profile", profile),
        ("03_setup", submit),
        ("03b_setup_moderate", setup_choose),
        ("03c_activities", setup_finish),
        ("04_profile_duplicate", duplicate),
        ("05_welcome_back", welcome_back),
        ("06_activities_returning", login_again),
        ("07_filter_advanced", filter_advanced),
        ("07b_settings_help", settings("help")),
        ("07c_settings_students", settings("students")),
        ("07d_settings_hardware", lambda: (close_settings(), settings("hardware")())),
        ("07e_settings_closed", close_settings),
        ("08_s1_intro", open_lesson("s1_hello")),
        ("09_s1_tour_offer", start_lesson),
        ("10_s1_run", press_run),
        ("11_free_build", free_build),
        ("12_free_build_gpio", lambda: (set_code("from gpiozero import LED, Button\nfrom signal import pause\n"
                                                 "light = LED(17)\nbutton = Button(23)\n"
                                                 "button.when_pressed = light.toggle\npause()\n")(), press_run())),
        ("13_free_build_pressed", press(23)),
        ("14_e1_intro", lambda: (release(23)(), stop(), open_lesson("e1_lightswitch")())),
        ("15_e1_step1", lambda: (start_lesson(), skip_tour())),
        ("16_e1_step1_ran", press_run),
        ("17_e1_step3_running", lambda: (to_step(2)(), app.screen.editor.set_code(
            app.screen.steps[2]["starter"].replace("___", "light.off")), press_run())),
        ("18_e1_step3_pressed", press(23)),
        ("19_e1_step3_stopped", lambda: (release(23)(), stop())),
        ("20_e1_step3_ticked", tick_confirms),
        ("21_e3_wiring", lambda: open_lesson("e3_simon")()),
        ("22_e4_board", lambda: (open_lesson("e4_dice")(), start_lesson())),
        ("23_a1_activities", lambda: (app.show("home"), app.screen.set_filter("advanced"))),
        ("24_a1_step1", lambda: (open_lesson("a1_traffic")(), start_lesson())),
        ("25_a1_header_map", lambda: app.screen.guide.canvas.yview_moveto(0.33)),
        ("26_a1_step2_goal", lambda: (to_step(1)(), goal()), 4200),
        ("27_a3_ultrasonic", lambda: (stop(), open_lesson("a3_alarm")(), start_lesson(), to_step(2)(),
                                      app.screen.editor.set_code(app.screen.steps[2]["starter"].replace("___", "clear")),
                                      press_run()), 1500),
        ("28_a3_close", slide_distance(15), 1200),
        ("28b_a3_cog_in_lesson", settings("help")),
        ("29_a3_checked", lambda: (close_settings(), slide_distance(90)(), stop()), 2500),
        ("30_camera_activities", lambda: (app.show("home"), app.screen.set_filter("camera"))),
        ("31_c1_photo", lambda: (open_lesson("c1_photobooth")(), start_lesson(), app.screen.editor.set_code(
            app.screen.steps[0]["starter"].replace("___", "me")), press_run()), 2500),
        ("32_c2_grid_goal", lambda: (open_lesson("c2_teachable")(), start_lesson(), to_step(1)(),
                                     app.screen._pick_object("box"), goal()), 6500),
        ("33_s2_goal_typed", lambda: (stop(), open_lesson("s2_pibot")(), start_lesson(), skip_tour(), to_step(3)(),
                                      goal()), 4500),
        ("34_level_advanced", lambda: (app.show("home"), set_level("advanced")())),
        ("35_a2_advanced_step", lambda: (open_lesson("a2_reaction")(), start_lesson())),
        ("36_a2_full_text", lambda: app.screen._toggle_explanation()),
        ("37_a2_skipped", lambda: app.screen.skip_step()),
        ("38_level_moderate", lambda: set_level("moderate")()),
        ("39_computer_tier", lambda: (app.show("home"), app.screen.set_filter("computer"))),
        ("40_p1_live_lights_goal", lambda: (open_lesson("p1_pihealth")(), start_lesson(), to_step(5)(), goal()), 4500),
        ("41_p2_binary_clock", lambda: (stop(), open_lesson("p2_binaryclock")(), start_lesson(), to_step(4)(),
                                        goal()), 3500),
        ("42_p3_dice_dj_goal", lambda: (stop(), open_lesson("p3_dicedj")(), start_lesson(), to_step(4)(),
                                        goal()), 3500),
        ("43_p4_doorbell_goal", lambda: (stop(), open_lesson("p4_doorbell")(), start_lesson(), to_step(5)(),
                                         goal()), 4000),
        ("44_hardware_filter", lambda: (stop(), app.show("home"), app.screen.set_filter("hardware"))),
        ("45_lab_new", lambda: app.screen.canvas.yview_moveto(0.55)),
        ("46_parking_goal", lambda: (open_lesson("e5_parking")(), start_lesson(), to_step(5)(), goal()), 4500),
        ("47_menu_edit", lambda: (stop(), app.screen.menubar.winfo_children()[1].event_generate("<ButtonPress-1>")), 800),
        ("48_about", lambda: (PopupMenu.of(app).hide(), about_box(app))),
        ("49_advanced_intro", lambda: (app._about.destroy(), app.show("home"), set_level("advanced")(),
                                       open_lesson("e6_whackamole")())),
        ("50_advanced_error", lambda: (app.screen.jump_to_challenge(), set_code("score = 0\ndef hit():\n    score += 1\nhit()\n")(),
                                       press_run()), 2500),
        ("51_code_review", lambda: (set_code("from gpiozero import LED\nfrom time import sleep\nled = LED(17)\n"
                                             + "led.on()\nsleep(0.3)\nled.off()\nsleep(0.3)\n" * 3
                                             + "q = int(input('How many? '))\n")(), app.screen.review_code())),
        ("52_level_up_outro", lambda: (app.student.mark_complete("e6_whackamole"), app.screen.show_outro())),
        ("53_morse_goal", lambda: (open_lesson("e7_morse")(), start_lesson(), to_step(2)(), goal()), 5000),
        ("54_nudge_first", lambda: (stop(), app.show("home"), set_level("beginner")(), open_lesson("s3_guess")(),
                                    start_lesson(), to_step(0)(), set_code("import random\nif True\n    print(1)\n")(),
                                    press_run()), 1500),
        ("55_nudge_same_error", press_run, 1500),
        ("56_nudge_hint", lambda: app.screen._offer_action("hint")),
        ("57_level_suggestion", lambda: (setattr(app.screen.adapter, "history",
                                                 [{"first_try": True, "failed": 0, "hints": 0, "secs": 40}] * 2),
                                         setattr(app.screen.adapter, "cooldown", 0),
                                         open_lesson("s1_hello")(), start_lesson(), skip_tour(), to_step(2)(),
                                         setattr(app.screen.adapter, "history",
                                                 [{"first_try": True, "failed": 0, "hints": 0, "secs": 40}] * 2),
                                         set_code(app.screen.steps[2]["demo"])(), press_run()), 2500),
        ("59_free_play_first_box", lambda: (stop(), app.show("home"), app.screen.set_filter("all"))),
        ("60_free_play", lambda: free_build()),
        ("61_add_led", lambda: app.screen.add_part(next(p for p in app.screen.library["parts"] if p["id"] == "led"))),
        ("62_add_button", lambda: app.screen.add_part(next(p for p in app.screen.library["parts"] if p["id"] == "button"))),
        ("63_wiring", lambda: app.screen.guide.scroll_to(app.screen.wiring_box)),
        ("64_free_error", lambda: (set_code("from gpiozero import LED\nled = LED(17)\nled.on(\n")(), press_run()), 1500),
        ("65_free_nudge", press_run, 1500),
        ("66_idea", lambda: app.screen.start_idea(next(i for i in app.screen.library["ideas"] if i["id"] == "disco"))),
        ("67_idea_run", press_run, 2500),
        ("68_done", lambda: (stop(), app.show("home"))),
        ("68b_curriculum_in_lesson", lambda: (open_lesson("e5_parking")(), app.open_settings("curriculum"))),
        ("68d_wheel", lambda: (app.close_settings(), app.show("home"), app.update(),
                               check_wheel(app, app.screen.canvas, app.screen.canvas, ("<Button-5>", {}),
                                           ("<MouseWheel>", {"delta": -3}), ("<MouseWheel>", {"delta": 120})),
                               check_wheel(app, app.screen.canvas, app.screen.hello, ("<Button-5>", {}),
                                           ("<MouseWheel>", {"delta": -3})),
                               set_level("moderate")(), open_lesson("a1_traffic")(), app.update(),
                               check_wheel(app, app.screen.guide.canvas, app.screen.guide.body.winfo_children()[0],
                                           ("<Button-5>", {}), ("<MouseWheel>", {"delta": -2})),
                               check_wheel(app, app.screen.guide.canvas, app.screen.board,
                                           ("<Button-5>", {}), ("<MouseWheel>", {"delta": -2})),
                               check_wheel(app, app.screen.guide.canvas, app.screen.editor.text,
                                           ("<Button-5>", {}), moves=False))),
        ("68c_curriculum_home", lambda: (app.close_settings(), app.show("home"), app.open_settings("curriculum"))),
        ("69_save_data", lambda: app.open_settings("data")),
        ("70_save_copy", lambda: (click(app._settings, "Save a copy"), check_copy())),
        ("71_wipe_typed", lambda: type_into(find(app._settings, tk.Entry), "wipe")),
        ("72_wiped_welcome", lambda: (click(app._settings, "Wipe session"), check_wiped()), 1500),
        ("73_welcome_save_data", lambda: app.open_settings()),
        ("74_closed", lambda: app.close_settings()),
    ]


def main():
    app = PiPathApp()
    app.geometry(os.environ.get("PIPATH_SMOKE_SIZE", "1366x768") + "+0+0")
    todo = list(scenes(app))
    failures = []

    def shoot(name):
        app.update()
        subprocess.run(["import", "-window", "root", str(OUT / f"{name}.png")], check=False)
        print("shot", name, flush=True)

    def step():
        if not todo:
            app.after(100, app.quit_app)
            return
        name, action, *settle = todo.pop(0)
        try:
            action()
        except Exception:
            failures.append(name)
            traceback.print_exc()
        app.after(settle[0] if settle else SETTLE_MS, lambda: (shoot(name), app.after(50, step)))

    app.after(600, step)
    app.mainloop()
    if failures:
        sys.exit(f"Scenes failed: {failures}")


if __name__ == "__main__":
    main()
