# Validation: guided wiring, Waste Sorter, launch updates and repository move

Validated in the cloud on Linux x86_64, system Python 3.13, Tk and gpiozero, using
simulated GPIO/camera hardware and an Xorg dummy display. This does not validate
physical Raspberry Pi wiring, USB-camera compatibility, servo power or mechanical clearance.

- The complete suite was rerun from `/workspace/BNTS_PIPath`: **140 tests, all passed,
  none skipped**. This includes every existing activity's model answers and starters,
  the Waste Sorter steps, real Tk interaction tests, Git/ZIP updater tests and the
  legacy-installer migration test.
- The existing GUI smoke driver completed **83 scenes**, with no failed actions,
  before the byte-for-byte repository transfer. These cover normal lessons, camera,
  GPIO, Free Play, settings, curriculum, scrolling, save/export and session wipe.
- The new Beginner flow was exercised in the real GUI: code covered and inaccessible,
  stop and retry, simulated button press/release, sensor responses, all-component test,
  partial observations remaining locked, complete observations unlocking the code,
  retained camera preview and rechecking after mode/camera changes. Screens were also
  inspected at the supported minimum application size, 1024×640.
- Both waste-sorting routes were exercised through the runner: red/waste/negative
  servo position and green/recycling/positive servo position, then centre and release.
  Labelled training data, held-out practice predictions and saved pixel arrays were checked.
- Updater transport is local in tests: real Git repositories and real ZIP archives,
  with the network boundary replaced. Tests cover fast-forward/current, local edits,
  local commits, development branches, offline fallback, invalid candidates, ZIP
  backups, unsafe archive paths, student-data overlap and the one-restart launch guard.
- The actual shell installer was run against local legacy/new repositories. Local
  commits survived on a backup branch, tracked edits and untracked notes survived
  in the stash, the legacy remote was retained and the active source became
  `jackallen28/BNTS_PIPath`, branch `main`.

## Session preservation

Before switching repositories, the previous checkout was archived and every file in
the archive checked against its SHA-256. A verified Git bundle preserves the complete
session history and refs. All **157 source files** then matched byte-for-byte in the
new checkout, including every untracked addition; Git diffs and status matched too.
Session branches were also imported under `refs/session-preserved/`.

The preservation archive, Git bundle, inventory and transfer report are retained under
`/workspace/shared/pipath-session-preservation/`. The previous checkout was copied,
verified again and retained outside the active workspace. The new repository is the
only active project checkout under `/workspace`.

## Classroom release

Review and merge the feature branch into `jackallen28/BNTS_PIPath/main`. After merging,
run the new installer once on existing classroom Pis using the migration command in
the README. The newly installed launcher then checks for updates when PiPath opens.
Test one physical Pi and kit before updating the rest of the class set. The image
classifier is a small greyscale nearest-neighbour teaching example, not a universal
waste/material recognition model; students must test unseen items and record errors.
