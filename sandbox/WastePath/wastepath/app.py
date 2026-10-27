"""Standalone Tk workshop, with PiPath's teal desktop and bevelled silver panels."""
from collections import Counter
import json
import math
from pathlib import Path
import threading
import shutil
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox
import cv2
import numpy as np
from PIL import Image, ImageTk
from .camera import Camera
from .outputs import Controller, OutputConfig, OutputRule, default_config, load_config, save_config, validate_config
from .output_ui import OutputDialog, HEADER_PINS
from .bin_setup import BinSetup, SimulatedBin
from .model import LABELS, MIN_PHOTOS, Model, Sample, Prediction, SteadyGate, requirements
from .storage import save, load
from .vision import inspection_crop, shrink, to_lab, inspect, difference_mask

C = {"desk":"#008080","bg":"#C0C0C0","purple":"#704988","teal":"#19C1CA",
     "ink":"#000000","muted":"#3C3C3C","warn":"#FFFFE1","ok":"#007A3D"}
STEPS = ("Set up", "Teach", "Train", "Test", "Live", "Set up bin")
# Step 5 (the bin) sits after Train on screen; the other numbers stay as they were.
NAV_ORDER = (0, 1, 2, 5, 3, 4)
LIVE, BIN = 4, 5
THUMB_W, THUMB_H = 62, 46
GUIDES = (
    ("Photograph the empty table", "Aim the camera at a plain table with steady lighting, as in ML Camera. The whole picture is used. Clear the table and keep the camera fixed.\n\nPress Photograph empty table. The app averages 10 frames to learn the background. If outlines miss an item, reduce the threshold; if shadows appear, increase it."),
    ("Teach Waste and Recycling", "Take at least 10 photos of Waste, then 10 of Recycling. Turn or move the object between photos, with your hand out of view. You can keep adding photos: more items, sides and positions make it smarter.\n\nThe item name is optional. There is no people or hands training category."),
    ("Train the camera", "The computer measures colour and shape, then uses the same five-neighbour learning method as your original ML Camera.\n\nThe photo quiz is practice, not a measure of accuracy on new items. Start sorting after training, or use Test to record fresh examples."),
    ("Try fresh items", "Show an item that was not in the training photos. Record whether it is Waste, Recycling or an unknown item / empty table. Test never operates real GPIO.\n\nIf guesses are wrong, add more varied photos with the right category and train again."),
    ("Sort with the camera", "Default outputs: a recognised Recycling item opens the servo bin. Waste or an unrecognised item flashes the LED and keeps the servo at rest. An empty table turns the LED off.\n\nEnable real GPIO once to operate the connected hardware. You can change the category mappings, pins and servo angles in GPIO outputs."),
    ("Set up the bin", "The lid presses a push button when it is shut, like the BNTS smart bin. The Pi uses it to find the closed position, then you choose how far the lid opens.\n\nDisconnect power before wiring. Keep fingers clear of the lid while it moves."),
)


