# Later PiPath integration

The standalone app deliberately has no import of PiPath and changes no PiPath files.

- `vision.py`: user-supplied ML Camera colour/shape functions plus inspection checks.
- `model.py`: labelled measurements, completeness rules, kNN, grouped quiz, steady gate.
- `camera.py`: newest-frame USB reader and explicitly synthetic demonstration source.
- `storage.py`: safe numeric NPZ loading and atomic measurement saves; no pickle.
- `outputs.py`: validated per-category GPIO mappings, simulation, lazy gpiozero
  devices and the decision-update watchdog. Configuration saves separately from arming.
- `app.py`: standalone Tk shell, workshop flow, GPIO settings, report and camera rendering.

For a merge, put the workshop inside a PiPath kept screen and replace the small Tk
shell with PiPath's `TitleBar`, `PButton`, scrolling frame and `theme.C`. The current
palette/layout follows those controls visually; no copy of PiPath application logic
is included. Inject a screen-owned Camera and route all Tk work through the main
thread. Stop camera reads when the screen closes. Keep student training/test data
in a separate project folder and invalidate calibration when camera setup changes.
Retain the independent training/test sets and the explicit withholding outcome.

Give the kept screen ownership of the output controller too. Feed it only fresh,
steady accepted Live decisions, and send neutral for a withheld result. Disarm it
when the screen is hidden, the camera or training changes, settings open, or the
app closes. Keep the decision watchdog independent of Tk callbacks. Do not restore
the armed state from saved GPIO mappings, and never let the synthetic demo arm real
pins. Route hardware errors back to the UI without automatically retrying activation.
The classifier has no servo position feedback and is not a people-safety interlock.

The uploaded original's extraction routines were adapted from `ml_camera.py`;
the four-object HighGUI application itself is not bundled or modified. All new
application files are under this folder.
