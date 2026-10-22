# PiPath: Python coding tutor for Raspberry Pi

Repository: `jackallen28/BNTS_PIPath`. Open all pull requests against `main` in this repository.
Use the existing task checkout; create a worktree only when the user explicitly requests one.

> This file is the brief for Claude Code. Read it fully before changing anything.
> It describes what PiPath is, what already exists, the rules to follow, the data
> formats, the full curriculum, and what's left to build.

---

## 1. What PiPath is

PiPath is a desktop app that runs on a student's Raspberry Pi. It works like a
tutor sitting beside them:

1. **Login:** welcome → pick your name, or create a profile: **first name(s) + school only**
   (up to 4 names when students share a Pi) → step 2: **how much help** and **what to show** →
   the **activity picker**. A **Settings cog** on every screen changes these (and names,
   hardware, text size) at any time. The workspace tour is *offered* (not forced) the first
   time a student reaches a step.
2. **Free choice:** every activity is open from day one, and students do as many or as few
   as they like, in any order. Tiers (Simple, Moderate, Pi & Computer, Advanced, Electronics Lab,
   Camera & AI)
   are a **guide**: a colour badge, a filter chip, and optional "Good to try first" tips.
   Nothing is locked, and **Free Play** (the sandbox, the first box on the picker) is always open.
