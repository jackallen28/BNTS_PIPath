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
- Take extra photos past 10 for one bin: the bar shows "+N extra" and the
  Train screen asks you to train again. Use **+ Add more … photos** from the quiz.
- Wire the closed button (BCM23 / pin 16 to GND / pin 14, never 5 V). Open
  **4. Set up bin**: the dial should show "Button pressed" when you press it by hand.
- **Find the closed position:** the lid closes slowly and stops as the button
  presses. Wrong way? Choose the other direction and try again.
- **Open 5° more** until the lid opens far enough, **Test**, then **Save**.
- Present known recycling: lid opens at once, LED off. Present waste: LED flashes,
  lid stays shut. Present an unfamiliar item: lid stays shut and LED flashes.
  Remove the recycling: after about 2 s the lid sweeps shut, stops on the button and
  goes quiet (no buzzing). Inspect the mechanism, not just the on-screen angle.
- Unplug the button wire and close the lid: Live shows ⚠ and the servo stops 15°
  past the saved angle, then rests at it. Hold the button down while it opens: ⚠.
- Press **Stop GPIO** with the lid open: it should close before the pins are freed.
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
