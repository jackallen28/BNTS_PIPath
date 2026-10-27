"""Editable GPIO mappings; opening the dialog stops hardware before any changes."""
import tkinter as tk
from tkinter import ttk
from .model import LABELS
from .outputs import OutputRule, OutputConfig, validate_config

# BCM signal numbers and their physical positions on the 40-pin header.
HEADER_PINS = {2:3,3:5,4:7,5:29,6:31,7:26,8:24,9:21,10:19,11:23,12:32,
               13:33,14:8,15:10,16:36,17:11,18:12,19:35,20:38,21:40,
               22:15,23:16,24:18,25:22,26:37,27:13}


class OutputDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("WastePath · GPIO outputs")
        self.configure(bg="#C0C0C0")
        self.geometry("790x555")
        self.resizable(False, False)
        self.transient(app)
        self.rows = []
        self.message = tk.StringVar(value="Simulation until you enable real GPIO in Live. Opening this window stops GPIO.")
        tk.Label(self,text="What should each detected category do?",bg="#704988",fg="white",
                 font=(app.ui_font,15,"bold"),padx=12,pady=12).pack(fill="x")
        tk.Label(self,text="Use a servo for the bin category and a flashing LED for wrong items. Set unused categories to Off.\n"
                 "Use BCM GPIO numbers; wire the corresponding physical header pin shown below.",
                 bg="#C0C0C0",justify="left",anchor="w",padx=14,pady=10).pack(fill="x")
        rules={rule.label:rule for rule in app.outputs.config.rules}
        for label in (0,1):
            rule=rules.get(label,OutputRule(label,"off",17 if label==0 else 18))
            box=tk.LabelFrame(self,text=LABELS[label],bg="#C0C0C0",bd=2,relief="groove",padx=10,pady=8)
            box.pack(fill="x",padx=14,pady=5)
            variables={"kind":tk.StringVar(value=rule.kind),"pin":tk.StringVar(value=str(rule.pin)),
                       "active_angle":tk.StringVar(value=str(rule.active_angle)),
                       "rest_angle":tk.StringVar(value=str(rule.rest_angle))}
            tk.Label(box,text="Output",bg="#C0C0C0").grid(row=0,column=0,sticky="w")
            kind=ttk.Combobox(box,textvariable=variables["kind"],values=("off","led","servo"),state="readonly",width=9)
            kind.grid(row=0,column=1,padx=8)
            tk.Label(box,text="BCM GPIO",bg="#C0C0C0").grid(row=0,column=2)
            pin=ttk.Combobox(box,textvariable=variables["pin"],values=tuple(HEADER_PINS),width=5)
            pin.grid(row=0,column=3,padx=8)
            physical=tk.Label(box,text="",bg="#C0C0C0"); physical.grid(row=0,column=4,sticky="w")
            tk.Label(box,text="Servo angle when detected",bg="#C0C0C0").grid(row=1,column=0,columnspan=2,sticky="w",pady=(10,0))
            active=tk.Entry(box,textvariable=variables["active_angle"],width=6)
            active.grid(row=1,column=2,pady=(10,0))
            tk.Label(box,text="Rest angle",bg="#C0C0C0").grid(row=1,column=3,pady=(10,0))
            rest=tk.Entry(box,textvariable=variables["rest_angle"],width=6)
            rest.grid(row=1,column=4,pady=(10,0))
            def refresh(*_,v=variables,physical=physical,active=active,rest=rest,pin=pin):
                try: text=f"Physical pin {HEADER_PINS[int(v['pin'].get())]}"
                except (ValueError,KeyError): text="Choose GPIO 2–27"
                physical.configure(text=text)
                state="normal" if v["kind"].get()=="servo" else "disabled"
                active.configure(state=state); rest.configure(state=state)
                pin.configure(state="disabled" if v["kind"].get()=="off" else "normal")
            variables["kind"].trace_add("write",refresh)
            variables["pin"].trace_add("write",refresh)
            refresh()
            self.rows.append(variables)
        tk.Label(self,text="An LED flashes for its category AND unrecognised items. A servo opens only\n"
                 "for its recognised category. Empty table: LED off and servo at rest.\n"
                 "Real outputs run only in Live. Servo power: use a suitable external supply and share its ground with the Pi.\n"
                 "Use a resistor with the LED. Disconnect power before changing wires.",
                 bg="#FFFFE1",justify="left",anchor="w",padx=10,pady=8).pack(fill="x",padx=14,pady=10)
        tk.Label(self,textvariable=self.message,bg="#C0C0C0",fg="#704988",wraplength=750,justify="left").pack(fill="x",padx=14)
        row=tk.Frame(self,bg="#C0C0C0"); row.pack(side="bottom",fill="x",padx=14,pady=12)
        app.button(row,"Save mappings",self.apply).pack(side="right",padx=5)
        app.button(row,"Cancel",self.cancel).pack(side="right",padx=5)
        self.protocol("WM_DELETE_WINDOW",self.cancel)
        self.grab_set()

    def read_config(self):
        rules=[]
        for label,v in enumerate(self.rows):
            kind=v['kind'].get()
            # Disabled angle/pin fields do not affect the active output.
            pin=int(v['pin'].get()) if kind!="off" else (17 if label==0 else 18)
            active=float(v['active_angle'].get()) if kind=="servo" else 90
            rest=float(v['rest_angle'].get()) if kind=="servo" else 0
            rules.append(OutputRule(label,kind,pin,active,rest))
        config=OutputConfig(rules)
        validate_config(config)
        return config

    def apply(self):
        try:
            config=self.read_config()
            if not self.app.apply_output_config(config):
                self.message.set(self.app.status.get()); return
        except (ValueError,TypeError) as e:
            self.message.set(f"Check the settings: {e}"); return
        self.cancel()

    def cancel(self):
        self.grab_release()
        self.app.output_dialog=None
        self.app.gate.reset()
        self.app.status.set("GPIO stopped. Mappings are simulated until you enable real GPIO in Live.")
        self.destroy()