3. **Help level, chosen by the student:** **Beginner** (full explanations, hints any time),
   **Moderate** (each activity's own gradual release) or **Advanced** (Year 9-10, "tutorial
   off": goal-first instructions, fewer hints, no tour, steps can be skipped). See §6.
4. **Step by step, one part at a time:** each activity starts with one part (an LED), tests
   each new part on its own (the button), then joins them up, step by step, to the finished
   project. Every step has instructions, starter code, a **checklist** that is checked
   automatically when the student presses Run (plus "I saw it happen" tick boxes for
   hardware), and a **Coach** that explains errors in plain English with tiered hints.
5. **Gradual release of responsibility:** early steps are *guided* (fill in the blanks,
   hints straight away). Later steps are *scaffolded*, then *brief* (just a goal, hints only
   after trying).
6. **Simulator or Real Pi (MakeCode-style):** GPIO and camera activities run on an on-screen
   board (the **Simulator**) or on the real pins and breadboard (**Real Pi**). **Watch the
   goal** plays the step's model answer on the board, so students see what *should* happen
   before they try it on real hardware. (Screen-only activities have it too: it types the
   demo's answers into the Output.)

**There is NO AI service in PiPath.** All help comes from a hand-written database of common
errors (`data/errors.toml`) and per-step hints written by the teacher. (The *Teachable
Machine* activity is machine learning the students write themselves: a nearest-neighbour
classifier over tiny greyscale grids. No model, library or internet.)

**Mouse wheel / trackpad:** scrolls like a web page. One app-wide handler (`widgets.install_wheel`)
looks under the mouse pointer for a Canvas marked with `widgets.wheel_target` (the activity picker,
every ScrollFrame); anywhere else (toolbar, board, titles) it scrolls the screen's `wheel_default`
(the cards, the instructions panel, the welcome list). The editor, Output and lists scroll themselves;
nothing behind an open Settings dialog scrolls. Handles Linux Button-4/5, Tk 8.6 macOS small
`<MouseWheel>` deltas, 120-per-notch deltas (Windows, Tk 9) and Tk 9's `<TouchpadScroll>` (newer Python
on a Mac). Don't add per-widget Enter/Leave wheel bindings.

**About box** (Help > About): developed by BNTS and reviewed by teachers, not hosted on AI, runs
locally on the Pi, aims to open up Python to every student by adapting to their needs.

**Look:** classic Windows 95/98 with the Banyule Nillumbik Tech School colours: the teal
(#008080) desktop, silver-grey (#C0C0C0) windows with two-level bevels, grey buttons with a black
ring for the default one, white sunken fields, purple→teal gradient title bars (✕ box on dialogs),
a File / Edit / Run / View / Help menu bar, Help > About PiPath, yellow tooltip-style tour
balloons, a Visual Basic 6 style white editor and an MS-DOS Prompt style Output. The school logo
sits in the top-left corner (`data/brand/`, made by `tools/make_logo_assets.py`). Colours and fonts
live in `ui/theme.py`; the retro pieces (TitleBar, MenuBar, PButton, CogButton, ChoiceList, window,
bevel, about_box) in `ui/widgets.py`. Keep new screens in this style.

**Year 9-10 coaching:** students who have used Python before choose **Advanced**. They get the
goal first, Python's real error message plus a technical explanation (`tech` in errors.toml), a
**code review** after each step (`pipath/review.py`: repeated code, magic numbers, names, input
validation, globals, bare except, test cases), **Jump to the challenge** on an activity's intro,
and **Level up** challenges in the outro. Each activity lists its Victorian Curriculum Digital
Technologies (Levels 9-10) links (`curriculum` in catalog.toml), shown in **Settings > Curriculum**
(a list of activities; opened from an activity, it starts on that one), not on the intro. Moderate students get the code
review and the deeper "Under the bonnet" explanation too.

**Adaptive scaffolding** (`pipath/adapt.py`, shown by the Coach as a yellow note with buttons):
on top of the chosen level, PiPath *offers* the right next thing. Stuck (the same error twice, a
check that keeps failing, 4+ failed runs, a quiet spell, no Run after 4 minutes) → a nudge with
"Show me a hint" / "Watch the goal" / "Show the full explanation", and hints unlock early at any
level. Flying (3 steps in a row first try, no hints) → "try a harder level?". Struggling (many
failed runs or hints over 3 steps) → "want a bit more help?". Each nudge once per step; a level
suggestion then waits 4 steps. History is saved in the profile (`adapt`); students can switch it
off in Settings (`adaptive`).

**Hardware safety:** classes use a **blue GPIO HAT**. Student-facing text always says: take the
blue HAT off before changing wires, put it back on after, and **never turn the Pi off** (they'd
lose their progress). `gpio.SAFETY` and `gpio.HAT_FIX` hold the wording.

Audience: secondary students (roughly Years 7–10) who are new to text-based coding.
The author is a teacher; content is aligned to Victorian Curriculum Digital
Technologies (general-purpose programming, algorithms, data, digital systems).

---

## 2. Target platform (design for this, test on this)

| Item | Target |
|---|---|
| Hardware | **Raspberry Pi 3 Model B**: 1 GB RAM, 4-core 1.2 GHz Cortex-A53 |
| OS | Latest **Raspberry Pi OS (Desktop)**: Trixie-based, Wayland (labwc) with XWayland |
| Python | System **Python 3.13** (code must also run on 3.11+) |
| GUI | **Tkinter / Tk 8.6** (preinstalled on Pi OS Desktop as `python3-tk`) |
| GPIO | **gpiozero** (preinstalled), using the **lgpio** pin factory; mock pins in the Simulator |
| Camera | **USB webcam** (UVC, e.g. DFRobot 720p) or **ribbon** (CSI) camera; optional |
| Screen | Usually 1920×1080 monitor or 1366×768 projector; min supported 1024×640 |
| Network | Assume **none**. Everything works offline. |

Performance budget on a Pi 3B: app start < 4 s; screen switch < 400 ms; Run
button to first output < 1 s; idle CPU ~0%. **Read `docs/perf.md` before touching the UI.**
In short: Tk widgets are the cost on a Pi, so screens are kept and re-used (the activity
picker, one activity workspace for every activity, Free Play), the step panel and checklist
rows are re-used from step to step, all `RichText` heights are measured in one shared layout
pass, and GPIO programs start in a spare runner process that already has gpiozero loaded.
Never re-highlight or re-render the whole UI on every keystroke (the editor debounces
highlighting by 150 ms). The board repaints only changed items; the shim reports pin states
only when they change. `tests/perf_probe.py` times the main interactions.

---

## 3. Rules for Claude Code

1. **Standard library only** (plus `gpiozero`, which ships with Pi OS). No pip installs,
   no PyQt, no web frameworks, no Electron. `tomllib` reads data files.
   The camera helper may *use* `picamera2`, `numpy` and `PIL` **when present** (they ship
   with Pi OS Desktop) but must always work without them (Simulator, V4L2, pure-Python PNG).
2. **Content is data, not code.** Lessons, the catalogue, hints, error messages, wiring and
   demos live in `data/*.toml`. A teacher must be able to add a lesson without touching Python.
3. **No AI, no network calls, no telemetry.** Student data stays on the Pi.
4. **Student-facing text:** plain English, short sentences, about Year 7 reading level,
   Australian spelling (colour, favourite, organise, recognise). Encouraging, never
   sarcastic. Errors are "clues", not "failures".
5. **No emoji in Tk widgets.** Tk 8.6 on Pi OS can't render colour emoji. Use BMP symbols
   that DejaVu Sans has: ✓ ✗ ○ ● ▶ ■ ◂ ▸ ▾ ★ ☆ ⚠ •
6. **No floating windows for UI.** Overlays (tour, tour offer, Settings) are frames
   drawn with `place()` inside the main window, so they behave the same on X11 and Wayland.
7. **Student code always runs in a separate process** (`pipath/runner.py`, always through
   `pipath/gpio_shim.py`, which reports pins, photos and `input()` waits), never `exec()`
   inside the app. The app must survive any student program.
8. **Every lesson step must have a model answer: its `demo`**, run by
   `tests/test_activities.py` (GPIO/camera steps in the Simulator with `demo_events`; all
   steps with `demo_input` typed in). It must pass the step's own checks. Every step also needs
   a goal for Advanced students: a `**Your task:**` / `**Goal:**` line, or a `goal` key.
9. **Build each activity one part at a time:** test a new part (LED, button, sensor,
   camera) on its own in a short step before a step joins it to the rest.
10. Keep `python3 -m unittest discover -s tests` green after every change.
11. Don't break the save format in `~/PiPath/`. If it must change, migrate old files.
    (Old profiles with a `class_code` still load and show it; profiles without `help_level`
    are Beginner.)
12. **Keep it quick on a Pi 3B** (`docs/perf.md`): don't make widgets on every step or Run
    (re-use them or draw on a Canvas), never call `update_idletasks()` per widget, and put
    slow imports in the spare runner's preload list (`Workspace.preload`).

---

## 4. What exists (v0.4)

Run it: `python3 main.py` (add `--scale 1.25` for big screens). Test: `python3 -m unittest discover -s tests`.

```
repo root
├── main.py                  entry point (checks Python ≥ 3.11)
├── CLAUDE.md                this file
├── README.md                teacher setup guide
├── install.sh               installs menu + desktop shortcut (+ Update PiPath) on a Pi
├── Install-PiPath.desktop   double-click installer: downloads + runs tools/install_pipath.sh
├── docs/pi-test-checklist.md  hardware test plan for a real Pi + breadboard + camera
├── docs/perf.md             what keeps PiPath quick on a Pi 3B, before/after timings, how to measure
├── data/
│   ├── config.toml          app name, Free Play's name, runaway limits, star thresholds
│   ├── freeplay.toml        Free Play's "Add a part" library and starter ideas
│   ├── catalog.toml         tiers + all activities (status ready | planned, try_first, gpio, camera)
│   ├── errors.toml          the Coach's knowledge (63 entries incl. GPIO + camera)
│   ├── demo_files/c2/examples.json   sample training data for Teachable Machine demos
│   └── lessons/
│       ├── s1_hello, s2_pibot, s3_guess        Simple (screen only)
│       ├── m1_quiz, m2_turtle, m3_tuckshop     Moderate (screen only; turtle opens its own window)
│       ├── a1_traffic, a2_reaction, a3_alarm   Advanced GPIO
│       ├── p1_pihealth, p2_binaryclock, p3_dicedj, p4_doorbell,
│       │   p5_focustimer, p6_controlpad                      Pi & Computer
│       ├── e1_lightswitch, e2_moodlamp, e3_simon, e4_dice,
│       │   e5_parking, e6_whackamole, e7_morse               Electronics Lab
│       └── c1_photobooth, c2_teachable          Camera & AI
│   ├── demo_files/p3/party/1.wav..6.wav  Dice DJ sounds (copied to the student's folder)
│   └── brand/               the school logo: original + corner / full sizes (RGBA PNG)
├── tools/make_logo_assets.py, make_party_sounds.py   remake the brand images (+ icon) / Dice DJ sounds
├── tools/install_pipath.sh  the installer / updater (download, install.sh, open PiPath)
├── pipath/
│   ├── app.py               main window, routing, activity states, wipe session
│   ├── content.py           loads config / catalogue / lessons / errors
│   ├── storage.py           profiles, progress, code files, app state, CSV export (atomic writes)
│   ├── levels.py            help levels (Beginner / Moderate / Advanced): hint rules, goal text, skip
│   ├── hints.py             Coach engine: precheck, gpio_lint, traceback parsing, matching, checks
│   ├── review.py            code review coach (ast): tips on how code is written, for Years 9-10
│   ├── adapt.py             adaptive scaffolding: nudges when stuck, level suggestions
│   ├── freeplay.py          Free Play logic: parts used by the code → wiring rows, pin clashes,
│   │                        "Add a part" (free pins, fresh names, imports at the top)
│   ├── runner.py            runs student code: live output, stdin, runaway detection, shim pipes,
│   │                        warm start (a spare shim process with gpiozero already imported)
│   ├── gpio.py              app-side GPIO: Pi detection, Simulator env, wiring parts, header map,
│   │                        demo event expansion, wiring-check program, camera guess
│   ├── gpio_shim.py         runs INSIDE the student process: mock/real pins, state + commands
│   ├── student_lib/
│   │   ├── pipath_camera.py   the students' camera helper (Simulated / USB via V4L2 / ribbon)
│   │   ├── pipath_computer.py cpu_temp / cpu_load / ram_used (from /sys, /proc), open_file /
│   │   │                      open_website (xdg-open), take_screenshot (grim), change_volume (wpctl),
│   │   │                      show_message; Watch the goal only prints what it would do
│   │   └── _headless_turtle.py stands in for turtle when there's no display (tests)
│   └── ui/
│       ├── theme.py         logo colours, named fonts (DejaVu fallbacks), tier colours, LOGO_SQUARES
│       ├── widgets.py       PButton, TitleBar, CogButton, ChoiceList, window, bevel, RichText
│       │                    (mini-markdown), ScrollFrame, PopupMenu, card, chip
│       ├── settings.py      Settings dialog (cog): Help · Show · Students · Hardware · Text size ·
│       │                    Curriculum (links per activity) · Save data (save a copy, wipe session)
│       ├── editor.py        code editor (undo groups, find/replace, go to line, brackets, smart paste)
│       ├── console.py       Output box + "type your answer" row (history, \r, live stderr)
│       ├── tour.py          coach-mark tour (place()-based overlay)
│       ├── onboarding.py    Welcome / profile picker, Create profile (names + school), Setup
│       │                    (help level + what to show)
│       ├── home.py          activity picker: help level, filter chips, cards drawn on one Canvas
│       ├── board.py         VirtualBoard: LEDs, RGB LEDs, buttons, buzzers, PIR, distance sensor
│       │                    (slider), camera panel, ● LIVE badge in Real Pi mode
│       ├── wiring.py        Wiring + Safety card with 40-pin header map and "Check my wiring"
│       └── workspace.py     LessonWorkspace (one, re-used for every activity) and FreePlayWorkspace (the sandbox)
└── tests/
    ├── test_hints.py        real broken programs → Coach entry; blanks precheck
    ├── test_storage.py      profiles: names + school, duplicates, old profiles, help level, show; levels
    ├── test_gpio.py         shim, warm start, simulated presses, GPIO errors, lint, confirm checks,
    │                        wiring check
    ├── test_camera.py       V4L2 layouts + ioctl numbers, MJPEG fix-up, PNG, Simulator camera, clues
    ├── test_computer.py     pipath_computer numbers, pretend stats, opening files (never for real)
    ├── test_editor.py       editor behaviour (needs Tk + a display; skipped otherwise)
    ├── test_review.py       the code review coach
    ├── test_adapt.py        adaptive scaffolding: nudges, level suggestions, no nagging
    ├── test_freeplay.py     Free Play: parts from code, wiring rows, adding parts, ideas run
    ├── test_activities.py   every step's demo passes its checks (all activities); lesson lint
    ├── shimrun.py           helper: run code through the shim with timed presses
    ├── gui_smoke.py         drives the real app under Xvfb and saves screenshots (not unittest)
    └── perf_probe.py        times the main interactions (not unittest; see docs/perf.md)
```

### How a Run works (data flow)

```
Run pressed
  → precheck(code, step.starter)   blanks (___) from the starter still there? → Coach, stop
  → gpio_lint(code)                GPIO activities: warnings in the Output ("⚠ Coach tip"), never blocks
  → save file, Runner.start()      python3 -u pipath/gpio_shim.py <file> (every run); own
                                   process group (Stop: SIGTERM to the shim, then SIGKILL the group;
                                   when the shim exits, anything it left running is killed too).
                                   Warm start: if a spare shim (--wait) is waiting, it gets one
                                   JSON line {"run","cwd","env"} instead; a new spare starts
                                   ~0.4 s after each run ends
                                   Simulator: GPIOZERO_PIN_FACTORY=mock, MOCK_PIN_CLASS=mockpwmpin
                                   Camera: PIPATH_CAMERA=sim|usb|ribbon, PIPATH_CAMERA_OBJECT
  → poll every 40 ms               stdout → Output; student types → stdin
                                   shim state pipe → ("gpio", {...}) → board (devices, values, photos)
                                   board clicks → runner.send_command("press 23")
                                   runaway: >3000 lines or >300k chars in 20 s, or CPU-busy +
                                   silent for 8 s → kill. stderr shows live (red); input() →
                                   ("gpio", {"t": "input"}) → focus the answer box
  → on exit (exit code + both pipes closed)
      Stop pressed on a run_mode="until_stopped" step → treated as a normal finish
      crashed? parse_traceback() → ErrorInfo → HintEngine.diagnose() → Coach card, red line
      evaluate_checks(checks, code, stdout, crashed, runs, confirmed, folder, since)
      all pass → step done; only "confirm" boxes left → "Did you see it happen?"
```

### The shim (`pipath/gpio_shim.py`)
- Runs the student's file with `runpy` (`sys.path[0]` = the student's folder; `student_lib/` appended).
- `--wait` (warm start): imports the modules in `PIPATH_PRELOAD` (gpiozero, its mock pins, lgpio
  on a Pi, `pipath_camera`, `picamera2` for a ribbon camera) with output silenced, then waits
  for the order on the command fd. EOF (the app closed it) → exits quietly.
- Simulator: the shim makes gpiozero's `MockFactory` itself. (Naming the factory in the
  environment makes gpiozero scan every installed package, which takes seconds on Pi OS.)
