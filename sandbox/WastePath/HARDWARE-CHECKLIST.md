# Trial on the actual Pi and webcam

Record the Pi/OS, webcam, lighting, camera mounting and local bin rules. Use clean,
safe example items and a small supervised mechanism, starting with simulation.

- Update application files and run `bash install.sh`. Open the menu launcher and
  check USB camera selection, the full view and correct proportions of objects.
- Take a clear-table background; wait for all ten frames to finish. Move the camera
  deliberately and confirm a new table photo and new training are required.
- Train ten Waste and ten Recycling photos with names left blank. Change position
  and orientation between photos. Verify no people/hands training is requested.
- Train and confirm the app opens Live. Look at the quiz separately if useful.
- Try fresh items; compare the outlines and recognition with your original ML Camera.
  Check Computer view and threshold changes on pale objects and shadows.
- Present known recycling: servo active/open angle, LED off. Present waste: servo
  rest angle, LED visibly flashing. Present an unfamiliar item: bin remains closed
  and LED flashes. Remove the item: LED off and servo rest. Inspect the mechanism,
  not just the on-screen angle, to establish actual movement.
- Record false classifications and withheld answers using Test; it must not move
  real GPIO. Improve example photos when the model confuses similar items.
- Disconnect/reconnect the webcam with a bin label displayed. The stale decision
  must clear after one second and withdraw GPIO. The interface must remain usable.
- Change pins/angles, navigate, reset, quit and restart; hardware must be disarmed.
  Confirm mappings survive restart, but physical GPIO does not automatically enable.
- Try a GPIO startup error and the update watchdog with the mechanism unloaded.
  A software stop cannot guarantee servo position after power loss or hardware fault.
- On first update, check old training is backed up before new full-frame training.
- Confirm existing PiPath student data is untouched, and record memory/frame rate
  on the actual Pi. Synthetic cloud tests cannot establish physical accuracy.

Disconnect power before wiring. Use a resistor for the LED and an appropriate
external servo supply with common ground. Keep fingers clear of the mechanism.
There is no people detector; use a fixed table-facing setup and remove hands when
presenting the item. This model is not a machinery safety interlock.