class App(tk.Tk):
    def __init__(self, data_dir, camera=None, demo=False):
        super().__init__()
        self.title("WastePath · BNTS machine learning lab")
        self.geometry("1160x760")
        self.minsize(1024,640)
        self.configure(bg=C["desk"])
        families = {name.lower(): name for name in tkfont.families(self)}
        self.ui_font = next((families[n.lower()] for n in ("DejaVu Sans", "Liberation Sans", "Helvetica") if n.lower() in families), "TkDefaultFont")
        self.mono_font = next((families[n.lower()] for n in ("DejaVu Sans Mono", "Liberation Mono", "Courier") if n.lower() in families), self.ui_font)
        self.option_add("*Font", (self.ui_font,10))
        self.data_dir = Path(data_dir)
        self.file = self.data_dir / "training.npz"
        self.output_file = self.data_dir / "outputs.json"
        output_config=default_config()
        self.output_load_error=None
        if self.output_file.exists():
            try: output_config=load_config(self.output_file)
            except (OSError,ValueError,TypeError,KeyError) as e: self.output_load_error=str(e)
        self.outputs=Controller(output_config)
        self.output_dialog=None
        self.samples, self.background = [], None
        self.model = None
        self.quiz = []
        self.test_records = []
        self.gate = SteadyGate()
        self.previous = None
        self.bg_frames = None
        self.frame = None
        self.frame_time = 0
        self.last_seq = None
        self.last_capture = 0
        self.observation = None
        self.calibrated = False
        self.prediction = Prediction(None,0,"Complete setup first")
        self.step = 0
        self.busy = False
        self.train_result = None
        self.bin = None
        self.retrain_needed = False
        self.bin_closing = None   # a set-up lid still closing; its pins are not free yet
        self.camera_index = tk.StringVar(value="auto" if camera is None else str(camera))
        self.demo = demo
        self.cam = Camera(camera,demo)
        self.label_var = tk.StringVar(value=LABELS[0])
        self.group_var = tk.StringVar()
        self.status = tk.StringVar(value="Welcome. Start by photographing the empty mat.")
        self.rule_var = tk.StringVar(value="Ask your teacher which clean items belong in each bin locally.")
        self.mask_view = tk.BooleanVar(value=False)
        self.threshold_var=tk.IntVar(value=22)
        self.load_error = None
        if self.file.exists():
            try: self.samples, self.background = load(self.file)
            except Exception as e: self.load_error = str(e)
        try:
            settings=json.loads((self.data_dir/"project.json").read_text())
            self.rule_var.set(settings["local_rules"])
            self.threshold_var.set(max(6,min(80,int(settings.get("threshold",22)))))
        except (OSError,ValueError,KeyError,TypeError): pass
        self._layout()
        self.show_step(0)
        if self.load_error:
            self.status.set(f"Saved examples could not be opened: {self.load_error}. They have not been changed.")
        if self.output_load_error:
            self.status.set("Saved GPIO mappings could not be read. Defaults are simulated; open GPIO outputs to correct them.")
        self.protocol("WM_DELETE_WINDOW",self.close)
        self.bind("<space>",self.space)
        self.after(100,self.tick)

    def text(self,parent,text,**kw):
        opts=dict(text=text,bg=C["bg"],fg=C["ink"],anchor="w",justify="left")
        opts.update(kw)
        return tk.Label(parent,**opts)

    def button(self,parent,text,command,**kw):
        return tk.Button(parent,text=text,command=command,bg=C["bg"],activebackground="#D4D0C8",
                         relief="raised",bd=2,padx=8,pady=5,**kw)

    def _layout(self):
        shell = tk.Frame(self,bg=C["bg"],bd=3,relief="raised")
        shell.pack(fill="both",expand=True,padx=12,pady=12)
        bar = tk.Canvas(shell,height=44,highlightthickness=0)
        bar.pack(fill="x")
        def title(e):
            bar.delete("all")
            a,b=(75,42,102),(18,169,177)
            for x in range(0,e.width,4):
                t=x/max(e.width,1); col="#"+"".join(f"{int(p+(q-p)*t):02x}" for p,q in zip(a,b))
                bar.create_rectangle(x,0,x+4,44,fill=col,outline=col)
            bar.create_text(16,22,text="WastePath",fill="white",font=(self.mono_font,18,"bold"),anchor="w")
            bar.create_text(e.width-16,22,text="BNTS | teach - test - improve",fill="white",anchor="e")
        bar.bind("<Configure>",title)
        nav=tk.Frame(shell,bg=C["bg"]); nav.pack(fill="x",padx=10,pady=8)
        self.nav=[None]*len(STEPS)
        for place,i in enumerate(NAV_ORDER):
            b=self.button(nav,f"{place+1}. {STEPS[i]}",lambda i=i:self.show_step(i))
            b.pack(side="left",padx=3); self.nav[i]=b
        self.button(nav,"New session",self.new_session).pack(side="right")
        self.button(nav,"Save",self.persist).pack(side="right",padx=5)
        self.button(nav,"GPIO outputs",self.show_outputs).pack(side="right",padx=5)
        if self.demo:
            self.text(shell,"SIMULATED CAMERA - coloured shapes demonstrate the workflow, not real rubbish accuracy.",bg=C["warn"]).pack(fill="x",padx=10)
        body=tk.Frame(shell,bg=C["bg"]); body.pack(fill="both",expand=True,padx=10,pady=5)
        body.columnconfigure(0,weight=3,minsize=450); body.columnconfigure(1,weight=2,minsize=340)
        body.rowconfigure(0,weight=1)
        left=tk.Frame(body,bg=C["bg"]); left.grid(row=0,column=0,sticky="nsew",padx=(0,10))
        self.preview=tk.Label(left,bg="#202020",bd=2,relief="sunken")
        self.preview.pack(fill="both",expand=True)
        self.result=self.text(left,"Connect a camera to begin",font=(self.ui_font,15,"bold"),wraplength=550,bg="white",padx=12,pady=12)
        self.result.pack(fill="x",pady=(8,0))
        self.detail=self.text(left,"",wraplength=560,pady=5)
        self.detail.pack(fill="x")
        self.output_status=tk.StringVar(value=self.outputs.state_text)
        self.text(left,"",textvariable=self.output_status,wraplength=550,fg=C["purple"],pady=4).pack(fill="x")
        output_buttons=tk.Frame(left,bg=C["bg"]); output_buttons.pack(fill="x")
        self.arm_button=self.button(output_buttons,"Enable real GPIO",self.arm_outputs,
                                    state="disabled" if self.demo else "normal")
        self.arm_button.pack(side="left")
        self.button(output_buttons,"Stop GPIO",self.stop_outputs,fg="#B00000").pack(side="left",padx=6)
        if self.demo:
            box=ttk.Combobox(left,state="readonly",values=["Empty table",*LABELS,"Unknown item"])
            box.set("Empty table"); box.pack(fill="x")
            box.bind("<<ComboboxSelected>>",lambda e:setattr(self.cam,"kind",box.get()))
            self.demo_box=box
        tk.Checkbutton(left,text="Computer view (changed pixels)",variable=self.mask_view,bg=C["bg"]).pack(anchor="w")
        right=tk.Frame(body,bg=C["bg"]); right.grid(row=0,column=1,sticky="nsew")
        canvas=tk.Canvas(right,bg=C["bg"],highlightthickness=0)
        scroll=ttk.Scrollbar(right,orient="vertical",command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right",fill="y"); canvas.pack(fill="both",expand=True)
        self.panel=tk.Frame(canvas,bg=C["bg"])
        panel_id=canvas.create_window((0,0),window=self.panel,anchor="nw")
        self.panel.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",lambda e:canvas.itemconfigure(panel_id,width=e.width))
        def wheel(e):
            if str(e.widget).startswith(str(right)):
                delta=(-1 if e.num==4 else 1) if e.num in (4,5) else (-1 if e.delta>0 else 1)
                canvas.yview_scroll(delta*3,"units")
        self.bind_all("<Button-4>",wheel); self.bind_all("<Button-5>",wheel); self.bind_all("<MouseWheel>",wheel)
        self.text(shell,"",textvariable=self.status,relief="sunken",bd=1,wraplength=1050,padx=8,pady=5).pack(fill="x",padx=8,pady=5)

    def show_step(self,step):
        if self.busy: return
        if 0<step<BIN and not self.calibrated:
            self.status.set("First photograph the empty mat, or check the saved table."); return
        if step in (3,LIVE) and self.model is None:
            self.status.set("Collect examples and train the model first."); return
        self.stop_outputs()
        self.release_bin()
        self.step=step; self.gate.reset()
        if self.model is not None: self.model.reset_prediction()
        for i,b in enumerate(self.nav): b.configure(relief="sunken" if i==step else "raised")
        for w in self.panel.winfo_children(): w.destroy()
        title,guide=GUIDES[step]
        self.text(self.panel,title,font=(self.ui_font,16,"bold"),fg=C["purple"],wraplength=350,pady=8).pack(fill="x")
        self.text(self.panel,guide,wraplength=350,pady=5).pack(fill="x")
        if step==0: self.setup_controls()
        elif step==1: self.teach_controls()
        elif step==2: self.train_controls()
        elif step==BIN: self.bin_controls()
        else: self.test_controls()

    def setup_controls(self):
        self.text(self.panel,"Your local bin rules:",pady=6).pack(fill="x")
        tk.Entry(self.panel,textvariable=self.rule_var).pack(fill="x",pady=4)
        row=tk.Frame(self.panel,bg=C["bg"]); row.pack(fill="x",pady=8)
        self.text(row,"USB camera number:").pack(side="left")
        tk.Entry(row,textvariable=self.camera_index,width=5).pack(side="left",padx=5)
        self.button(row,"Reconnect",self.reconnect).pack(side="left")
        self.button(self.panel,"Photograph empty table",self.calibrate).pack(fill="x",pady=6)
        if self.background is not None and self.samples:
            self.button(self.panel,"Check saved table (empty mat)",self.check_saved).pack(fill="x",pady=6)
        tk.Scale(self.panel,from_=6,to=80,orient="horizontal",variable=self.threshold_var,
                 label="Background threshold (default 22)",bg=C["bg"]).pack(fill="x",pady=6)
        self.button(self.panel,"Next: teach the camera →",lambda:self.show_step(1)).pack(fill="x",pady=6)

    def teach_controls(self):
        self.text(self.panel,"Choose a bin, then take photos:",pady=4).pack(fill="x")
        self.cards={}
        for label,name in enumerate(LABELS):
            card=tk.Canvas(self.panel,width=340,height=106,bg=C["bg"],highlightthickness=0,cursor="hand2")
            card.pack(fill="x",pady=3)
            card.bind("<Button-1>",lambda e,name=name:self.choose_bin(name))
            self.cards[label]=card
        self.text(self.panel,"Item name (optional), for example bottle, cup or wrapper:",wraplength=350).pack(fill="x",pady=(6,0))
        tk.Entry(self.panel,textvariable=self.group_var).pack(fill="x",pady=4)
        self.take_button=self.button(self.panel,"",self.capture,font=(self.ui_font,12,"bold"))
        self.take_button.pack(fill="x",pady=6)
        self.counts=self.text(self.panel,"",wraplength=350,bg="white",pady=8,padx=8)
        self.counts.pack(fill="x")
        row=tk.Frame(self.panel,bg=C["bg"]); row.pack(fill="x",pady=6)
        self.button(row,"Undo last photo",self.undo).pack(side="left",fill="x",expand=True)
        self.button(row,"Delete this named set",self.delete_group).pack(side="left",fill="x",expand=True,padx=(6,0))
        self.next_button=self.button(self.panel,"Next: train →",lambda:self.show_step(2))
        self.next_button.pack(fill="x",pady=6)
        self.update_counts()

    def choose_bin(self,name):
        if name!=self.label_var.get():
            self.label_var.set(name); self.group_var.set("")
        self.update_counts()

    def update_counts(self):
        if self.step!=1: return
        chosen=LABELS.index(self.label_var.get())
        totals=[sum(s.label==c for s in self.samples) for c in range(len(LABELS))]
        self.thumb_images=[]
        for label,name in enumerate(LABELS):
            card=self.cards[label]; card.delete("all")
            n=totals[label]; picked=label==chosen
            card.create_rectangle(2,2,338,104,fill="white" if picked else "#DCDCDC",
                                  outline=C["purple"] if picked else "#808080",width=3 if picked else 1)
            card.create_text(12,16,anchor="w",text=("● " if picked else "○ ")+name,
                             font=(self.ui_font,12,"bold"),fill=C["purple"] if picked else C["ink"])
            done=n>=MIN_PHOTOS
            count=f"{n} photos ✓" if done else f"{n} / {MIN_PHOTOS} photos"
            card.create_text(328,16,anchor="e",text=count,fill=C["ok"] if done else C["ink"])
            card.create_rectangle(12,30,328,42,fill="#FFFFFF",outline="#808080")
            card.create_rectangle(12,30,12+316*min(n,MIN_PHOTOS)/MIN_PHOTOS,42,
                                  fill=C["ok"] if done else C["teal"],outline="")
            if n>MIN_PHOTOS:
                card.create_text(170,36,text=f"+{n-MIN_PHOTOS} extra",fill="white",font=(self.ui_font,8,"bold"))
            recent=[s for s in self.samples if s.label==label][-5:]
            for k in range(5):
                x=12+k*(THUMB_W+3); y=50
                sample=recent[k] if k<len(recent) else None
                if sample is not None and sample.thumb is not None:
                    card.create_image(x,y,image=sample.thumb,anchor="nw")
                    self.thumb_images.append(sample.thumb)
                else:
                    card.create_rectangle(x,y,x+THUMB_W,y+THUMB_H,fill="#F0F0F0",outline="#A0A0A0",dash=(2,2))
                    card.create_text(x+THUMB_W/2,y+THUMB_H/2,text="✓" if sample is not None else "",fill="#808080")
        name=LABELS[chosen]
        left=MIN_PHOTOS-totals[chosen]
        self.take_button.configure(text=f"Take a {name} photo  [Space]")
        if left>0:
            tip=f"{name}: {left} more photo{'s' if left!=1 else ''} to go. Turn or move the item each time."
        elif requirements(self.samples):
            other=LABELS[1-chosen]
            tip=f"{name} has enough photos. Choose {other} next (click its box)."
        else:
            tip=("Both bins are ready to train. ✓\n\nWant it smarter? Keep adding photos: new items, "
                 "other sides, different places on the table. Then train again.")
        groups=Counter((s.label,s.group) for s in self.samples if s.label==chosen and s.group!=LABELS[s.label])
        if groups:
            tip+="\n\nNamed items: "+", ".join(f"{g} ({n})" for (c,g),n in groups.items())
        self.counts.configure(text=tip)
        ready=not requirements(self.samples)
        self.next_button.configure(text="Next: train →" if ready else "Next: train (needs 10 of each) →",
                                   default="active" if ready else "normal")

    def train_controls(self):
        missing=requirements(self.samples)
        totals=[sum(s.label==c for s in self.samples) for c in range(len(LABELS))]
        self.text(self.panel,"\n".join(missing) if missing else
                  "Photos ready: "+", ".join(f"{n} {name}" for name,n in zip(LABELS,totals)),wraplength=350,pady=8).pack(fill="x")
        self.train_button=self.button(self.panel,"Train again" if self.quiz else "Train and quiz",self.train,state="disabled" if missing else "normal")
        self.train_button.pack(fill="x",pady=6)
        if self.quiz:
            self.text(self.panel,"Photo quiz (practice, not a fresh-item test):",pady=4).pack(fill="x")
            for r in self.quiz:
                box=tk.Frame(self.panel,bg="white",bd=1,relief="sunken"); box.pack(fill="x",pady=3)
                share=r['correct']/max(r['total'],1)
                self.text(box,f"{r['group']}: {r['correct']} of {r['total']} photos guessed right",bg="white",padx=6).pack(fill="x")
                bar=tk.Canvas(box,height=10,bg="white",highlightthickness=0); bar.pack(fill="x",padx=6)
                bar.bind("<Configure>",lambda e,b=bar,share=share:(b.delete("all"),
                         b.create_rectangle(0,0,e.width*share,10,fill=C["ok"] if share>=.9 else C["teal"],outline="")))
                tip="More photos would help this bin." if share<.9 else "Looking good."
                self.text(box,tip,bg="white",fg=C["muted"],padx=6).pack(fill="x")
                self.button(box,f"+ Add more {r['group']} photos",lambda name=r['group']:self.more_photos(name)).pack(fill="x",padx=6,pady=4)
            if self.model is not None:
                self.button(self.panel,"Next: set up the bin →",lambda:self.show_step(BIN)).pack(fill="x",pady=6)
                self.button(self.panel,"Start sorting (Live) →",lambda:self.show_step(LIVE)).pack(fill="x",pady=3)
                self.button(self.panel,"Optional: fresh-item test",lambda:self.show_step(3)).pack(fill="x",pady=3)
        else:
            self.button(self.panel,"+ Add more photos first",lambda:self.show_step(1)).pack(fill="x",pady=3)

    def more_photos(self,name):
        self.label_var.set(name); self.group_var.set("")
        self.show_step(1)
        self.status.set(f"Add more {name} photos. Afterwards, train again.")

    def test_controls(self):
        self.text(self.panel,"Local rules: "+self.rule_var.get(),wraplength=350,bg=C["warn"],pady=6).pack(fill="x")
        self.text(self.panel,"Record the real category of this fresh view:",wraplength=350,pady=8).pack(fill="x")
        for label in range(3):
            self.button(self.panel,LABELS[label] if label<2 else "Unknown item / empty table",lambda label=label:self.record_test(label)).pack(fill="x",pady=3)
        self.test_report=self.text(self.panel,"",wraplength=350,bg="white",pady=8)
        self.test_report.pack(fill="x",pady=8)
        self.update_report()
        self.button(self.panel,"Clear test results",self.clear_tests).pack(fill="x",pady=3)
        self.button(self.panel,"+ Add more photos",lambda:self.show_step(1)).pack(fill="x",pady=6)
        self.text(self.panel,"Similarity votes are not an accuracy percentage. Only the fresh tests above show how this model behaved. This is a teaching model; check uncertain items against local recycling guidance.",wraplength=350,pady=6).pack(fill="x")

    # ---------------- Bin set-up: the hardware calibration ----------------
    def servo_rule(self):
        rules=[r for r in self.outputs.config.rules if r.kind=="servo"]
        return rules[0] if rules else OutputRule(1,"servo",18,90,0)

    def bin_controls(self):
        rule=self.servo_rule()
        self.bin_vars={"servo":tk.StringVar(value=str(rule.pin)),
                       "button":tk.StringVar(value=str(rule.button_pin or 23)),
                       "closes":tk.StringVar(value="up" if rule.rest_angle>rule.active_angle else "down"),
                       "label":tk.StringVar(value=LABELS[rule.label])}
        if self.demo:
            self.text(self.panel,"DEMO: a pretend lid. Its button presses at 120°, so choose 'towards 180°'.",
                      bg=C["warn"],wraplength=350,pady=4).pack(fill="x")
        form=tk.Frame(self.panel,bg=C["bg"]); form.pack(fill="x",pady=4)
        self.text(form,"Lid opens for:").grid(row=0,column=0,sticky="w")
        ttk.Combobox(form,textvariable=self.bin_vars["label"],values=LABELS,state="readonly",width=10).grid(row=0,column=1,sticky="w",pady=2)
        self.text(form,"Servo signal GPIO:").grid(row=1,column=0,sticky="w")
        ttk.Combobox(form,textvariable=self.bin_vars["servo"],values=tuple(HEADER_PINS),width=5).grid(row=1,column=1,sticky="w",pady=2)
        self.text(form,"Closed button GPIO:").grid(row=2,column=0,sticky="w")
        ttk.Combobox(form,textvariable=self.bin_vars["button"],values=tuple(HEADER_PINS),width=5).grid(row=2,column=1,sticky="w",pady=2)
        self.text(form,"To close, the servo turns:").grid(row=3,column=0,sticky="w")
        turn=tk.Frame(form,bg=C["bg"]); turn.grid(row=3,column=1,sticky="w")
        for value,text in (("up","towards 180°"),("down","towards 0°")):
            tk.Radiobutton(turn,text=text,value=value,variable=self.bin_vars["closes"],bg=C["bg"]).pack(anchor="w")
        self.bin_dial=tk.Canvas(self.panel,width=340,height=140,bg="white",highlightthickness=1,highlightbackground="#808080")
        self.bin_dial.pack(fill="x",pady=4)
        self.bin_note=self.text(self.panel,"",wraplength=350,bg="white",pady=6,padx=6)
        self.bin_note.pack(fill="x")
        self.bin_buttons={}
        def add(key,text,command,parent=None,**pack):
            b=self.button(parent or self.panel,text,command); b.pack(**(pack or {"fill":"x","pady":3}))
            self.bin_buttons[key]=b
        add("find","1. Find the closed position",self.bin_find)
        row=tk.Frame(self.panel,bg=C["bg"]); row.pack(fill="x",pady=3)
        add("more","2. Open 5° more",lambda:self.bin_open(1),row,side="left",fill="x",expand=True)
        add("less","5° less",lambda:self.bin_open(-1),row,side="left",padx=(6,0))
        add("test","3. Test: open, then close",self.bin_test)
        add("save","4. Save the bin settings",self.bin_save)
        add("stop","Stop and close the lid",self.release_bin)
        self.bin_wiring=self.text(self.panel,"",bg=C["warn"],wraplength=350,pady=6,padx=6)
        self.bin_wiring.pack(fill="x",pady=4)
        for var in ("servo","button"):
            self.bin_vars[var].trace_add("write",lambda *_:self.show_bin_wiring())
        self.show_bin_wiring()
        self.draw_bin()

    def show_bin_wiring(self):
        def physical(var):
            try: return f"physical pin {HEADER_PINS[int(self.bin_vars[var].get())]}"
            except (ValueError,KeyError): return "choose a GPIO from 2 to 27"
        self.bin_wiring.configure(text=(
            f"Wiring (power off first):\n• Servo signal → GPIO{self.bin_vars['servo'].get()} ({physical('servo')}). "
            "Servo power from its own 5 V supply; join its GND to the Pi's GND.\n"
            f"• Push button: one leg → GPIO{self.bin_vars['button'].get()} ({physical('button')}), "
            "other leg → GND (for example physical pin 14). No resistor needed. Never wire the button to 5 V.\n"
            "• Fix the button where the shut lid presses it."))

    def bin_settings(self):
        try:
            servo,button=int(self.bin_vars["servo"].get()),int(self.bin_vars["button"].get())
            label=LABELS.index(self.bin_vars["label"].get())
        except ValueError:
            raise ValueError("Choose GPIO numbers for the servo and the button")
        # Check the pins against the other output before touching hardware.
        other=[r for r in self.outputs.config.rules if r.label!=label]
        trial=OutputRule(label,"servo",servo,0.,90.,button)
        validate_config(OutputConfig(other+[trial]))
        return servo,button,label

    def bin_find(self):
        if self.bin is None:
            try:
                servo,button,_=self.bin_settings()
            except ValueError as e:
                self.status.set(f"Check the bin settings: {e}"); return
            self.stop_outputs()
            if self.lids_busy():
                self.status.set("Wait a moment: the lid is still closing."); return
            rule=self.servo_rule()
            closes_up=self.bin_vars["closes"].get()=="up"
            start=rule.active_angle if rule.button_pin and (rule.rest_angle>rule.active_angle)==closes_up else 90
            try:
                factory=SimulatedBin() if self.demo else None
                if factory is None:
                    import gpiozero as factory
                self.bin=BinSetup(factory,servo,button,closes_up,start)
            except Exception as e:
                self.bin=None
                self.status.set(f"The servo or button could not start: {e}"); return
        if self.bin.find_closed():
            self.status.set("Finding the closed position: the lid closes slowly until it presses the button…")
        else:
            self.status.set(self.bin.lid.fault)
        self.draw_bin()

    def bin_open(self,steps):
        if self.bin is None or self.bin.closed_angle is None:
            self.status.set("First press 1. Find the closed position."); return
        self.bin.open_by(steps)
        self.status.set(f"Lid open at {self.bin.open_angle:g}°. Keep pressing Open 5° more until it opens far enough.")
        self.draw_bin()

    def bin_test(self):
        if self.bin is None or not self.bin.test_cycle():
            self.status.set("Find the closed position and open the lid first."); return
        self.status.set("Testing: the lid stays open for 2 seconds, then closes until the button presses.")

    def bin_save(self):
        if self.bin is None or not self.bin.ready:
            self.status.set("Find the closed position and set how far it opens first."); return
        label=LABELS.index(self.bin_vars["label"].get())
        rules=[r for r in self.outputs.config.rules if r.label!=label]+[self.bin.rule(label)]
        config=OutputConfig(sorted(rules,key=lambda r:r.label))
        closed,opened,button=self.bin.closed_angle,self.bin.open_angle,self.bin.button_pin
        self.release_bin()
        if self.apply_output_config(config):
            self.show_step(LIVE if self.model is not None else BIN)
            self.status.set(f"Bin saved: closed at {closed:g}°, open at {opened:g}°, button on GPIO{button}. "
                            +("Start sorting: press Enable real GPIO." if self.model is not None else "Train the camera, then sort in Live."))

    def lids_busy(self):
        if self.bin_closing is not None and not self.bin_closing.busy: self.bin_closing=None
        return self.bin_closing is not None or self.outputs.lid_closing

    def release_bin(self):
        if self.bin is not None:
            self.bin_closing=self.bin.release()
            self.bin=None
            if self.step==BIN and hasattr(self,"bin_dial"): self.draw_bin()

    def draw_bin(self):
        if self.step!=BIN or not hasattr(self,"bin_dial"): return
        d=self.bin_dial; d.delete("all")
        w=max(int(d.winfo_width()),340); cx,cy,r=w//2,124,100
        d.create_arc(cx-r,cy-r,cx+r,cy+r,start=0,extent=180,style="arc",outline="#A0A0A0",width=2)
        for a in range(0,181,30):
            d.create_text(cx+(r-14)*math.cos(math.radians(a)),cy-6-(r-18)*math.sin(math.radians(a)),text=f"{a}",fill="#808080",font=(self.ui_font,7))
        b=self.bin
        def ray(angle,colour,width):
            d.create_line(cx,cy,cx+r*math.cos(math.radians(angle)),cy-r*math.sin(math.radians(angle)),fill=colour,width=width)
        if b is not None and b.closed_angle is not None:
            ray(b.closed_angle,C["purple"],3)
            d.create_text(10,14,anchor="w",text=f"— closed {b.closed_angle:g}°",fill=C["purple"],font=(self.ui_font,9,"bold"))
        if b is not None and b.open_angle is not None:
            ray(b.open_angle,C["ok"],3)
            d.create_text(10,32,anchor="w",text=f"— open {b.open_angle:g}°",fill=C["ok"],font=(self.ui_font,9,"bold"))
        if b is not None:
            ray(b.lid.position,"#000000",4)
            d.create_oval(cx-6,cy-6,cx+6,cy+6,fill="#000000")
            pressed=b.pressed
            d.create_oval(10,cy-14,26,cy+2,fill=C["ok"] if pressed else "white",outline="#000000")
            d.create_text(32,cy-6,anchor="w",text="Button pressed" if pressed else "Button up",font=(self.ui_font,8))
            d.create_text(w-10,14,anchor="e",text=f"Servo {b.lid.position:g}° · {b.lid.state}",font=(self.ui_font,9))
        else:
            d.create_text(cx,cy-40,text="Servo off. Press 1. Find the closed position.",fill="#808080")
        # Explain the next thing to do.
        if b is None: note="Wire the servo and button, choose their pins, then press 1."
        elif b.homing: note="Closing slowly… it stops when the lid presses the button."
        elif b.lid.fault: note="⚠ "+b.lid.fault
        elif b.closed_angle is None: note="The button didn't press. Check its wires and which way the lid closes, then press 1 again."
        elif b.open_angle is None: note=f"✓ Closed at {b.closed_angle:g}°. Now press 2. Open 5° more until the lid opens far enough."
        else: note=f"Opens to {b.open_angle:g}° ({abs(b.closed_angle-b.open_angle):g}° from closed). Try 3. Test, then 4. Save."
        self.bin_note.configure(text=note)
        ready=b is not None and b.ready
        for key,on in (("more",b is not None and b.closed_angle is not None),("less",b is not None and b.open_angle is not None),
                       ("test",ready),("save",ready),("stop",b is not None)):
            self.bin_buttons[key].configure(state="normal" if on else "disabled")

    def fresh(self):
        if self.frame is None or time.monotonic()-self.frame_time>1:
            self.status.set("Wait for a fresh camera picture.")
            return False
        return True

    def reconnect(self):
        text=self.camera_index.get().strip().lower()
        try: index=None if text in ("","auto") else int(text); assert index is None or index>=0
        except (ValueError,AssertionError): self.status.set("Use auto, or a camera number such as 0 or 1."); return
        self.stop_outputs()
        self.cam.close(); self.cam=Camera(index,self.demo)
        self.frame=None; self.last_seq=None; self.previous=None; self.calibrated=False; self.bg_frames=None
        self.gate.reset(); self.show_step(0)
        self.status.set("Reconnected. Check the empty mat before using saved examples.")

    def calibrate(self):
        if not self.fresh(): return
        if self.load_error and not messagebox.askyesno("Replace unreadable training", "The saved training could not be read. Replace it with a new session?"): return
        if self.samples and not messagebox.askyesno("New table photo", "A new table photo clears the old training and tests. Continue?"): return
        self.stop_outputs()
        if self.load_error and self.file.exists():
            backup=self.file.with_name(f"training-backup-{time.time_ns()}.npz")
            try: shutil.copy2(self.file,backup)
            except OSError as e:
                self.status.set(f"Could not preserve previous training: {e}"); return
        self.load_error=None
        self.model=None; self.calibrated=False; self.bg_frames=[]
        self.previous=None; self.gate.reset()
        self.status.set("Learning the empty table: 0/10 frames. Keep it clear…")

    def check_saved(self):
        if not self.fresh() or self.background is None: return
        small=shrink(inspection_crop(self.frame))
        mask=difference_mask(small,self.background,self.threshold_var.get())
        raw=float(np.mean(np.abs(to_lab(small)-self.background)))
        if (mask>0).mean()>.03 or raw>8:
            self.status.set("The table view changed. Clear the mat; if the camera moved, take a new table photo."); return
        self.calibrated=True; self.previous=None; self.gate.reset()
        self.status.set("Saved table checked. You can add examples or retrain the saved measurements.")

    def invalidate(self):
        self.stop_outputs()
        self.model=None; self.quiz=[]; self.test_records=[]; self.gate.reset()
        self.persist_tests()

    def capture(self):
        if self.busy or not self.calibrated or not self.fresh(): return
        name=self.group_var.get().strip() or self.label_var.get()
        if len(name)>80:
            self.status.set("Use an item name of up to 80 characters."); return
        if len(self.samples)>=480: self.status.set("Example limit reached. Remove old sets to continue."); return
        label=LABELS.index(self.label_var.get())
        if any(s.group==name and s.label!=label for s in self.samples):
            self.status.set("That name already belongs to another category. Use a different item name."); return
        o=self.observation
        if o is None or o.feature is None:
            self.status.set("I can't see an object. Put it on the table and take your hand away."); return
        if o.reason:
            self.status.set(o.reason); return
        now=time.monotonic()
        if now-self.last_capture<.35: return
        self.last_capture=now
        self.samples.append(Sample(o.feature.copy(),label,name,self.thumbnail(o.contour)))
        self.retrain_needed=self.retrain_needed or self.model is not None
        self.invalidate(); saved=self.persist()
        n=sum(s.label==label and s.group==name for s in self.samples)
        if saved: self.status.set(f"{name}: {n} photos. Turn or move it before the next photo.")
        count=sum(s.label==label for s in self.samples)
        if count==MIN_PHOTOS:
            if label==0 and sum(s.label==1 for s in self.samples)<MIN_PHOTOS:
                self.label_var.set(LABELS[1]); self.group_var.set("")
                self.status.set("Waste photos done. Now take 10 Recycling photos.")
            elif not requirements(self.samples):
                self.status.set("Both bins have 10 photos. Press Next: train, or keep adding photos.")
        elif self.retrain_needed and saved:
            self.status.set(f"{name}: {n} photos. Train again to use the new photos.")
        self.update_counts()

    def thumbnail(self,contour):
        """A small picture of the item for the Teach screen (never saved to disk)."""
        try:
            x,y,w,h=(2*v for v in cv2.boundingRect(contour))
            pad=max(w,h)//6
            crop=self.frame[max(0,y-pad):y+h+pad,max(0,x-pad):x+w+pad]
            scale=min(THUMB_W/crop.shape[1],THUMB_H/crop.shape[0])
            small=cv2.resize(crop,(max(1,int(crop.shape[1]*scale)),max(1,int(crop.shape[0]*scale))),interpolation=cv2.INTER_AREA)
            tile=np.full((THUMB_H,THUMB_W,3),40,np.uint8)
            top,left=(THUMB_H-small.shape[0])//2,(THUMB_W-small.shape[1])//2
            tile[top:top+small.shape[0],left:left+small.shape[1]]=small
            return ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(tile,cv2.COLOR_BGR2RGB)))
        except (cv2.error,ValueError,ZeroDivisionError,tk.TclError):
            return None

    def undo(self):
        if self.samples:
            self.samples.pop(); self.invalidate(); self.update_counts(); self.persist()

    def delete_group(self):
        label=LABELS.index(self.label_var.get()); name=self.group_var.get().strip() or self.label_var.get()
        if name and messagebox.askyesno("Delete set",f"Delete all photos measured for {name}?"):
            self.samples=[s for s in self.samples if (s.label,s.group)!=(label,name)]
            self.invalidate(); self.update_counts(); self.persist()

    def train(self):
        missing=requirements(self.samples)
        if missing: self.status.set("More examples needed: "+"; ".join(missing)); return
        self.stop_outputs()
        self.busy=True; self.train_result=None; self.train_button.configure(state="disabled")
        self.status.set("Training and running the original photo quiz…")
        samples=list(self.samples)
        def work():
            try: self.train_result=(Model(samples),Model.training_quiz(samples),None)
            except Exception as e: self.train_result=(None,[],str(e))
        threading.Thread(target=work,daemon=True).start()

    def record_test(self,label):
        if not self.fresh() or self.model is None: return
        now=time.monotonic()
        if now-self.last_capture<1: return
        self.last_capture=now
        self.test_records.append({"actual":label,"predicted":self.prediction.label,"reason":self.prediction.reason})
        self.update_report(); self.persist_tests()
        self.status.set("Fresh test recorded. Remove it and try a different item or scene.")

    def update_report(self):
        lines=[]
        for label,name in enumerate((*LABELS,"Unknown / empty")):
            rows=[r for r in self.test_records if r['actual']==label]
            good=sum(r['predicted']==label for r in rows) if label<2 else 0
            withheld=sum(r['predicted'] is None for r in rows)
            wrong=len(rows)-good-withheld
            lines.append(f"{name}: {len(rows)} tests\n{good} correct bin · {withheld} withheld · {wrong} wrong bin")
        self.test_report.configure(text="\n\n".join(lines))

    def clear_tests(self):
        self.test_records=[]; self.update_report(); self.persist_tests()

    def persist_tests(self):
        try:
            self.data_dir.mkdir(parents=True,exist_ok=True)
            (self.data_dir/"fresh-tests.json").write_text(json.dumps(self.test_records,indent=2))
        except OSError as e: self.status.set(f"Could not save test results: {e}")

    def persist(self):
        try:
            self.data_dir.mkdir(parents=True,exist_ok=True)
            if self.background is not None: save(self.file,self.samples,self.background)
            (self.data_dir/"project.json").write_text(json.dumps({"local_rules":self.rule_var.get(),"threshold":self.threshold_var.get()},indent=2))
            self.status.set("Saved measurements on this computer. No camera photos were saved.")
            return True
        except (OSError,ValueError) as e:
            self.status.set(f"Could not save: {e}"); return False

    def new_session(self):
        if self.busy:
            self.status.set("Wait for training to finish before starting a new session."); return
        self.stop_outputs()
        if not messagebox.askyesno("New session", "Delete this session's saved examples and test results? This cannot be undone."): return
        self.samples=[]; self.background=None; self.model=None; self.quiz=[]; self.test_records=[]; self.retrain_needed=False
        self.calibrated=False; self.bg_frames=None; self.gate.reset(); self.previous=None
        try:
            for name in ("training.npz","fresh-tests.json","project.json"):
                (self.data_dir/name).unlink(missing_ok=True)
        except OSError as e: self.status.set(f"Some saved files could not be deleted: {e}")
        self.show_step(0)

    def space(self,event):
        if isinstance(self.focus_get(),(tk.Entry,ttk.Combobox)): return
        if self.step==1: self.capture()
        return "break"

    def tick(self):
        if self.train_result is not None:
            self.model,self.quiz,error=self.train_result
            if not error: self.retrain_needed=False
            self.train_result=None; self.busy=False; self.gate.reset(); self.test_records=[]
            needs_bin=not self.demo and any(r.kind=="servo" and not r.button_pin for r in self.outputs.config.rules)
            self.show_step(2 if error else BIN if needs_bin else LIVE)
            self.status.set(f"Training failed: {error}" if error else
                            "Training finished. Next: set up the bin's servo and closed button." if needs_bin else
                            "Training finished. Sorting is ready; enable real GPIO to operate the bin and LED.")
        latest,error=self.cam.read()
        now=time.monotonic()
        if latest is None or now-latest[1]>1:
            self.gate.reset(); self.previous=None; self.observation=None
            if self.bg_frames is not None:
                self.bg_frames=None
                self.status.set("Table capture interrupted. Reconnect the camera and photograph it again.")
            if self.model is not None: self.model.reset_prediction()
            self.outputs.update(None)
            self.prediction=Prediction(None,0,"Camera unavailable: no bin choice")
            self.result.configure(text=self.prediction.reason,fg=C["purple"])
            self.detail.configure(text=error or "Waiting for a fresh camera frame")
        elif latest[0]!=self.last_seq:
            self.last_seq,self.frame_time,self.frame=latest
            roi=self.frame
            if self.bg_frames is not None:
                self.bg_frames.append(to_lab(shrink(roi)))
                self.status.set(f"Learning the empty table: {len(self.bg_frames)}/10 frames…")
                if len(self.bg_frames)>=10:
                    self.background=np.mean(self.bg_frames,axis=0).astype(np.float32)
                    self.bg_frames=None; self.samples=[]; self.quiz=[]; self.test_records=[]
                    self.previous=None; self.calibrated=True
                    if self.persist(): self.status.set("Empty table learned. Next: take 10 Waste photos and 10 Recycling photos.")
            o=None
            if self.calibrated and self.background is not None:
                o,self.previous=inspect(roi,self.background,self.previous,self.threshold_var.get())
                self.observation=o
            p=Prediction(None,0,"Train the camera before choosing a bin")
            raw=None
            if self.model is not None and o is not None and self.step>=3:
                raw=self.model.predict(o.feature)
                p=self.gate.apply(raw,o.reason,now=now)
            self.prediction=p
            # Hardware uses only fresh, stable LIVE predictions, never Test or a settings dialog.
            self.outputs.update(p.label if self.step==4 and self.calibrated and
                                not self.busy and self.output_dialog is None else None,
                                rejected=bool(self.step==4 and self.output_dialog is None and
                                              not self.busy and o is not None and o.feature is not None and
                                              raw is not None and raw.label is None))
            text=LABELS[p.label].upper() if p.label is not None else p.reason
            self.result.configure(text=text,fg=C["ok"] if p.label==1 else C["purple"])
            self.detail.configure(text=(f"Similarity vote: {p.similarity:.0%} (not a probability)" if p.similarity else "Whole camera image, as in ML Camera."))
            view=self.frame.copy()
            if self.mask_view.get() and o is not None:
                m=difference_mask(shrink(roi),self.background,self.threshold_var.get())
                view=cv2.resize(cv2.cvtColor(m,cv2.COLOR_GRAY2BGR),(640,480))
            if o is not None and o.contour is not None:
                contour=(o.contour*2).astype(np.int32)
                colour=(70,200,70) if p.label==1 else (50,180,240)
                cv2.drawContours(view,[contour],-1,colour,3)
            width=max(100,self.preview.winfo_width()-8); height=max(100,self.preview.winfo_height()-8)
            scale=min(width/640,height/480)
            image=Image.fromarray(cv2.cvtColor(view,cv2.COLOR_BGR2RGB)).resize((int(640*scale),int(480*scale)))
            self.photo=ImageTk.PhotoImage(image)
            self.preview.configure(image=self.photo)
        self.refresh_outputs()
        if self.bin is not None: self.draw_bin()
        self.after(120,self.tick)

    def show_outputs(self):
        if self.output_dialog is not None:
            self.output_dialog.lift(); return
        self.stop_outputs()
        self.output_dialog=OutputDialog(self)

    def apply_output_config(self,config):
        self.stop_outputs()
        try:
            validate_config(config)
            save_config(self.output_file,config)
            self.outputs.configure(config)
            self.output_load_error=None
        except (ValueError,TypeError,OSError) as e:
            self.status.set(f"Could not save GPIO mappings: {e}"); return False
        self.refresh_outputs()
        return True

    def refresh_outputs(self):
        text=self.outputs.state_text
        self.output_status.set(text)
        can_arm=(not self.demo and self.step==4 and self.model is not None and
                 self.calibrated and not self.busy and self.output_dialog is None and
                 not self.outputs.armed and not self.output_load_error and
                 self.frame is not None and time.monotonic()-self.frame_time<=1)
        self.arm_button.configure(state="normal" if can_arm else "disabled")

    def arm_outputs(self):
        if self.demo:
            self.status.set("The demo simulates outputs and cannot enable real GPIO."); return
        if (self.step!=4 or self.model is None or not self.calibrated or self.busy or
                self.output_dialog is not None):
            self.status.set("Train and test first, then open Live to enable real GPIO."); return
        if not self.fresh(): return
        if self.output_load_error:
            self.status.set("Correct and save the GPIO mappings before enabling hardware."); return
        if self.lids_busy():
            self.status.set("Wait a moment: the lid is still closing."); return
        self.gate.reset()
        self.model.reset_prediction()
        if self.outputs.arm():
            self.status.set("Real GPIO enabled. Outputs wait for a fresh, steady Live decision.")
        else:
            self.status.set("GPIO stayed off: "+self.outputs.error)
        self.refresh_outputs()

    def stop_outputs(self):
        self.outputs.disarm()
        self.gate.reset()
        if hasattr(self,"output_status"): self.refresh_outputs()

    def report_callback_exception(self,*args):
        # Tk normally continues after a failed callback; release hardware first.
        if hasattr(self,"outputs"): self.outputs.disarm()
        super().report_callback_exception(*args)

    def close(self):
        try:
            self.release_bin()
            self.outputs.close()
            lid=self.bin_closing
            if lid is not None and not lid.join(5): lid.stop_now()
        finally:
            self.cam.close()
            self.destroy()