- Patches gpiozero **only when the student imports it** (import hook), recording every
  `GPIODevice` and `RGBLED`. A 50 ms thread sends `devices` / `pins` messages (JSON lines,
  fd in `PIPATH_STATE_FD`) only when something changed. Values: outputs = brightness 0–1,
  inputs = 1 when active.
- Commands (fd in `PIPATH_CMD_FD`): `press N` / `release N` (Simulator only; pull-up inputs
  are driven low), `show <object>` (simulated camera), `distance ECHO CM` (Simulator: the
  DistanceSensor's `_read` is patched on mock pins), `stat temp|load|ram VALUE` (Simulator:
  pretend numbers for `pipath_computer`, via `PIPATH_SIM_*` env vars).
- `builtins.input` is wrapped to send `{"t": "input"}` so the app focuses the answer box (and
  Watch the goal types the next answer).
- Tracebacks are trimmed to start in the student's file. A crash inside an event handler
  (e.g. `when_pressed`) is reported and ends the program. SIGTERM (Stop) → `SystemExit(0)`
  so gpiozero closes devices and real LEDs switch off.
- **Real Pi mode** uses the same shim with the real pin factory: the board mirrors what the
  code tells the pins to do, so students can compare it with their breadboard.

### Storage layout (`~/PiPath`, override with `PIPATH_HOME`)

