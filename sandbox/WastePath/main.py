#!/usr/bin/env python3
"""Start the standalone WastePath classroom workshop."""
import argparse
from pathlib import Path
import os
import signal
from wastepath.app import App

def main():
    parser=argparse.ArgumentParser(description="WastePath: teach a Pi camera waste vs recycling")
    parser.add_argument("--camera",type=int,default=0,help="USB camera number, normally 0")
    parser.add_argument("--demo",action="store_true",help="Use synthetic shapes without a webcam")
    parser.add_argument("--data-dir",type=Path,default=Path(os.environ.get("WASTEPATH_HOME",Path.home()/"WastePath")))
    args=parser.parse_args()
    if args.camera<0: parser.error("camera must be zero or positive")
    # Demo measurements never mix with a real camera session by default.
    folder=args.data_dir/"demo" if args.demo else args.data_dir
    app=App(folder,args.camera,args.demo)
    signal.signal(signal.SIGTERM,lambda *_: app.close())
    try:
        app.mainloop()
    except KeyboardInterrupt:
        app.close()
    finally:
        app.outputs.close()
        app.cam.close()

if __name__=="__main__": main()
