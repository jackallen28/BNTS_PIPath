# PiPath

A Python coding tutor for Raspberry Pi with a classic Windows 95/98 look, in the colours of the
Banyule Nillumbik Tech School. Students log in with their **first name and school**
(up to four names on one profile when they share a Pi), then choose any activity: screen-only
Python, the Pi talking to its own computer, electronics with the GPIO pins, or the camera.
A built-in **Coach** explains errors in plain English and gives tiered hints from a
common-errors database. No AI service and no internet needed.

GPIO and camera activities work like MakeCode: students try their code on an on-screen
**Simulator** board first (and can **Watch the goal** to see what should happen), then
switch to **Real Pi** and run the same code on their breadboard. In Real Pi mode the board shows
**● LIVE** while the program drives the real pins.

## Screenshots

| | |
|---|---|
| ![Welcome](docs/screenshots/01_welcome_first_run.png) | ![Set up](docs/screenshots/02_setup.png) |
| ![Hardware projects](docs/screenshots/03_hardware_filter.png) | ![Motion Alarm with the Simulator](docs/screenshots/04_a3_close.png) |
| ![Edit menu](docs/screenshots/06_menu_edit.png) | ![Advanced: Python's own error and a technical explanation](docs/screenshots/08_advanced_error.png) |
| ![Code review coach](docs/screenshots/09_code_review.png) | ![About PiPath](docs/screenshots/11_about.png) |
| ![Free Play, the first box](docs/screenshots/12_free_play_first_box.png) | ![Free Play: Add a part](docs/screenshots/13_free_play_add_part.png) |
| ![Free Play: wiring made from the code](docs/screenshots/14_free_play_wiring.png) | ![Free Play: a nudge from the Coach](docs/screenshots/15_free_play_nudge.png) |

## Quick start (on the Pi)

**Double-click installer:** on the Pi, open
`https://raw.githubusercontent.com/jackallen28/BNTS_PIPath/main/Install-PiPath.desktop` in the
browser and save it (right-click > Save as, or Ctrl+S), then double-click **Install-PiPath.desktop**
in Downloads. If asked, choose **Execute** (or **Execute in Terminal**). A window shows the progress:
it downloads the latest PiPath into `~/pipath`, adds **PiPath** (and **Update PiPath**) to the menu
under Programming and an icon to the desktop, then opens PiPath. Run it again (or use
**Update PiPath**) to update; students' work in `~/PiPath` is never touched.

Or in a Terminal (the same installer):

```
curl -fsSL https://raw.githubusercontent.com/jackallen28/BNTS_PIPath/main/tools/install_pipath.sh | bash
```

Or by hand:

```
git clone --depth 1 -b main https://github.com/jackallen28/BNTS_PIPath.git ~/pipath
cd ~/pipath
./install.sh                 # menu entry + desktop icon; ./install.sh --autostart also opens it at login
python3 main.py              # add --scale 1.25 for larger text
```

No internet on the Pi? Download
`https://github.com/jackallen28/BNTS_PIPath/archive/refs/heads/main.zip`
on another computer, copy it over on a USB stick, unzip it and run `./install.sh` in that folder.

Needs Raspberry Pi OS Desktop (Bookworm or newer, Python 3.11+). Tkinter, gpiozero, lgpio and
Picamera2 are already installed on the Desktop image. PiPath also runs on any Linux computer
with Python 3.11+ and Tkinter, in Simulator mode (`pip install gpiozero` for GPIO activities).

## How students use it

1. **Log in:** pick their name, or make a profile: first name (press **+ Add another student**
   for a pair or group, up to 4) and school.
2. **Set up** (step 2 of making a profile): choose **how much help they want** and **what they
   want to see** on the activity picker. Both can change any time with the **Settings** cog,
   which is on every screen (it also has the names, Simulator / Real Pi, the camera and the
   code text size). Help levels:
   - **Beginner:** full explanations, and hints whenever they want them
   - **Moderate:** help fades as they go (each activity's own plan: have a try, then hints unlock)
   - **Advanced** (Year 9-10, "tutorial off"): just the goal (the full explanation is one click
     away), fewer hints, no tour, and they can **skip** steps they already know
3. **Pick an activity.** Everything is open, and students do as many or as few as they like, in
   any order. The coloured tiers are a guide: *Simple*, *Moderate*, *Pi & Computer*, *Advanced*,
   *Electronics Lab*, *Camera & AI*. Cards show "Good to try first" tips.
4. **Work through the steps.** Each activity starts with one part (an LED, say), tests each new
   part on its own (the button), then joins them up, step by step, to the finished project.
   Every step has instructions, a checklist and the Coach. The first time, PiPath offers a
   30-second tour (**? Tour** shows it again).
5. **GPIO and camera activities** have:
   - **Run on: Simulator | Real Pi** next to the Run button (Real Pi only appears on a Pi)
   - the **board**, beside the Output. In the Simulator it *is* the hardware: click and hold
     buttons, drag the distance sensor's slider. In Real Pi mode it shows what the code is doing,
     live.
   - **Watch the goal ▶**: plays the finished step on the board (screen-only activities have it
     too, next to the Run button: it types the answers in, so students see a whole run)
   - a **Wiring + Safety** card with a pin map and **Check my wiring**
   - "I saw it happen" boxes in the checklist, ticked by the student after a run
   - for camera activities, a **camera panel**: click its title to switch
     **Simulated / USB / Ribbon** (remembered on that Pi)
6. **Free Play** (the first box on the activity picker) is the sandbox, open any time. Students
   build anything, with **Guide me** (the Coach explains errors, nudges when they're stuck and
   suggests ideas to level up) or **On my own**. **Add a part** puts working code for an LED,
   button, buzzer, distance sensor, RGB LED, LED bar or the camera where the cursor is, with pins
   from the pin plan, and **My wiring** shows how to hook up whatever their code uses (with the pin
   map and Check my wiring). Starter ideas: Magic 8-Ball, Secret password, Disco lights, a reaction
   game, a "too close!" alarm and a selfie button.

## Help that adapts

Students choose a help level, and PiPath adjusts around it as they go (it *offers*, never forces):

- **Stuck?** The same error twice, a check that keeps failing, a long quiet spell, or no Run after a
  few minutes brings a gentle nudge with buttons: *Show me a hint*, *Watch the goal*, *Show the
  full explanation*. Hints also unlock early, whatever the level.
- **Flying?** Three steps in a row first try with no hints: *"You're flying! Try a harder level?"*
- **Finding it tough?** Lots of tries or hints over several steps: *"Want a bit more help?"*

Each nudge appears once per step, and level suggestions wait a few steps, so it never nags.
Students can turn it off in Settings (Help tab).

## Coaching for Years 9-10

Students who have used Python before pick **Advanced** (at setup, or with the Settings cog):

- each step starts with the goal, and **Jump to the challenge** on an activity's first page skips the
  practice steps
- errors show Python's own message plus a technical explanation (scope, types, callbacks, zero-indexing...)
- after each step, and any time with **Run > Review my code**, the code review coach looks at *how*
  the code is written: repeated code, magic numbers, unclear names, input that isn't validated,
  `global`, bare `except:`, deep nesting, and functions without a test case
- every activity's **Victorian Curriculum Digital Technologies (Levels 9-10)** links are in
  **Settings > Curriculum** (pick an activity), and its finish page has three **Level up** challenges (classes, dictionaries, validation
  and `assert` test cases, CSV analysis, structured English...)

Moderate students get the code review and the deeper explanation too. Check the curriculum links
against the version of the Victorian Curriculum your school uses.

## Activities

| Tier | Activity | Students build | Kit |
|---|---|---|---|
| Simple | Hello, Pi! · Meet PiBot · Guess My Number | print, variables, input, if, loops | none |
| Moderate | **Quiz Master** | lists, `zip()`, a bug hunt with `.strip().lower()`, a function that returns, percentages, shuffling | none |
| Moderate | **Turtle Art Studio** | shapes with loops, `def polygon(sides, size)`, spinning rainbow patterns, your own artwork | none |
| Moderate | **Tuckshop Till** | a menu dictionary, an order loop, a receipt with GST, saving receipts, a sales log and the day's takings | none |
| Pi & Computer | **Pi Health Lights** | read the Pi's temperature, CPU load and RAM (from the helper, then the file itself), a live monitor, text bar graphs, three LEDs that glow brighter as the numbers rise, warnings, a CSV log | 3 LEDs |
| Pi & Computer | **Binary Clock** | read the clock, binary with `format()`, a ticking clock on screen, the seconds live on six LEDs, a button for seconds / minutes / hours | 6 LEDs, button |
| Pi & Computer | **Dice DJ** | a button rolls an LED dice and the computer plays a sound for the number, then any song / video / picture from a folder; a surprise button opens a website | 6 LEDs, 2 buttons, speaker |
| Pi & Computer | **Doorbell Cam** | the distance sensor notices a visitor, a bell rings, the camera snaps them and the photo opens on the screen; cooldown + visitor log | HC-SR04, LED, buzzer, camera |
| Pi & Computer | **Focus Timer** | a countdown, a shrinking bar of LEDs, a beep, a break message on the screen, a study log | 6 LEDs, buzzer, button |
| Pi & Computer | **Control Pad** | buttons that take a screenshot, change the volume and open a website; a dictionary of actions; an action log | 3 buttons, LED |
| Advanced | **Traffic Lights** | one LED, the Australian sequence, `def cycle()` + loop, test the button, pedestrian crossing, beeper, countdown | 3 LEDs, button, buzzer |
| Advanced | **Reaction Timer** | the LED, random waits, test the button with a stopwatch, reaction game, false starts, 2-player race, high-score file | LED, 2 buttons |
| Advanced | **Motion Alarm & Logger** | test the light + buzzer, measure distance with the ultrasonic sensor, "something's close" events, the alarm, arm/disarm state, CSV log, cooldown + report | HC-SR04, LED, buzzer, button |
| Electronics Lab | Light Switch · RGB Mood Lamp · Simon Says · Bar Graph & Dice | events, PWM, colours, lists, games | see each Wiring card |
| Electronics Lab | **Parking Sensor** | a car reversing beeper: zones, beeps that speed up, a parking game | HC-SR04, 3 LEDs, buzzer, button |
| Electronics Lab | **Whack-a-Mole** | an arcade game with timeouts, a score that speeds up and a high-score file | 3 LEDs, 3 buttons, buzzer |
| Electronics Lab | **Morse Code Messenger** | dictionaries, sending with light and sound, timing a key, decoding, a quiz | LED, buzzer, button |
| Camera & AI | **Photo Booth** | photo, button photo, LED 3-2-1 countdown, all together, timestamped photos, photo strip | camera, 3 LEDs, button, buzzer |
| Camera & AI | **Teachable Machine** | images as numbers, training data, distance, a nearest-neighbour guess, lights for the answer, accuracy, bias | camera, 2 LEDs, button |

### Kit per Pi (covers every activity)

- Breadboard and male-to-female jumper wires
- LEDs: red, amber (yellow), green, plus 3 more for the Bar Graph; **330Ω resistor for every LED**
- 3 push buttons (4-leg tactile)
- 1 **active** buzzer (beeps when powered; a passive buzzer won't work with `Buzzer`)
- 1 **HC-SR04 ultrasonic distance sensor** (or similar: HC-SR04P, RCWL-1601) and a **1kΩ + 2kΩ**
  resistor for its ECHO pin (the two make the 5V echo a safe 3.3V; 3.3V sensors don't need them)
- Headphones or a small speaker (Dice DJ)
- Optional: 1 common-cathode RGB LED (Mood Lamp), 1 tilt switch (Dice)
- A camera: a **USB webcam** (any UVC webcam, e.g. DFRobot 720p wide-angle) or a
  **Raspberry Pi Camera Module** on the ribbon cable

### Standard pin plan (every activity uses it, so one build carries over)

| Part | GPIO | Physical pin |
|---|---|---|
| Red LED / LED 1 | 17 | 11 |
| Amber LED / LED 2 | 27 | 13 |
| Green LED / LED 3 | 22 | 15 |
| LED 4, 5, 6 | 5, 6, 13 | 29, 31, 33 |
| Button 1 / 2 / 3 | 23 / 24 / 25 | 16 / 18 / 22 |
| Buzzer (+) | 18 | 12 |
| Distance sensor TRIG | 4 | 7 (VCC → 5V pin 2, GND → pin 6) |
| Distance sensor ECHO | 26 | 37, through the 1kΩ / 2kΩ divider |

## Cameras

- **USB webcam:** plug it in. PiPath reads it directly (no extra software). Check it with
  `python3 pipath/student_lib/pipath_camera.py usb`
- **Ribbon camera:** (teacher) shut the Pi down, connect the ribbon (blue side towards the USB
  ports), turn on. Check it with `rpicam-hello --list-cameras`, then `python3 pipath/student_lib/pipath_camera.py ribbon`
- **Simulated:** no camera needed. The board makes pretend photos (a face, a ball, a box).

Students write the same code for all three: `from pipath_camera import Camera`,
`cam.take_photo("me.jpg")`, `cam.capture_grid(16, 16)`.

The **Pi & Computer** activities use a second helper, `from pipath_computer import ...`:
`cpu_temp()`, `cpu_load()`, `ram_used()` (read from `/sys` and `/proc`), and `open_file(name)` /
`open_website(url)` (opened with the desktop's normal app through `xdg-open`). **Watch the goal**
never opens anything; it shows what would open. `open_website` needs the internet, and the app
itself never goes online.

## GPIO safety (read before the GPIO activities)

The class kits use a **blue GPIO HAT** (breakout board). Students:

- **take the blue HAT off the GPIO pins before changing any wires**, and put it back on when done
- **never turn the Pi off** to change wires: they'd lose their progress (and an unsaved program)
- always put a 330Ω resistor in series with an LED
- never connect 5V to a GPIO pin: the distance sensor's ECHO goes through its two resistors
- don't power motors straight from GPIO pins
- ask the teacher to check the wiring before putting the HAT back on

The Wiring + Safety card in each activity repeats this, and "Check my wiring" failures say
"Take the blue HAT off, fix the wiring, put the HAT back on, then try again."

## Before your first class (checklist)

1. On one Pi: `git clone` (see Quick start), then `./install.sh`. Open PiPath from the menu.
2. Make a test profile, open **Traffic Lights**, choose **Real Pi** (or Settings > Hardware) and press
   **Check my wiring** with a breadboard built from the pin plan below.
3. Plug in the USB webcam and try **Photo Booth** step 1 (click the camera panel's title to choose USB).
4. Wipe the test profile (Settings > **Save data** > **Wipe session**), then clone the SD card for the class set.
5. In class: students take the **blue HAT** off before changing wires, and never turn the Pi off.

## For teachers

- **No teacher setup needed.** Students choose what to do, and how much help they want.
- **Help levels** are the student's choice and can change any time. Independence stars still
  count the hints they open, at every level.
- **Student work** is saved in `~/PiPath/students/<name>/` (code, photos, logs), so students pick
  up where they left off next time they choose their name. Updating PiPath never touches it.
- **Save data** (Settings > Save data, or the **Save data** button on the welcome screen):
  - **Save a copy** puts a zip of everyone's work in the Pi's **Downloads** folder
    (`~/Downloads/PiPath_save_<date>.zip`), with a `progress.csv` you can open in a spreadsheet
    (each student's activities, hints, runs and help level).
  - **Wipe session** (type `WIPE` to confirm) deletes every profile on the Pi, with all progress,
    code, photos and Free Play projects, ready for the next school or group. The Pi's own settings
    (Simulator / Real Pi, camera) stay. Do it on every Pi in the class set.
- **Edit content** without coding:
  - `data/lessons/*.toml`: steps, starter code, checklists, hints, wiring, and `demo` (the model
    answer that **Watch the goal** plays, with `demo_events` for simulated button presses and
    `demo_input` for typed answers). Start each step's goal with `**Your task:**` or `**Goal:**`:
    Advanced students see just that part.
  - `data/errors.toml`: the Coach's explanations for common errors
  - `data/catalog.toml`: which activities appear, their tier, and "Good to try first" tips
  - `data/demo_files/`: sample files a lesson copies into the student's folder (`files = [...]`,
    e.g. the Dice DJ sounds; `python3 tools/make_party_sounds.py` remakes them)
  - `data/config.toml`: Free Play's name, runaway-loop limits, star thresholds
- **Class set:** set up one Pi, then clone its SD card with *SD Card Copier*.
- **Speed on a Pi 3B:** `docs/perf.md` explains what keeps PiPath quick, and how to measure it
  on your Pis (`python3 tests/perf_probe.py`).
- **Testing on real hardware:** follow `docs/pi-test-checklist.md`.

## Developers

See `CLAUDE.md` for the architecture, data formats and what's next. Run the tests with:

```
python3 -m unittest discover -s tests
```

Every step's model answer (its `demo`) is run, in the Simulator for GPIO and camera steps,
with its button presses and typed answers, and must pass that step's own checklist. Screenshots of every main screen:
`xvfb-run -s "-screen 0 1366x768x24" python3 tests/gui_smoke.py shots/`

## Waste Sorter student project

Open **Camera & AI → Waste Sorter** in the activity picker. Allow about 120 minutes
across two or three sessions. The eight steps test the LEDs, test the servo, capture
camera grids, collect labelled training data, code nearest-neighbour prediction,
evaluate unseen samples and combine the parts in a sorting gate.

Use a USB webcam, two LEDs (red GPIO17, green GPIO22), two 330Ω resistors and **one
positional hobby servo** (signal GPIO18). The servo needs a teacher-approved separate
regulated supply matched to its voltage/current rating and a common ground with the Pi.
Do not connect external supply positive to Pi power pins. Test the bare servo before
fitting a light cardboard pointer; keep hands clear. The lesson includes full physical
pin connections and a wiring check. It is a supervised demonstration, not an automatic
waste processing machine. The gate releases after returning to centre and cannot hold a load.

Start in Simulator mode: **Ball represents waste; Box represents recycling**. On hardware,
choose **USB** from the camera panel title. Use clean samples and local council bin rules.
Students collect their own `waste_examples.json`; the activity does not install a pretrained
waste recognition model. Tiny greyscale nearest-neighbour matching works best with a fixed
camera and plain background, and can confuse unfamiliar objects or similar shapes.
Keep test items separate from training and record both kinds of incorrect prediction.
Watch the goal uses separate practice data, leaving student examples untouched.

Before classroom use on a Pi, test both camera classes, both LEDs, both gate directions,
return to centre, `q` and Stop; repeat under different lighting. Confirm the servo supply
is stable and the mechanism cannot jam. Real hardware has not been validated by the cloud tests.

## Beginner: connect, test, then code

Beginner hardware and camera activities open an in-window wiring walkthrough before the
code is accessible. Students identify each part, read what it does, follow the connections,
and run a ready-made test whose source never appears in their editor. Buttons must be
pressed and released; sensors must respond; LEDs, sound, servo movement and the camera
must also be confirmed by the student. All tests must finish successfully and every
observation must be ticked before **Open my code** is enabled. Failed or stopped checks
can be retried. **Back to activities** leaves without unlocking the code.

Simulator checks are practice, not proof that real wires are correct. Changing hardware
mode or camera invalidates the current check. Reopening a hardware activity starts a new
check. Moderate and Advanced keep the existing direct access to the coding workspace.
Teachers can add `wire_steps = ["first connection", "next connection"]` to a lesson wiring
row for separate connection pages; otherwise the existing connection text is shown.

The simulator and wiring panels share bundled Fritzing breadboard artwork. Component
pictures identify the package; the lesson's terminal names, physical pin numbers and
resistor values determine the wiring. See `data/parts/fritzing/ATTRIBUTION.md` for the
CC BY-SA 3.0 credit, original sources and image changes. Fritzing is not needed on a Pi.

## Updates when PiPath opens

On a Raspberry Pi, PiPath now checks the configured GitHub release branch **before**
loading the application. A small progress window stays responsive. If a new version is
installed, PiPath restarts once into it. Offline or failed checks open the installed
version; student work in `~/PiPath` stays on the Pi. This launch check is the only new
network use; lessons and the Coach still work offline and send no student data.

The release source is now `jackallen28/BNTS_PIPath`, branch `main`.
A Git installation updates only when that release branch is clean and can fast-forward.
Local app edits, extra untracked files, local commits, a different origin or a development
branch cause the automatic update to be skipped. Nothing is stashed, reset or force-switched.
ZIP installations managed by the installer use a file manifest to detect local edits,
validate the downloaded candidate before replacing files and retain a `pipath.before-update-*`
backup alongside the installation. Unmanaged ZIP copies need one manual update first.
Concurrent updates are locked; a second launch asks the user to reopen shortly.

Use `python3 main.py --no-update` or `PIPATH_AUTO_UPDATE=0` for an offline-only launch.
Development computers do not check automatically. Existing classroom Pis need to run
**Programming → Update PiPath** once after this release is merged to install this feature.
Future opens/reopens then check automatically. If that Pi is kept open all day, close and
reopen PiPath to check again. Custom installs can use the existing `PIPATH_REPO` and
`PIPATH_BRANCH` environment overrides; no GitHub token is required for the public release.

Deployment: review and merge the feature branch into **main** in
`jackallen28/BNTS_PIPath`. All future pull requests target this repository and branch. Before rolling out to the class, validate USB camera
capture, all button/sensor checks, both LEDs and servo directions on one classroom Pi,
then update the rest of the set. Cloud simulation cannot verify physical wiring or power.

### Move an existing classroom Pi from the old repository

After this release is merged into `jackallen28/BNTS_PIPath/main`, run the new installer
once in a terminal (the old Update PiPath shortcut still points at the previous source):

```bash
curl -fsSL https://raw.githubusercontent.com/jackallen28/BNTS_PIPath/main/tools/install_pipath.sh | bash
```

It installs in the existing `~/pipath` folder and keeps student work in `~/PiPath`.
For an old Git installation it fetches the new repository, preserves the old HEAD on a
backup branch, stashes local app edits including untracked files, and retains the old
remote before selecting `main` from the new repository. The new desktop/menu entries
then use the new checkout and its automatic launch updater. Backups are retained for
teachers to recover app edits; they are not automatically reapplied over new app code.
An old ZIP installation is also retained as a sibling backup when replaced.