```
~/PiPath/app.json                        last_student, gpio_mode (sim|real), camera (sim|usb|ribbon)
~/PiPath/students/<slug>/profile.json    first_name (all names joined: "Sam & Alex"), names [..],
                                          school, created, last_seen, tour_done, help_level
                                          (beginner|moderate|advanced; missing = beginner), show
                                          ("all", "hardware" or a tier id), code_size (optional),
                                          adaptive (false = no nudges), adapt {history, cooldown}
                                          (older profiles may also have class_code; no names = [first_name])
~/PiPath/students/<slug>/progress.json   lessons.<id>: status, step, steps_done, steps_started,
                                          steps_skipped, hints_used, hints_seen, runs, errors,
                                          started, completed
~/PiPath/students/<slug>/lessons/*.py    lesson code (one file per activity, built up step by step)
~/PiPath/students/<slug>/lessons/*.jpg|csv|json   photos, logs, examples.json written by programs
~/PiPath/students/<slug>/lessons/backups/  code saved before a "replace" step overwrote it
~/PiPath/students/<slug>/projects/*.py   Free Play projects
~/PiPath/exports/progress_<date>.csv     (older versions' exports; now in the Save a copy zip)
~/Downloads/PiPath_save_<date>.zip       Save a copy: everyone's work + progress.csv
```

---

## 5. Data formats

### 5.1 `catalog.toml`

```toml
[[tier]]          # id, title, tagline, description. Order = order on the activity picker
[[project]]
id = "a1_traffic"         # also the lesson file name: data/lessons/a1_traffic.toml
tier = "advanced"
title, subtitle, concepts = [..], minutes, support = "scaffolded"
status = "ready"          # ready | planned ("Coming soon" card)
try_first = ["s3_guess"]  # optional tip "Good to try first: ...", hidden once those are done
gpio = true               # optional: card says "needs GPIO kit"
camera = true             # optional: card says "needs camera"
parts = [..]              # optional: shopping list, shown in the Wiring card
curriculum = [..]         # "Strand: what students do" (Victorian Curriculum DT Levels 9-10), in Settings > Curriculum
stretch = [..]            # Level up challenges for experienced students, in the outro
```

Nothing is locked; `unlock_after` and `free_build_unlock` are gone.

### 5.2 Lesson file (`data/lessons/<id>.toml`)

