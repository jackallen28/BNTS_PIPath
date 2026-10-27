"""Standalone Tk workshop, with PiPath's teal desktop and bevelled silver panels."""
from collections import Counter
import json
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
from .outputs import Controller, default_config, load_config, save_config, validate_config
from .output_ui import OutputDialog
from .model import LABELS, MIN_PHOTOS, Model, Sample, Prediction, SteadyGate, requirements
from .storage import save, load
from .vision import inspection_crop, shrink, to_lab, inspect, difference_mask

C = {"desk":"#008080","bg":"#C0C0C0","purple":"#704988","teal":"#19C1CA",
     "ink":"#000000","muted":"#3C3C3C","warn":"#FFFFE1","ok":"#007A3D"}
STEPS = ("Set up", "Teach", "Train", "Test", "Live")
GUIDES = (
    ("Photograph the empty table", "Aim the camera at a plain table with steady lighting, as in ML Camera. The whole picture is used. Clear the table and keep the camera fixed.\n\nPress Photograph empty table. The app averages 10 frames to learn the background. If outlines miss an item, reduce the threshold; if shadows appear, increase it."),
    ("Teach Waste and Recycling", "Take 10 photos of Waste, then 10 of Recycling. Turn or move the object between photos, with your hand out of view. Include different items if you want it to learn more examples.\n\nThe item name is optional. There is no people or hands training category."),
    ("Train the camera", "The computer measures colour and shape, then uses the same five-neighbour learning method as your original ML Camera.\n\nThe photo quiz is practice, not a measure of accuracy on new items. Start sorting after training, or use Test to record fresh examples."),
    ("Try fresh items", "Show an item that was not in the training photos. Record whether it is Waste, Recycling or an unknown item / empty table. Test never operates real GPIO.\n\nIf guesses are wrong, add more varied photos with the right category and train again."),
    ("Sort with the camera", "Default outputs: a recognised Recycling item opens the servo bin. Waste or an unrecognised item flashes the LED and keeps the servo at rest. An empty table turns the LED off.\n\nEnable real GPIO once to operate the connected hardware. You can change the category mappings, pins and servo angles in GPIO outputs.")
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
        self.nav=[]
        for i,name in enumerate(STEPS):
            b=self.button(nav,f"{i+1}. {name}",lambda i=i:self.show_step(i))
            b.pack(side="left",padx=3); self.nav.append(b)
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
        if step>0 and not self.calibrated:
            self.status.set("First photograph the empty mat, or check the saved table."); return
        if step>2 and self.model is None:
            self.status.set("Collect examples and train the model first."); return
        self.stop_outputs()
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
        ttk.Combobox(self.panel,textvariable=self.label_var,values=LABELS,state="readonly").pack(fill="x",pady=6)
        self.text(self.panel,"Item name (optional):").pack(fill="x")
        tk.Entry(self.panel,textvariable=self.group_var).pack(fill="x",pady=5)
        self.text(self.panel,"For example: bottle, cup or wrapper. No name is needed to start; take 10 photos in each category.",wraplength=350).pack(fill="x")
        self.button(self.panel,"Take photo  [Space]",self.capture).pack(fill="x",pady=8)
        self.counts=self.text(self.panel,"",wraplength=350,bg="white",pady=8)
        self.counts.pack(fill="x")
        self.update_counts()
        self.button(self.panel,"Undo last photo",self.undo).pack(fill="x",pady=6)
        self.button(self.panel,"Delete this named set",self.delete_group).pack(fill="x",pady=6)
        self.button(self.panel,"Next: train →",lambda:self.show_step(2)).pack(fill="x",pady=6)

    def update_counts(self):
        if self.step!=1: return
        counts=Counter((s.label,s.group) for s in self.samples)
        lines=[f"{name}: {sum(s.label==c for s in self.samples)}/{MIN_PHOTOS} photos" for c,name in enumerate(LABELS)]
        lines += [f"{LABELS[c]} - {g}: {n}" for (c,g),n in counts.items()]
        self.counts.configure(text="\n".join(lines[-12:]) or "No examples yet.")

    def train_controls(self):
        missing=requirements(self.samples)
        self.text(self.panel,"\n".join(missing) if missing else f"{len(self.samples)} examples ready for training.",wraplength=350,pady=8).pack(fill="x")
        self.train_button=self.button(self.panel,"Train and quiz",self.train,state="disabled" if missing else "normal")
        self.train_button.pack(fill="x",pady=6)
        report=[]
        for r in self.quiz:
            report.append(f"{r['group']}: {r['correct']}/{r['total']} correct bin, {r['withheld']} withheld, {r['wrong_bin']} wrong bin")
        if report:
            self.text(self.panel,"Photo quiz (as in ML Camera; not a fresh-item test):\n\n"+"\n".join(report),wraplength=350,bg="white",pady=8).pack(fill="x",pady=6)
            self.button(self.panel,"Start sorting →",lambda:self.show_step(4)).pack(fill="x",pady=6)
            self.button(self.panel,"Optional: fresh-item test",lambda:self.show_step(3)).pack(fill="x",pady=6)

    def test_controls(self):
        self.text(self.panel,"Local rules: "+self.rule_var.get(),wraplength=350,bg=C["warn"],pady=6).pack(fill="x")
        self.text(self.panel,"Record the real category of this fresh view:",wraplength=350,pady=8).pack(fill="x")
        for label in range(3):
            self.button(self.panel,LABELS[label] if label<2 else "Unknown item / empty table",lambda label=label:self.record_test(label)).pack(fill="x",pady=3)
        self.test_report=self.text(self.panel,"",wraplength=350,bg="white",pady=8)
        self.test_report.pack(fill="x",pady=8)
        self.update_report()
        self.button(self.panel,"Clear test results",self.clear_tests).pack(fill="x",pady=3)
        self.button(self.panel,"Add better training examples",lambda:self.show_step(1)).pack(fill="x",pady=6)
        self.text(self.panel,"Similarity votes are not an accuracy percentage. Only the fresh tests above show how this model behaved. This is a teaching model; check uncertain items against local recycling guidance.",wraplength=350,pady=6).pack(fill="x")

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
        self.samples.append(Sample(o.feature.copy(),label,name))
        self.invalidate(); self.update_counts(); saved=self.persist()
        n=sum(s.label==label and s.group==name for s in self.samples)
        if saved: self.status.set(f"{name}: {n} photos. Turn or move it before the next photo.")
        count=sum(s.label==label for s in self.samples)
        if count==MIN_PHOTOS:
            if label==0 and sum(s.label==1 for s in self.samples)<MIN_PHOTOS:
                self.label_var.set(LABELS[1]); self.group_var.set("")
                self.status.set("Waste photos done. Now take 10 Recycling photos.")
            elif not requirements(self.samples): self.show_step(2)

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
        self.samples=[]; self.background=None; self.model=None; self.quiz=[]; self.test_records=[]
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
            self.train_result=None; self.busy=False; self.gate.reset(); self.test_records=[]
            self.show_step(2 if error else 4)
            self.status.set(f"Training failed: {error}" if error else "Training finished. Sorting is ready; enable real GPIO to operate the bin and LED.")
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
            self.outputs.close()
        finally:
            self.cam.close()
            self.destroy()
