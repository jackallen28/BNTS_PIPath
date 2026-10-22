"""An in-window Beginner wiring gate. The test never enters the student editor."""
import tkinter as tk
from pathlib import Path

from ..wiring_guide import WiringSession, guide_pages, test_items, wiring_test_program
from .board import VirtualBoard
from .parts import draw_connection
from .theme import C
from .widgets import PButton, RichText, ScrollFrame, label, window


OBSERVE = {
    'led':'I saw this LED blink three times', 'rgbled':'I saw red, green and blue separately',
    'buzzer':'I heard three beeps', 'button':'I pressed and released this button and it responded',
    'switch':'I activated and released this switch and it responded',
    'pir':'The sensor responded when I moved', 'distance':'The sensor detected my object nearby',
    'servo':'I saw both movements and the return to centre', 'camera':'I saw a new camera picture',
}


class WiringWalkthrough(tk.Frame):
    def __init__(self, workspace, on_done, on_cancel):
        super().__init__(workspace, bg=C['bg'])
        self.workspace, self.on_done, self.on_cancel = workspace, on_done, on_cancel
        self.pages = guide_pages(workspace.lesson)
        self.items = test_items(workspace.lesson)
        self.session = WiringSession({item['id'] for item in self.items})
        self.i = 0
        self._output_buffer = ""
        self.context = workspace.wiring_context()
        win, body = window(self, 'Connect, test, then code', padx=12, pady=10)
        win.pack(fill='both', expand=True, padx=8, pady=8)
        self.heading = label(body, font='h3')
        self.heading.pack(fill='x')
        self.where = label(body, font='small_bold', fg=C['purple'])
        self.where.pack(fill='x', pady=4)
        controls = tk.Frame(body, bg=C['bg'])
        controls.pack(fill='x')
        for mode, title in [('sim','Simulator'),('real','Real Pi')]:
            button = PButton(controls, title, lambda m=mode:self.change_mode(m), font='small', pady=3)
            button.pack(side='left', padx=3)
            button.set_enabled(mode == 'sim' or workspace.real_pi)
        if workspace.uses_camera():
            for camera, title in [('sim','Simulated camera'),('usb','USB camera'),('ribbon','Ribbon camera')]:
                PButton(controls, title, lambda k=camera:self.change_camera(k), font='small', pady=3).pack(side='left', padx=3)
        foot = tk.Frame(body, bg=C['bg'])
        foot.pack(side='bottom', fill='x', pady=(8,0))
        PButton(foot, 'Back to activities', self.cancel, font='small').pack(side='left')
        label(foot,'Artwork: Fritzing contributors • CC BY-SA 3.0',font='small',fg=C['muted']).pack(side='left',padx=10)
        self.next = PButton(foot, 'Connected — next ▸', self.forward, kind='primary', font='small_bold')
        self.next.pack(side='right')
        self.back = PButton(foot, '◂ Back', self.backward, font='small')
        self.back.pack(side='right', padx=6)
        self.content = ScrollFrame(body, bg=C['bg'])
        self.content.pack(fill='both', expand=True)
        self.wheel_default = self.content.canvas
        self.text = RichText(self.content.body, font='ui')
        self.text.pack(fill='x', pady=6)
        self.diagram = tk.Canvas(self.content.body, width=500, height=230, bg='#FFFFFF', highlightthickness=1,
                                 highlightbackground=C['faint'])
        self.test_panel = tk.Frame(self.content.body, bg=C['bg'])
        self.start = PButton(self.test_panel, 'Test all components', self.test, kind='primary')
        self.start.pack(anchor='w', pady=5)
        self.stop_button = PButton(self.test_panel, 'Stop test', workspace.stop, kind='stop')
        self.stop_button.pack(anchor='w')
        self.status = label(self.test_panel, font='small_bold', wraplength=850)
        self.status.pack(fill='x', pady=6)
        self.board = VirtualBoard(self.test_panel, on_press=workspace._board_press,
                                  on_release=workspace._board_release, on_distance=workspace._board_distance,
                                  on_object=self.pick_object)
        self.board.canvas.configure(height=230)
        self.board.set_parts(workspace.parts)
        self.board.pack(fill='x')
        self.output = tk.Text(self.test_panel, height=5, bg='#101820', fg='#FFFFFF', font='small', state='disabled', wrap='word')
        self.output.pack(fill='x', pady=5)
        self.checks = []
        for item in self.items:
            var = tk.BooleanVar(self, False)
            cb = tk.Checkbutton(self.test_panel, text=item['label'] + ': ' + OBSERVE.get(item['kind'], 'I saw it work'),
                                variable=var, command=lambda ident=item['id'],v=var:self.confirm(ident,v.get()),
                                bg=C['bg'], anchor='w', font='small', wraplength=850, state='disabled')
            cb.pack(fill='x', anchor='w')
            self.checks.append((var,cb))
        self.place(x=0,y=0,relwidth=1,relheight=1)
        self.lift()
        self.grab_set()
        self.show_page()
        self.next.focus_set()

    def show_page(self):
        page = self.pages[self.i]
        self.heading.configure(text=f'WIRING {self.i + 1} / {len(self.pages)} • {page["title"]}')
        self.where.configure(text=f'{"Simulator" if self.workspace.mode == "sim" else "Real Pi"} — '
                                  'confirm every component before opening the code')
        self.text.render(page['text'])
        self.diagram.pack_forget()
        self.test_panel.pack_forget()
        testing = page['kind'] == 'test'
        if testing:
            self.test_panel.pack(fill='x')
            self.board.set_mode(self.workspace.mode)
            if self.workspace.uses_camera():
                if self.board.camera is None:
                    self.board.enable_camera(self.workspace.camera, self.workspace.sim_object)
                else:
                    self.board.set_camera_kind(self.workspace.camera)
        elif page['kind'] != 'note':
            self.diagram.pack(anchor='w', pady=8)
            draw_connection(self.diagram, page)
        self.back.set_enabled(self.i > 0 and not self.session.running)
        self.next.configure(text='Open my code ▸' if testing else 'Connected — next ▸')
        self.next.set_enabled(self.session.ready if testing else not self.session.running)
        self.start.set_enabled(not self.session.running)
        self.stop_button.set_enabled(self.session.running)
        self.content.to_top()

    def forward(self):
        if self.session.running:
            return
        if self.i < len(self.pages)-1:
            self.i += 1
            self.show_page()
        elif self.session.ready:
            self.on_done(self.context)

    def backward(self):
        if self.i and not self.session.running:
            self.i -= 1
            self.session.passed = False
            self.session.observed.clear()
            self._clear_checks()
            self.show_page()

    def _clear_checks(self):
        for var,cb in self.checks:
            var.set(False)
            cb.configure(state='disabled')

    def test(self):
        if self.workspace.runner.running or self.workspace._busy:
            return
        self.session.start()
        self._output_buffer = ""
        self._clear_checks()
        self.output.configure(state='normal')
        self.output.delete('1.0','end')
        self.output.configure(state='disabled')
        self.status.configure(text='Watch each output and respond when the test asks for an input.')
        self.show_page()
        self.board.set_live(self.workspace.mode == 'real')
        self.workspace.run_special('wiring-guide', wiring_test_program(self.workspace.lesson),
                                   self.workspace.extra_env(), 'Testing your circuit. Follow the messages.')
        # Initialise simulator sensor positions from this visible board.
        for pin, cm in self.board.sim_distance.items():
            self.workspace.runner.send_command(f'distance {pin} {cm}')

    def append_output(self, text):
        self.output.configure(state='normal')
        self._output_buffer += text
        while '\n' in self._output_buffer:
            line, self._output_buffer = self._output_buffer.split('\n',1)
            if not line.startswith('PIPATH_CHECK:'):
                self.output.insert('end', line+'\n')
        self.output.see('end')
        self.output.configure(state='disabled')

    def message(self, msg):
        kind = msg.get('t')
        if kind == 'devices':
            self.board.set_devices(msg['devices'])
        elif kind == 'pins':
            self.board.set_values(msg['pins'])
        elif kind == 'photo':
            self.board.show_photo(msg.get('preview',''), 'Camera test picture')

    def finished(self, stdout, stderr, rc, reason):
        self.session.finish(stdout, stderr, rc, reason)
        self.board.set_live(False)
        self.board.set_values({})
        self.status.configure(text=('Test finished. Scroll down and tick each part ONLY if you observed it working.' if self.session.passed else
                                    'Test incomplete. Check the connections, then test again. Ask your teacher if a component did not respond.'))
        for _,cb in self.checks:
            cb.configure(state='normal' if self.session.passed else 'disabled')
        self.show_page()

    def confirm(self, ident, on):
        self.session.confirm(ident,on)
        self.next.set_enabled(self.session.ready)

    def pick_object(self, key):
        self.workspace.sim_object = key
        self.workspace.runner.send_command('show ' + key)

    def change_mode(self, mode):
        if mode != self.workspace.mode:
            self.workspace.set_mode(mode)

    def change_camera(self, kind):
        from .. import storage
        if kind != self.workspace.camera:
            storage.set_app_state(camera=kind)
            self.workspace.app.settings_changed('hardware')

    def reset_context(self):
        self.context = self.workspace.wiring_context()
        self.session = WiringSession({item['id'] for item in self.items})
        self._clear_checks()
        self.i = 0
        self.show_page()

    def cancel(self):
        self.workspace._abandon_run()
        self.on_cancel()

    def destroy(self):
        if self.grab_current() == self:
            self.grab_release()
        super().destroy()