```toml
id = "a1_traffic"
title = "Traffic Lights"
file_name = "traffic_lights.py"     # what the student's file is called
intro = """markdown"""              # shown before step 1
outro = """markdown"""              # shown on completion with stars + extension ideas
requires_gpio = true                # Wiring card, Simulator / Real Pi switch, board
requires_camera = true              # camera panel on the board (click its title to switch camera)
files = ["p3/party"]                # optional: copied from data/demo_files/ into the student's
                                    # folder when the activity opens (never replacing their files)

[[wiring]]                          # one row per part (rows without kind are tips)
part = "Red LED"                    # name in the card and on the board
kind = "led"                        # led | rgbled | button | switch | buzzer | pir | distance
pin = 17                            # GPIO (BCM) number; rgbled uses pins = [r, g, b];
                                    # distance uses pins = [echo, trigger]
colour = "red"                      # led colour on the board: red amber yellow orange green blue white
connect = "GPIO17 (pin 11) → 330Ω → long leg; short leg → GND"

[[steps]]
title = "Keep guessing with a loop"
support = "guided" | "scaffolded" | "brief"
starter_mode = "replace" | "append" | "keep"   # applied the FIRST time a step is entered
starter = '''code'''                # may contain ___ blanks
run_mode = "until_stopped"          # program runs until Stop; checks evaluated when Stop is pressed
text = """markdown instructions"""  # put the goal in a **Your task:** / **Goal:** line: Advanced
                                    # students see the text from there on (or the whole text if
                                    # it starts with it), with "Show the full explanation"
goal = """markdown"""               # optional: a hand-written short version for Advanced instead
hints = ["nudge", "more specific", "almost the answer"]   # max 3
error_hints = { TypeError = "step-specific hint shown first for this error type" }
success = "message when every check passes"
demo = '''model answer'''           # REQUIRED. Played by "Watch the goal", tested in tests/, and put in
                                    # the editor when an Advanced student skips the step (if the next
                                    # step builds on it, i.e. isn't "replace")
demo_events = ["2 tap 23", "1.5 press 4", "3 release 4", "0.5 show ball",
               "1 tap 23 every 0.8 until 30",
               "1.5 distance 26 15", "2 stat load 90"]   # presses, camera objects, distances, Pi numbers
demo_seconds = 10                   # stop the demo after this long (until_stopped programs)
demo_input = "5\n"                  # answers typed into the Output, one at a time, at each prompt
demo_files = ["c2/examples.json"]   # copied from data/demo_files/ into the demo's folder

[[steps.checks]]
type = "output_contains"
value = "You got it"
label = "You played until you won"      # shown in the checklist
fail = "shown in the Coach if this is the first failing check"
ignore_case = true                       # optional
```

In TOML `'''literal'''` strings backslashes are literal: write `\n` (not `\\n`) in `demo`
code, and `\\n` in `"""basic"""` strings such as `text`.

Mini-markdown supported by `RichText`: `## heading`, `**bold**`, `*italic*`, `` `code` ``,
`- bullets`, `1. numbered`, fenced ``` code blocks ```.

### 5.3 Check types

| type | passes when | extra keys |
|---|---|---|
| `runs_ok` | the program didn't crash | |
| `output_contains` | stdout contains `value` (case-insensitive by default) | `ignore_case` |
| `output_regex` | regex `value` matches stdout | `ignore_case` |
| `output_lines_min` | at least `min` non-blank output lines | `min` |
| `code_contains` | source contains `value` | |
| `code_regex` | regex `value` matches source (multiline) | `ignore_case` |
| `code_uses` | AST feature present (see below) | |
| `code_count` | AST feature appears at least `min` times | `min` |
| `run_count_min` | student pressed Run at least `min` times this step | `min` |
| `confirm` | student ticked "I saw it happen" (only allowed after a run) | |
| `file_exists` | at least `min` files matching glob `value` were written **this run** | `min` |
| `file_contains` | a file matching glob `file`, written this run, matches regex `value` | `file`, `ignore_case` |

AST features from `hints.code_features()`: `call:print`, `call:randint` (function or
method name), `import:random`, `import:LED` (names from `from x import y`),
`attr:upper`, `attr:when_pressed`, `node:While` / `node:For` / `node:If` /
`node:FunctionDef` / `node:Return` / `node:Break` / `node:List` / `node:Dict` / `node:Try`
(any `ast` node class), `fstring`, `elif`.

**Unknown check types pass**, so a lesson written for a newer PiPath never blocks a student.

### 5.4 `errors.toml`

```toml
[[error]]
id = "concat_str_number"            # unique, used in tests
type = "TypeError"                  # last segment of the exception name; "*" = catch-all
message = '''regex with (?P<named>groups)'''   # optional, searched in the message
code = '''regex'''                  # optional, searched in the broken line of code
title = "Can't join text and a number with +"
explain = "markdown. {line}, {code_line}, {type}, {message} and named groups are filled in"
hints = ["up to 3, nudge → near-answer"]
tech = """optional: the deeper why, with technical terms, for Moderate / Advanced (Years 9-10)"""
```

First match wins, so **specific entries go above general ones**. The file ends with a
`*` catch-all. Internal types: `PiPathBlanks` (blanks left), `PiPathRunaway` with
message `output`, `busy_gpio` (a busy loop that polls `is_pressed` etc.) or `busy`.
Camera types: `CameraNotFound`, `CameraBusy` (raised by `pipath_camera`). Write `{{` `}}`
for literal braces.

**When adding an entry, add a test case** (`tests/test_hints.py`, or `tests/test_gpio.py`
for GPIO errors with mock pins) with a real broken program.

---

## 6. Gradual release model

| support | badge | step hints unlock | error hints shown | typical use |
|---|---|---|---|---|
| `guided` | GUIDED (green) | immediately | all 3 tiers | blanks to fill, code given |
| `scaffolded` | SOME HELP (blue) | after 1 failed run | all 3 tiers | instructions + examples, student writes code |
| `brief` | ON YOUR OWN (red) | after 2 failed runs | first 2 tiers only (no near-answer) | goal + checklist only |

- Error **explanations** are always shown. Understanding errors is a learning goal.
- Every hint revealed adds to `hints_used`. **Independence stars:** ≤2 hints ★★★,
  ≤6 ★★, else ★ (thresholds in `config.toml`). Stars are framed positively.
- Within an activity, support should fade: at least one `brief` step per activity from S3 on.
- Because students choose freely, the first step of each activity can drop back a level.

### Help levels (the student's choice, `pipath/levels.py`)

Students pick a level on the activity picker or with **Help:** in the workspace top bar. It's
saved in `profile.json` (`help_level`) and goes on top of each step's `support`:

| level | hints unlock | hint tiers | instructions | tour | skip a step |
|---|---|---|---|---|---|
| Beginner (default) | immediately | all 3 | full text | offered | no |
| Moderate | the step's `support` rule (table above) | the step's rule | full text | offered | no |
| Advanced | after 2 tries | 2 (never the near-answer; step hints too) | goal first, "▸ Show the full explanation" | not offered | yes |

