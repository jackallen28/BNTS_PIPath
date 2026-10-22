"""Cached, offline Fritzing artwork. Runtime uses Tk's built-in PNG support."""
from pathlib import Path
import math
import tkinter as tk

PARTS = Path(__file__).resolve().parents[2] / 'data/parts/fritzing'


def part_image(master, kind: str, colour: str = 'red', size: int = 96):
    if kind == 'camera':
        kind = 'usb'  # USB connector, not an illustration of a particular webcam
    if kind == 'led':
        colour = colour if colour in ('red','green','blue','amber','yellow','orange','white') else 'red'
        kind = 'led_' + colour
    path = PARTS / (kind + '.png')
    if not path.exists():
        return None
    root = master.winfo_toplevel()
    if not hasattr(root, '_part_images'):
        root._part_images = {}
    factor = max(1, math.ceil(256 / max(16, size)))
    key = (kind, factor)
    if key not in root._part_images:
        root._part_images[key] = tk.PhotoImage(master=master, file=str(path)).subsample(factor)
    return root._part_images[key]


def draw_connection(canvas, page: dict):
    """Labelled connection overview; exact terminal instructions remain alongside it."""
    canvas.delete('all')
    kind = page['kind']
    if kind == 'safety':
        for x, name, caption in [(110, 'pi', 'Raspberry Pi: find the GPIO header'),
                                  (360, 'breadboard', 'Breadboard: match your kit')]:
            canvas.create_image(x, 90, image=part_image(canvas, name, size=128))
            canvas.create_text(x, 170, text=caption, font='small', fill='#1E2330', width=225)
        return
    if kind == 'led' and page.get('pins'):
        # Upstream LED-5mm-red-leg.svg: connector0 is cathode, connector1 anode.
        image = part_image(canvas, 'led', page.get('colour','red'), 128)
        canvas.create_image(300,85,image=image)
        x0 = 300 - image.width()/2
        cathode = x0 + image.width()*6.287/21.467
        anode = x0 + image.width()*16.29/21.467
        end = 85 + image.height()/2
        pin = page['pins'][0]
        from ..gpio import HEADER
        physical = next(n for n,v in HEADER.items() if v == pin)
        canvas.create_text(10,20,anchor='w',text=f'GPIO{pin} • physical pin {physical}',font='small_bold',fill='#1E2330')
        canvas.create_line(130,40,390,40,390,170,anode,170,anode,end,fill='#008080',width=3)
        canvas.create_image(180,40,image=part_image(canvas,'resistor',size=64))
        canvas.create_text(180,65,text='330Ω resistor',font='small',fill='#1E2330')
        canvas.create_text(355,145,anchor='w',text='+ long leg',font='small_bold',fill='#1E2330')
        canvas.create_line(cathode,end,cathode,195,430,195,fill='#1E2330',width=3)
        canvas.create_text(200,160,text='− short leg',font='small_bold',fill='#1E2330')
        canvas.create_text(430,213,text='GND • pin 6',font='small_bold',fill='#1E2330')
        return
    image = part_image(canvas, kind, page.get('colour', 'red'), 128)
    if image is not None:
        canvas.create_image(245, 78, image=image)
    pins = page.get('pins', [])
    from ..gpio import HEADER
    for i, pin in enumerate(pins):
        y = 30 + i * 35
        physical = next((n for n,v in HEADER.items() if v == pin), '?')
        canvas.create_text(10, y, anchor='w', text=f'GPIO{pin} (pin {physical})', font='small_bold', fill='#1E2330')
        canvas.create_line(130, y, 165, y, 165, 78, 180, 78, fill='#008080', width=3, arrow='last')
    if kind == 'led':
        resistor = part_image(canvas, 'resistor', size=64)
        canvas.create_image(165, 78, image=resistor)
        canvas.create_text(165, 103, text='330Ω', font='small', fill='#1E2330')
    if kind in ('led','rgbled','button','switch','buzzer','distance','pir','servo'):
        canvas.create_text(245, 157, text='GND: follow the terminal instructions', font='small', fill='#1E2330')
    if kind == 'servo':
        canvas.create_text(245, 180, text='Separate servo supply + common ground', font='small_bold', fill='#7A1020')
    if kind == 'camera':
        canvas.create_text(245, 157, text='USB connection (for a USB webcam)', font='small', fill='#1E2330')
    canvas.create_text(10, 210, anchor='w', text='Connection overview • check terminal labels on your own part', font='small', fill='#525866')
