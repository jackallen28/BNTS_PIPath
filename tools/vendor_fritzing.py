"""Rebuild the bundled Fritzing artwork (developer tool; needs Inkscape).

Usage: python3 tools/vendor_fritzing.py /path/to/fritzing-parts
The source checkout must contain the pinned upstream commit. No network at runtime.
"""
import json
import re
import subprocess
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

COMMIT = '27535f2fd02097be9bed229b75aa8e9be282a4a0'
ROOT = Path(__file__).resolve().parents[1] / 'data/parts/fritzing'
SOURCES = {
    'led': 'svg/core/breadboard/LED-5mm-red-leg.svg',
    'rgbled': 'svg/core/breadboard/led-rgb-4pin-anode-leg.svg',
    'button': 'svg/core/breadboard/Pushbuttonc.svg',
    'switch': 'svg/core/breadboard/tilt_switch.svg',
    'buzzer': 'svg/core/breadboard/Buzzer-v15_breadboard.svg',
    'distance': 'svg/core/breadboard/hc-sr04_bf8299a_002.svg',
    'pir': 'svg/contrib/breadboard/PIR_sensor__723e9e78d3d1bdc76f4badecd521__breadboard__bde4d2a73b9c7784602c3b4f93cfb0ab_6B.svg',
    'servo': 'svg/core/breadboard/servo.svg',
    'resistor': 'svg/core/breadboard/resistor_220.svg',
    'pi': 'svg/core/breadboard/raspberry_pi_3_rev-1.2.svg',
    'breadboard': 'svg/core/breadboard/halfBreadboard.svg',
    'usb': 'svg/core/breadboard/usb_3.0_female_fix_breadboard.svg',
}
COLOURS = {'red':'#E60000', 'green':'#18A540', 'blue':'#205DE0', 'amber':'#FFB000',
           'yellow':'#FFE14D', 'orange':'#FF8A00', 'white':'#EFEFEF'}


def main():
    checkout = Path(sys.argv[1]).resolve()
    ROOT.mkdir(parents=True, exist_ok=True)
    def read(path):
        return subprocess.check_output(['git','-C',str(checkout),'show',f'{COMMIT}:{path}'])
    (ROOT/'LICENSE.txt').write_bytes(read('LICENSE.txt'))
    manifest = {'repository':'https://github.com/fritzing/fritzing-parts', 'commit':COMMIT,
                'licence':'CC-BY-SA-3.0', 'sources':SOURCES,
                'changes':'PNG rasterisation; LED colour variants; resistor bands changed to 330 ohms. '
                          'RGB package illustration has four leads; follow lesson terminal instructions for your common-cathode part.'}
    for name, path in SOURCES.items():
        data = read(path).decode()
        if name == 'resistor':
            data = data.replace('#C40808', '#FF8000')  # orange, orange, brown = 330 ohms
        variants = {f'led_{k}':data.replace('#E60000',v) for k,v in COLOURS.items()} if name == 'led' else {name:data}
        for stem, svg in variants.items():
            source = ROOT / (stem+'.svg')
            svg = "\n".join(line.rstrip() for line in svg.splitlines()) + "\n"
            source.write_text(svg)
            attrs = ET.fromstring(svg).attrib
            view = attrs.get('viewBox', '').split()
            w, h = ((float(view[2]), float(view[3])) if view else
                    tuple(float(re.match(r'[0-9.]+', attrs[key])[0]) for key in ('width','height')))
            args = ['inkscape',str(source),'--export-type=png',
                    '--export-filename='+str(ROOT/(stem+'.png')),
                    '--export-width=256' if w >= h else '--export-height=256']
            subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    (ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__ == '__main__':
    main()
