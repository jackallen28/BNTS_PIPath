#!/bin/sh
# Run in a terminal on Raspberry Pi OS Desktop (Bookworm or newer).
set -eu
APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if ! /usr/bin/python3 -c 'import tkinter, cv2, numpy, gpiozero, lgpio; from PIL import Image, ImageTk' 2>/dev/null; then
    sudo apt-get update
    sudo apt-get install -y python3-tk python3-opencv python3-numpy python3-pil python3-pil.imagetk python3-gpiozero python3-lgpio
fi
/usr/bin/python3 -c 'import tkinter, cv2, numpy, gpiozero, lgpio; from PIL import Image, ImageTk'
/usr/bin/python3 - "$APP_DIR" <<'PY'
import os
from pathlib import Path
import subprocess
import sys
root=Path(sys.argv[1])

def quoted(value):
    return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')+'"'
entry='\n'.join(['[Desktop Entry]','Type=Application','Name=WastePath',
    'Comment=Teach the camera waste vs recycling',
    'Exec=/usr/bin/python3 '+quoted(root/'main.py'),
    'Path='+str(root),'Icon='+str(root/'icon.svg'),'Terminal=false',
    'Categories=Education;Science;','StartupNotify=true',''])
menu=Path.home()/'.local/share/applications'
menu.mkdir(parents=True,exist_ok=True)
(menu/'wastepath.desktop').write_text(entry)
try:
    desktop=Path(subprocess.check_output(['xdg-user-dir','DESKTOP'],text=True).strip())
except (FileNotFoundError,subprocess.CalledProcessError):
    desktop=Path.home()/'Desktop'
if desktop.is_dir() and desktop != Path.home():
    launcher=desktop/'WastePath.desktop'
    launcher.write_text(entry)
    launcher.chmod(0o755)
print('WastePath installed. Open it from the Education menu or run:')
print('/usr/bin/python3 '+str(root/'main.py'))
PY