- **Skip** (Advanced only) records the step in `steps_skipped` (a faint dot), saves the
  student's code in `backups/` and, if the next step builds on this one, puts the skipped
  step's `demo` in the editor so the next step has what it needs.
- Stars still count hints at every level. 

---

## 7. Curriculum: all activities

Legend: ✅ written, playable and tested in the Simulator · 🔲 outline only (write the TOML)

**Shape of every hardware activity:** one part first (an LED), a short step that tests each
new part on its own (the button, the sensor, the camera, the countdown lights), then a step
that joins it to the rest, and so on to the finished project. A test-the-part step that
"replace"s the code says the student's code is safe in `backups/`; the joining step's starter
brings the earlier work back (as the model answer) with blanks for the new connections.

Standard pin plan for **all** GPIO activities (Pi 3B, BCM numbers), so one breadboard build
carries between activities:

| Part | GPIO | Physical pin |
|---|---|---|
| Red LED / LED 1 | 17 | 11 |
| Amber/Green LED / LED 2 | 27 | 13 |
| Green/Blue LED / LED 3 | 22 | 15 |
| LED 4, 5, 6 | 5, 6, 13 | 29, 31, 33 |
| Button 1 / 2 / 3 | 23 / 24 / 25 | 16 / 18 / 22 |
| Buzzer (active) | 18 | 12 |
| Distance sensor (HC-SR04) TRIG | 4 | 7 (VCC → 5V pin 2, GND → pin 6) |
| Distance sensor ECHO | 26 | 37, **through a 1kΩ / 2kΩ divider** (5V echo → 3.3V) |
| GND | | 6, 9, 14, 20, 25, 30, 34, 39 |

Avoid GPIO 2/3 (I²C, fixed pull-ups) and 14/15 (serial console).

| Tier | Activity | Status | Steps (support) |
|---|---|---|---|
| Simple | S1 Hello, Pi! | ✅ | run · name blank · 3 prints · bug hunt (G) · ASCII art (S) |
| Simple | S2 Meet PiBot | ✅ | variables · input + f-string (G) · `input()+1` bug · `.upper()` (S) · own question (B) |
| Simple | S3 Guess My Number | ✅ | randint · if/else · elif · while (S) · counter 1–100 (B) |
| Moderate | M1 Quiz Master | ✅ | one question + score · lists + `zip()` · bug hunt: `.strip().lower()` · `def ask()` returns · percentage bands · challenge: `random.shuffle` (S → B) |
| Moderate | M2 Turtle Art Studio | ✅ | square (G) · `for` loop · `def polygon(sides, size)` · spinning rainbow with `%` (S) · own artwork (B) |
| Moderate | M3 Tuckshop Till | ✅ | menu dictionary + `:.2f` · order loop · receipt with GST · save receipt · `sales.csv` (S) · challenge: the day's takings (B) |
| Pi & Computer | P1 Pi Health Lights | ✅ | `cpu_temp()` etc. (G) · read the temp file with try/except (G) · loop monitor (S) · text bars (S) · test 3 PWMLEDs (G) · live brightness (S) · warnings (S) · CSV log (B) |
| Pi & Computer | P2 Binary Clock | ✅ | `datetime.now()` (G) · `format(n, "06b")` (G) · ●/○ clock on screen (S) · test 6 LEDs (G) · seconds on LEDBoard (S) · test the button (G) · seconds/minutes/hours modes (B) |
| Pi & Computer | P3 Dice DJ | ✅ | randint (G) · test the button (G) · test LEDBarGraph (G) · LED dice (S) · `open_file(sounds[roll - 1])` (S) · `glob` playlist (S) · surprise button → `open_website` (B) |
| Pi & Computer | P4 Doorbell Cam | ✅ | test the distance sensor (G) · test camera + `open_file(name)` (G) · test the bell (G) · `when_in_range` ding dong (S) · snap the visitor (S) · show it (S) · cooldown + visitor CSV (B) |
| Pi & Computer | P5 Focus Timer | ✅ | countdown (G) · test 6 LEDs (G) · shrinking bar (S) · test buzzer (G) · button starts, beep at end · `show_message` break (S) · study log CSV (B) |
| Pi & Computer | P6 Control Pad | ✅ | test buttons · test LED (G) · screenshot · volume (S) · dictionary of actions · `when_held` website (S) · action log CSV (B) |
| Advanced | A1 Traffic Lights | ✅ | flash one LED (G) · green→amber→red (S) · `def cycle()` + `while True` (S) · test the button: 3 × `wait_for_press` (G) · lights + button = pedestrian crossing (S) · add the beeper (S) · countdown + flashing red (B) |
| Advanced | A2 Reaction Timer | ✅ | light the LED (G) · random wait (S) · test the button: hold timer with `monotonic()` (G) · reaction stopwatch (S) · false start with `wait_for_press(timeout=)` (S) · 2-player `when_pressed` race (B) · best of 5 + `highscore.txt` with try/except (B) |
| Advanced | A3 Motion Alarm & Logger | ✅ | HC-SR04 ultrasonic: test the LED + buzzer (G) · `sensor.distance * 100` (G) · `when_in_range` / `when_out_of_range` (S) · sensor + alarm (S) · armed state + button (S) · CSV log with `datetime` (B) · cooldown + report (B) |
| Lab | E1 Light Switch Lab | ✅ | LED · `wait_for_press` (G) · hold-to-light · toggle (S) · PWM dimmer (B) |
| Lab | E2 RGB Mood Lamp | ✅ | tuples · rainbow nested loop · `%` wrap, planted IndexError (S) · party mode `when_held` · own lamp (B) |
| Lab | E3 Simon Says | ✅ | lists of LEDs · `zip()` · random pattern · `get_press()` returns (S) · full game (B) |
| Lab | E4 Bar Graph & Digital Dice | ✅ | LEDBoard · scanner · counter with limits (S) · dice roll · shake to roll (B) |
| Lab | E5 Parking Sensor | ✅ | test the sensor · test 3 LEDs (G) · zones with if/elif (S) · test the buzzer (G) · beep faster when closer (S) · lights + beeps, print on change (S) · parking game (B) |
| Lab | E6 Whack-a-Mole | ✅ | random mole (G) · test the buttons (G) · `which_button(timeout)` (S) · one round (S) · test the buzzer (G) · 10 moles + score (S) · faster and faster (S) · 3 lives + high score file (B) |
| Lab | E7 Morse Code Messenger | ✅ | SOS on the LED (G) · Morse dictionary (G) · send a word with light and sound (S) · test the key (G) · dot or dash (S) · decode letters (S) · Morse quiz (B) |
| Camera & AI | C1 Photo Booth | ✅ | `take_photo` (G) · button to snap (G) · countdown lights + beep, no camera (S) · button → `countdown()` → photo (S) · `datetime` names + loop (S) · 4-photo strip + `glob` count (B) |
| Camera & AI | C2 Teachable Machine | ✅ | `capture_grid` as `#`/`.` art (S) · collect labelled examples → `examples.json` (S) · `distance()` with `abs()` (S) · nearest-neighbour `classify()` guesses one photo (S) · button + matching LED in a loop (S) · accuracy test (B) |

Camera activities use the students' helper `from pipath_camera import Camera`
(`take_photo(name)`, `capture_grid(rows, cols)`). The Simulator's pretend camera shows a
face, ball, box or nothing (picked on the board); a nearest-neighbour classifier gets
about 90% on its ball/box pictures.

### Free Play (the sandbox)
The first box on the activity picker, always open (its name is `free_play_name` in config.toml).
No steps or checklists. The student picks **Guide me** (the Coach explains errors, nudges when
stuck with the adaptive coach in "free" context, and after a working run adds one "Idea to level
up" from the code review) or **On my own** (errors are explained, nothing else); saved as
`free_play_mode` in the profile. The left panel has:
- **Add a part** (`data/freeplay.toml`): LED, button, buzzer, distance sensor, RGB LED, 6-LED bar,
  camera, the Pi's numbers, and code snippets. Inserted at the cursor (one Ctrl+Z removes it), with
  free pins from the standard plan, a fresh name and imports at the top; the Coach says how to wire it.
- **My wiring**: built from the code (`freeplay.parts_from_code`): a Wiring card with connections,
  the header map and **Check my wiring**; pin clashes are flagged; the Simulator board shows the parts.
- My projects (names that shadow modules are refused), **Need an idea?** starter projects, cheat sheet.

---

## 8. GPIO + camera design (as built)

- **Simulator / Real Pi** switch in the workspace toolbar (`Run on:`) and in Settings. Real Pi
  is disabled off a Pi (`/proc/device-tree/model`; `PIPATH_FORCE_SIM=1` pretends). Saved per Pi
  in app.json; a Pi starts on Real Pi. While a Real Pi run is going the board shows **● LIVE**.
- **Board** (`ui/board.py`): parts from the lesson's `[[wiring]]` rows (in order), plus any
  device the program makes. Click and hold buttons; click the PIR to "wave" (3 s); drag the
  distance sensor's slider (2–150 cm; hidden in Real Pi mode, where it shows the real reading).
  The board switches everything off when a program ends, like real hardware.
- **Watch the goal**: runs the step's `demo` in a temp folder on the Simulator with its
  `demo_events`; the student's code isn't touched and the run isn't counted. `demo_input`
  answers are typed in one at a time, each time the program shows a prompt (and echoed in the
  Output, as if a student typed them).
- **Warm start** (`Workspace.preload`, `Runner.warm_up`): GPIO/camera workspaces and Free Play
  keep one spare shim process waiting with the slow modules imported. It's dropped when the
  workspace is hidden and re-made after each run and when the camera kind changes. The spare
  never touches the pins: the pin factory is only made once it's given a program.
- **Wiring + Safety card** (`ui/wiring.py`): safety list, parts, connect rows, 40-pin header
  map with the activity's pins highlighted, and **Check my wiring** (a generated program
  that blinks each LED, beeps the buzzer and waits for each button / the PIR; ✓/✗ ticks).
- **Distance sensor:** gpiozero `DistanceSensor(echo=26, trigger=4)`. The shim hides the trigger
  pin from the board and drops gpiozero's "use pigpio" warning. A missing echo shows a Coach tip
  (`DistanceSensorNoEcho`) instead of a wall of warnings.
- **Lint** (`hints.gpio_lint`): `when_pressed = f()` brackets, `while True` that never
  waits, a loop that waits for a press but never for the release (holding the button repeats
  it), a pin used twice, pins outside 2–27 or special pins. Lesson demos must be lint-free
  (`tests/test_activities.py`).
- **Camera** (`student_lib/pipath_camera.py`): `sim` (pure Python, PNG), `usb` (V4L2 via
  ctypes/ioctl/mmap: MJPEG for photos with standard Huffman tables added if missing, YUYV
  for grids; Picamera2 fallback), `ribbon` (Picamera2, or `rpicam-still`). Photos and grid
  previews are sent to the board's camera panel; click its title to switch camera
  (saved per Pi).
- Safety panel text lives in `gpio.SAFETY` (also in the README).

---

## 9. Save data (no teacher panel)

There is no teacher panel or PIN: the students run PiPath. **Settings > Save data** (also the
**Save data** button on the welcome desktop, which opens Settings with only that tab when nobody is
logged in):
- **Save a copy** (`storage.save_copy`): a zip of `students/` (and any old `exports/`) plus a
  `progress.csv` summary, in `~/Downloads` (`PIPATH_DOWNLOADS` overrides; made if missing). Photos
  and sounds are stored, not re-compressed (quick on a Pi).
- **Wipe session** (`App.wipe_session` → `storage.wipe_all`): type `WIPE` to enable the button.
  Logs out (stops any program), removes `students/` and `exports/` by moving them aside first,
  drops `last_student`, keeps the Pi's settings (`gpio_mode`, `camera`), shows the welcome screen.

Ideas for later: reset one activity; delete one student (with confirm); import lessons from a USB
stick (`/media/*/PiPath-lessons/*.toml`) after validating them; a lesson lint command
(`python3 -m pipath.lint`, from `tests/test_activities.py::TestLessonFiles`).

---

## 10. Deployment

- **Double-click installer** `Install-PiPath.desktop` (repo root): a launcher that downloads and runs
  `tools/install_pipath.sh` from the `main` branch in a terminal window. The script installs
  or updates `~/pipath` (git fetch + checkout of the branch, local edits stashed; or a fresh shallow
  clone; or, without git, the branch zip swapped in), runs `install.sh`, then opens PiPath. It never
  touches `~/PiPath` (student work) and never asks for a GitHub login. `PIPATH_REPO`,
  `PIPATH_BRANCH`, `PIPATH_DIR` override; `PIPATH_NO_LAUNCH=1` skips opening the app.
- `install.sh`: adds a menu entry (Programming → PiPath, with the school icon `data/brand/icon_128.png`),
  **Update PiPath** (runs the installer script in a terminal) and a desktop icon; optional
  `--autostart`; pre-compiles the Python files (`compileall`) so the first start is quicker.
- Classroom roll-out: set up one Pi fully, then clone the SD card (Raspberry Pi
  **SD Card Copier** or Imager) for the class set.
- Updates: menu → Update PiPath (or `git pull`), or copy a new `data/` folder from USB. Student work in `~/PiPath`
  is never touched by updates.
- Pi OS Desktop already has `python3-tk`, `python3-gpiozero`, `python3-lgpio`,
  `python3-picamera2`. On Lite images:
  `sudo apt install python3-tk python3-gpiozero python3-lgpio python3-picamera2`.

---

## 11. What's next

Built and passing in the Simulator: all 24 activities (nothing is "coming soon"), adaptive
scaffolding, the GPIO foundation, A1–A3 (A3 now ultrasonic), the
Electronics Lab, the Camera & AI tier, the Pi & Computer tier (P1–P4), student-chosen help
levels, the setup step + Settings cog, group profiles, the retro school-branded look, the
Thonny-style editor, the step-by-step (one part at a time) activity structure, and the Pi 3B
speed work (`docs/perf.md`). Still to do, roughly in this order:

1. **Real hardware check** (docs/pi-test-checklist.md): Pi 3B on Trixie with a breadboard
   kit, a USB webcam and a ribbon camera. Run `tests/perf_probe.py` and record the timings
   in `docs/perf.md`.
2. **Classroom feedback on the adaptive coach**: tune the thresholds in `pipath/adapt.py`.
3. **Phase 1 polish**: undo/redo buttons, "Reset step code", underline the exact word from
   the `^^^^` markers, `--scale` per student, high-contrast theme, 80+ errors.toml entries,
   a hidden log of entry ids hit per student.
4. **Save data extras** (§9).
5. **Classroom trial**: export CSVs; rewrite the steps with the most runs, errors and hints.

---

## 12. Testing

- `tests/test_hints.py` runs **real broken programs** with the current interpreter and
  asserts the Coach entry id.
- `tests/test_activities.py` runs **every step's `demo`, in every activity**, through the shim
  (mock pins for GPIO/camera) with its `demo_events` and `demo_input` (in parallel) and checks
  it passes the step's checks; hardware starters must start cleanly; every lesson file is
  linted (support, ≤3 hints, regexes compile, a checklist, a goal for Advanced, no blanks in
  demos).
- `tests/test_gpio.py` (incl. the warm start), `tests/test_camera.py`, `tests/test_storage.py`
  (incl. help levels) cover the engine. GPIO tests skip if gpiozero isn't installed.
- GUI smoke test: `xvfb-run -s "-screen 0 1366x768x24" python3 tests/gui_smoke.py shots/`
  drives login → activities → lessons → Simulator → Watch the goal → camera → help levels →
  Skip, and saves screenshots (needs Tk, Xvfb, ImageMagick `import`). Run it at 1024×640 too
  (`PIPATH_SMOKE_SIZE=1024x640`).
- Speed: `python3 tests/perf_probe.py` (under `xvfb-run` on a PC) prints ms per interaction.
- Manual Pi checklist: `docs/pi-test-checklist.md`.

---

## 13. Decisions already made (don't relitigate without reason)

- **Tkinter over a Thonny plugin.** Full control of onboarding, the guide panel and gradual
  release; light enough for a Pi 3B.
- **TOML for content**: readable, comments allowed, multi-line literal strings for code.
- **First name(s) + school only.** No class, surnames, emails or photos of students in profiles.
  Up to 4 first names on one profile for students who share a Pi. Duplicate names + school →
  suggest adding a surname initial.
- **Free choice.** Every activity is open; tiers are a guide (badge, filter, try_first tips).
- **Simulator first, then real hardware**, MakeCode-style, with Watch the goal.
- **One camera helper for students** (`pipath_camera`) so the same code works with a USB
  webcam, a ribbon camera or the Simulator; the outro shows the real Picamera2 code. Likewise
  `pipath_computer` for the Pi's numbers and opening files (lessons show the raw code too).
- **The retro look in the school's colours** (Windows 95 / 90s Mac), logo in the corner.
- **HC-SR04 ultrasonic sensor** for the alarm (not a PIR): it gives a number to work with.
- **Blanks are `___`** (3+ underscores), detected only on lines copied from the step's
  starter, so students' own ASCII art with underscores still runs.
- **Stars measure independence (hints), not speed.**
- **The help level is the student's choice** (Beginner / Moderate / Advanced), changeable any
  time; it never locks content and stars still count hints.
- **One part at a time:** test each new part on its own, then join it up (§7).
- **Speed on a Pi 3B comes from not making widgets**: kept screens, re-used panels, one
  Canvas for the activity picker, a warm spare runner (`docs/perf.md`).
