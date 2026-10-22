"""A beginner-friendly code editor with what students get in Thonny: line numbers, colours,
4-space indents, undo and redo, find and replace, go to line, bracket matching and a
right-click menu.

Keys: Tab / Shift+Tab indent and unindent (a whole selection at once), Ctrl+/ comments lines
in or out, Ctrl+Z / Ctrl+Y undo and redo, Ctrl+A selects all, Ctrl+F finds, Ctrl+H replaces,
Ctrl+G goes to a line, Home jumps to the start of the code on the line, Ctrl+= / Ctrl+- zoom.
"""
from __future__ import annotations

import bisect
import keyword
import re
import tkinter as tk
import tkinter.font as tkfont

from .theme import C
from .widgets import PButton, PopupMenu

BUILTINS = ["print", "input", "int", "float", "str", "len", "range", "list", "dict", "round",
            "abs", "min", "max", "sum", "sorted", "type", "bool", "open", "enumerate", "zip"]

_KW = r"\b(?P<KEYWORD>" + "|".join(keyword.kwlist) + r")\b"
_BUILTIN = r"(?<![.\w])(?P<BUILTIN>" + "|".join(BUILTINS) + r")(?=\s*\()"
_COMMENT = r"(?P<COMMENT>#[^\n]*)"
_STRING = (r"(?P<STRING>(?:\b[rRbBfFuU]{1,2})?(?:'''[\s\S]*?(?:'''|\Z)|\"\"\"[\s\S]*?(?:\"\"\"|\Z)"
           r"|'[^'\\\n]*(?:\\.[^'\\\n]*)*'?|\"[^\"\\\n]*(?:\\.[^\"\\\n]*)*\"?))")
_NUMBER = r"(?<![\w.])(?P<NUMBER>\d+(?:\.\d+)?)\b"
_DEF = r"(?:(?<=\bdef )|(?<=\bclass ))(?P<DEF>\w+)"
PATTERN = re.compile("|".join([_STRING, _COMMENT, _KW, _BUILTIN, _NUMBER, _DEF]))
TAGS = {"KEYWORD": "syn_kw", "STRING": "syn_str", "COMMENT": "syn_com", "NUMBER": "syn_num",
        "BUILTIN": "syn_builtin", "DEF": "syn_def"}
# Keys Tk gives a Text box for Emacs users. Students press them by accident and lose work.
EMACS_KEYS = ("<Control-k>", "<Control-t>", "<Control-o>", "<Control-d>", "<Control-b>", "<Control-e>",
              "<Control-n>", "<Control-p>", "<Control-w>", "<Control-i>")

SKIP = re.compile("|".join([_STRING, _COMMENT]))      # where brackets don't count

DEDENT_AFTER = re.compile(r"\s*(return|pass|break|continue|raise)\b")
OPENERS, CLOSERS = "([{", ")]}"
# Code copied from a web page or a document often has characters Python rejects
PASTE_FIXES = [("\r\n", "\n"), ("\r", "\n"), ("\t", "    "), (" ", " "), ("​", ""), ("﻿", ""),
               ("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'")]


def code_part(line: str) -> str:
    """The line without its # comment (a # inside a string doesn't count)."""
    for m in SKIP.finditer(line):
        if m.lastgroup == "COMMENT":
            return line[:m.start()]
    return line


class CodeEditor(tk.Frame):
    def __init__(self, master, on_change=None):
        super().__init__(master, bg=C["ed_bg"])
        self.on_change = on_change
        self._hl_job = None
        self._gutter_job = None
        self._br_job = None
        self._goto_job = None
        self._suspend = False
        self._error_line = None

        self.find_bar = FindBar(self)
        self.gutter = tk.Canvas(self, width=46, bg=C["ed_gutter"], highlightthickness=0, bd=0)
        self.text = tk.Text(
            self, wrap="none", undo=True, maxundo=-1, autoseparators=True,
            font="code", bg=C["ed_bg"], fg=C["ed_fg"], insertbackground=C["ed_cursor"],
            insertwidth=2, selectbackground=C["ed_sel"], selectforeground=C["ed_sel_fg"],
            relief="flat", bd=0, highlightthickness=0, padx=10, pady=8, spacing1=2, spacing3=2,
        )
        self.vsb = tk.Scrollbar(self, orient="vertical", command=self._yview, width=12)
        self.hsb = tk.Scrollbar(self, orient="horizontal", command=self.text.xview, width=12)
        self.text.configure(yscrollcommand=self._on_yscroll, xscrollcommand=self.hsb.set)

        # row 0 is the find bar (only while it's open)
        self.gutter.grid(row=1, column=0, sticky="ns")
        self.text.grid(row=1, column=1, sticky="nsew")
        self.vsb.grid(row=1, column=2, sticky="ns")
        self.hsb.grid(row=2, column=1, sticky="ew")
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        t = self.text
        for tag, colour in TAGS.items():
            t.tag_configure(colour, foreground=C[colour])
        t.tag_configure("errline", background=C["ed_errline"])
        t.tag_configure("blank", background="#FFFF80", foreground="#000000")
        t.tag_configure("found", background="#C6DCFF")
        t.tag_configure("found_now", background="#FFC34D", foreground="#000000")
        t.tag_configure("bracket", background="#C8C8FF", foreground="#000000")
        t.tag_configure("bracket_bad", background="#FF9C9C", foreground="#000000")
        t.tag_configure("goto", background="#E6E6FF")
        t.tag_raise("sel")
        self._set_tabs()

        for seq, fn in (
            ("<Tab>", self._tab), ("<Shift-Tab>", self._dedent), ("<ISO_Left_Tab>", self._dedent),
            ("<Return>", self._newline), ("<KP_Enter>", self._newline), ("<BackSpace>", self._backspace),
            ("<Home>", self._home), ("<KP_Home>", self._home),
            ("<Control-slash>", self.toggle_comment),
            ("<Control-a>", self.select_all), ("<Control-A>", self.select_all),
            ("<Control-y>", self.redo), ("<Control-Y>", self.redo),
            ("<Control-f>", lambda e: self.find_bar.open("find")), ("<Control-F>", lambda e: self.find_bar.open("find")),
            ("<Control-h>", lambda e: self.find_bar.open("replace")), ("<Control-H>", lambda e: self.find_bar.open("replace")),
            ("<Control-g>", lambda e: self.find_bar.open("line")), ("<Control-G>", lambda e: self.find_bar.open("line")),
            ("<Control-equal>", lambda e: self.zoom(1)), ("<Control-plus>", lambda e: self.zoom(1)),
            ("<Control-minus>", lambda e: self.zoom(-1)),
        ):
            t.bind(seq, fn)
        for seq in EMACS_KEYS:          # Tk's old Emacs keys (Ctrl+K deletes a line, Ctrl+T swaps letters...)
            t.bind(seq, lambda e: "break")
        t.bind("<<Modified>>", self._modified)
        t.bind("<Configure>", lambda e: self._draw_gutter())
        t.bind("<KeyRelease>", self._moved)
        t.bind("<ButtonRelease-1>", self._moved)
        t.bind("<Button-3>", self._context_menu)
        # Pasting curly quotes from documents is a classic beginner trap: straighten them
        t.bind("<<Paste>>", self._paste)

    def destroy(self):
        for job in (self._hl_job, self._gutter_job, self._br_job, self._goto_job):
            if job:
                self.after_cancel(job)
        super().destroy()

    # ---------------------------------------------------------------- public
    def get_code(self) -> str:
        return self.text.get("1.0", "end-1c")

    def set_code(self, code: str) -> None:
        self._suspend = True
        self.text.delete("1.0", "end")
        self.text.insert("1.0", code)
        self.text.edit_reset()
        self.text.edit_modified(False)
        self._suspend = False
        self.clear_marks()
        self.highlight()
        self.text.mark_set("insert", "end-1c")
        self.text.see("insert")
        self.find_bar.close(focus=False)

    def append_code(self, code: str) -> None:
        cur = self.get_code().rstrip("\n")
        self.set_code((cur + "\n" if cur else "") + code)

    def mark_error_line(self, line: int | None) -> None:
        self.text.tag_remove("errline", "1.0", "end")
        if line:
            self.text.tag_add("errline", f"{line}.0", f"{line}.0 lineend+1c")
            self.text.see(f"{line}.0")
        self._error_line = line
        self._draw_gutter()

    def clear_marks(self) -> None:
        self._error_line = None
        self.text.tag_remove("errline", "1.0", "end")
        self._draw_gutter()

    def focus(self):
        self.text.focus_set()

    def zoom(self, step: int):
        f = tkfont.nametofont("code")
        size = max(9, min(26, f.cget("size") + step))
        f.configure(size=size)
        self._set_tabs()
        self._draw_gutter()
        return "break"

    def undo(self, _e=None):
        try:
            self.text.edit_undo()
        except tk.TclError:
            pass                    # nothing left to undo
        return "break"

    def redo(self, _e=None):
        try:
            self.text.edit_redo()
        except tk.TclError:
            pass
        return "break"

    def select_all(self, _e=None):
        self.text.tag_add("sel", "1.0", "end-1c")
        self.text.mark_set("insert", "end-1c")
        return "break"

    def goto_line(self, n: int) -> None:
        t = self.text
        last = int(t.index("end-1c").split(".")[0])
        n = max(1, min(n, last))
        t.mark_set("insert", f"{n}.0")
        t.tag_remove("sel", "1.0", "end")
        t.see("insert")
        t.tag_remove("goto", "1.0", "end")
        t.tag_add("goto", f"{n}.0", f"{n}.0 lineend+1c")
        if self._goto_job is not None:
            self.after_cancel(self._goto_job)
        self._goto_job = self.after(1200, self._clear_goto)
        t.focus_set()

    def _clear_goto(self):
        self._goto_job = None
        self.text.tag_remove("goto", "1.0", "end")

    # ---------------------------------------------------------------- highlighting
    def highlight(self) -> None:
        self._hl_job = None
        code = self.get_code()
        t = self.text
        for tag in list(TAGS.values()) + ["blank"]:
            t.tag_remove(tag, "1.0", "end")
        idx = _indexer(code)
        for m in PATTERN.finditer(code):
            kind = m.lastgroup
            if kind:
                t.tag_add(TAGS[kind], idx(m.start(kind)), idx(m.end(kind)))
        for m in re.finditer(r"_{3,}", code):
            t.tag_add("blank", idx(m.start()), idx(m.end()))

    def _schedule_highlight(self):
        if self._hl_job:
            self.after_cancel(self._hl_job)
        self._hl_job = self.after(150, self.highlight)

    # ---------------------------------------------------------------- bracket matching
    def _moved(self, _e=None):
        self._draw_gutter()
        if self._br_job is None:
            self._br_job = self.after_idle(self._match_brackets)

    def _match_brackets(self) -> None:
        """Light up the bracket next to the cursor and its partner (red if it has none)."""
        self._br_job = None
        t = self.text
        t.tag_remove("bracket", "1.0", "end")
        t.tag_remove("bracket_bad", "1.0", "end")
        brackets = OPENERS + CLOSERS
        before_ok = len(t.get("insert-1c", "insert")) == 1 and t.get("insert-1c", "insert") in brackets
        after_ok = len(t.get("insert", "insert+1c")) == 1 and t.get("insert", "insert+1c") in brackets
        if not (before_ok or after_ok):
            return
        code = self.get_code()
        pos = len(t.get("1.0", "insert"))
        here = pos - 1 if before_ok else pos
        if not 0 <= here < len(code) or code[here] not in brackets:
            return
        skips = [(m.start(), m.end()) for m in SKIP.finditer(code)]
        starts = [s for s, _ in skips]

        def skipped(i):
            k = bisect.bisect_right(starts, i) - 1
            return k >= 0 and skips[k][0] <= i < skips[k][1]

        if skipped(here):
            return
        ch = code[here]
        step, mine, theirs = (1, ch, CLOSERS[OPENERS.index(ch)]) if ch in OPENERS else \
                             (-1, ch, OPENERS[CLOSERS.index(ch)])
        depth, i, partner = 0, here, None
        while 0 <= i < len(code):
            c = code[i]
            if (c == mine or c == theirs) and not skipped(i):
                depth += 1 if c == mine else -1
                if depth == 0:
                    partner = i
                    break
            i += step
        idx = _indexer(code)
        if partner is None:
            t.tag_add("bracket_bad", idx(here), idx(here + 1))
        else:
            for p in (here, partner):
                t.tag_add("bracket", idx(p), idx(p + 1))

    # ---------------------------------------------------------------- gutter
    def _yview(self, *args):
        self.text.yview(*args)
        self._draw_gutter()

    def _on_yscroll(self, first, last):
        self.vsb.set(first, last)
        self._draw_gutter()

    def _draw_gutter(self):
        """Redraw line numbers once the current burst of keys / scrolling is over."""
        if self._gutter_job is None:
            self._gutter_job = self.after_idle(self._draw_gutter_now)

    def _draw_gutter_now(self):
        self._gutter_job = None
        g = self.gutter
        digits = len(self.text.index("end-1c").split(".")[0])
        width = tkfont.nametofont("code_ui").measure("9" * max(2, digits)) + 18
        if int(g.cget("width")) != width:
            g.configure(width=width)
        g.delete("all")
        err = self._error_line
        i = self.text.index("@0,0")
        while True:
            d = self.text.dlineinfo(i)
            if d is None:
                break
            n = int(i.split(".")[0])
            y = d[1]
            if n == err:
                g.create_rectangle(0, y, width, y + d[3], fill=C["accent"], outline="")
                g.create_text(width - 6, y + d[3] // 2, anchor="e", text=str(n), fill="#FFFFFF", font="code_ui")
            else:
                g.create_text(width - 6, y + d[3] // 2, anchor="e", text=str(n), fill=C["ed_gutter_fg"],
                              font="code_ui")
            nxt = self.text.index(f"{i}+1line")
            if nxt == i:
                break
            i = nxt

    def _set_tabs(self):
        w = tkfont.nametofont("code").measure("    ")
        self.text.configure(tabs=(w,))

    # ---------------------------------------------------------------- editing helpers
    def _modified(self, _e=None):
        if self.text.edit_modified():
            self.text.edit_modified(False)
            if not self._suspend:
                if self._error_line:
                    self.clear_marks()
                self._schedule_highlight()
                self._draw_gutter()
                self.find_bar.text_changed()
                if self.on_change:
                    self.on_change()

    def _block(self, fn) -> None:
        """Run fn as ONE undo step (otherwise Tk undoes a block indent a line at a time)."""
        t = self.text
        t.configure(autoseparators=False)
        t.edit_separator()
        try:
            fn()
        finally:
            t.edit_separator()
            t.configure(autoseparators=True)

    def _lines(self) -> tuple[int, int]:
        """First and last line of the selection (or the cursor's line)."""
        t = self.text
        if t.tag_ranges("sel"):
            first = int(t.index("sel.first").split(".")[0])
            end = t.index("sel.last")
            last = int(end.split(".")[0])
            if end.endswith(".0") and last > first:
                last -= 1           # the selection stops at the start of a line: that line isn't in it
            return first, last
        ln = int(t.index("insert").split(".")[0])
        return ln, ln

    def _reselect(self, first: int, last: int) -> None:
        t = self.text
        t.tag_remove("sel", "1.0", "end")
        t.tag_add("sel", f"{first}.0", f"{last}.end")

    def _tab(self, _e=None):
        t = self.text
        if t.tag_ranges("sel"):
            return self.indent()
        col = int(t.index("insert").split(".")[1])
        t.insert("insert", " " * (4 - col % 4))
        return "break"

    def indent(self, _e=None):
        t = self.text
        first, last = self._lines()

        def go():
            for ln in range(first, last + 1):
                if t.get(f"{ln}.0", f"{ln}.end").strip():
                    t.insert(f"{ln}.0", "    ")
        self._block(go)
        if first != last or t.tag_ranges("sel"):
            self._reselect(first, last)
        return "break"

    def _dedent(self, _e=None):
        t = self.text
        first, last = self._lines()
        had_sel = bool(t.tag_ranges("sel"))

        def go():
            for ln in range(first, last + 1):
                line = t.get(f"{ln}.0", f"{ln}.end")
                n = len(line) - len(line.lstrip(" "))
                if n:
                    t.delete(f"{ln}.0", f"{ln}.{n % 4 or 4}")
        self._block(go)
        if had_sel:
            self._reselect(first, last)
        return "break"

    def _newline(self, _e=None):
        t = self.text
        t.edit_separator()
        if t.tag_ranges("sel"):
            t.delete("sel.first", "sel.last")
        line = t.get("insert linestart", "insert")
        indent = re.match(r"[ \t]*", line).group(0)
        if code_part(line).rstrip().endswith(":"):
            indent += "    "
        elif DEDENT_AFTER.match(line) and code_part(line).strip():
            indent = indent[:-4]      # nothing else runs after return / pass / break...
        t.insert("insert", "\n" + indent)
        t.see("insert")
        return "break"

    def _backspace(self, _e=None):
        t = self.text
        if t.tag_ranges("sel"):
            return None
        before = t.get("insert linestart", "insert")
        if before and not before.strip(" "):
            n = len(before) % 4 or 4      # back to the last indent level
            t.delete(f"insert-{n}c", "insert")
            return "break"
        return None

    def _home(self, e):
        """Home goes to the start of the code on the line, then (pressed again) to the very start."""
        if e.state & 0x0001:           # Shift+Home: let Tk extend the selection
            return None
        t = self.text
        line = t.get("insert linestart", "insert lineend")
        first = len(line) - len(line.lstrip())
        col = int(t.index("insert").split(".")[1])
        t.mark_set("insert", f"insert linestart+{0 if col == first else first}c")
        t.tag_remove("sel", "1.0", "end")
        t.see("insert")
        self._moved()
        return "break"

    def toggle_comment(self, _e=None):
        t = self.text
        first, last = self._lines()
        lines = [t.get(f"{ln}.0", f"{ln}.end") for ln in range(first, last + 1)]
        uncomment = all(line.lstrip().startswith("#") or not line.strip() for line in lines)

        def go():
            for ln, line in zip(range(first, last + 1), lines):
                if uncomment:
                    m = re.match(r"(\s*)# ?", line)
                    if m and line.strip():
                        t.delete(f"{ln}.{len(m.group(1))}", f"{ln}.{m.end()}")
                elif line.strip():
                    n = len(line) - len(line.lstrip())
                    t.insert(f"{ln}.{n}", "# ")
        self._block(go)
        return "break"

    def _paste(self, _e=None):
        try:
            clip = self.clipboard_get()
        except tk.TclError:
            return "break"
        for bad, good in PASTE_FIXES:
            clip = clip.replace(bad, good)
        t = self.text

        def go():
            if t.tag_ranges("sel"):
                t.delete("sel.first", "sel.last")
            t.insert("insert", clip)
        self._block(go)
        t.see("insert")
        return "break"

    def cut(self):
        self.text.event_generate("<<Cut>>")

    def copy(self):
        self.text.event_generate("<<Copy>>")

    def paste(self):
        self._paste()

    def _context_menu(self, e):
        t = self.text
        if not t.tag_ranges("sel"):
            t.mark_set("insert", f"@{e.x},{e.y}")
        sel = bool(t.tag_ranges("sel"))
        PopupMenu.of(self).show([
            ("Undo", "Ctrl+Z", self.undo, True),
            ("Redo", "Ctrl+Y", self.redo, True),
            None,
            ("Cut", "Ctrl+X", self.cut, sel),
            ("Copy", "Ctrl+C", self.copy, sel),
            ("Paste", "Ctrl+V", self.paste, True),
            ("Select all", "Ctrl+A", self.select_all, True),
            None,
            ("Indent", "Tab", self.indent, True),
            ("Unindent", "Shift+Tab", self._dedent, True),
            ("Comment / uncomment", "Ctrl+/", self.toggle_comment, True),
            None,
            ("Find and replace", "Ctrl+F", lambda: self.find_bar.open("replace"), True),
            ("Go to line", "Ctrl+G", lambda: self.find_bar.open("line"), True),
        ], e.x_root, e.y_root)
        return "break"


ASTRAL = re.compile("[\U00010000-\U0010FFFF]")


def _indexer(code: str):
    """A function turning a character offset in code into a Tk "line.column" index."""
    starts = [0] + [m.end() for m in re.finditer("\n", code)]
    wide = ASTRAL.search(code) is not None      # Tk 8.6 counts an emoji as 2 characters

    def idx(pos: int) -> str:
        ln = bisect.bisect_right(starts, pos) - 1
        col = pos - starts[ln]
        if wide:
            col += len(ASTRAL.findall(code, starts[ln], pos))
        return f"{ln + 1}.{col}"
    return idx


class FindBar(tk.Frame):
    """Find, replace and go to line, in a bar above the code (Ctrl+F, Ctrl+H, Ctrl+G).
    Searching ignores capitals unless you type a capital letter."""

    BG = C["bg"]

    def __init__(self, editor: CodeEditor):
        super().__init__(editor, bg=self.BG, padx=8, pady=5)
        self.ed = editor
        self.mode = "find"
        self.matches: list[tuple[str, str]] = []
        self.current = -1
        self._job = None
        self.is_open = False

        row = tk.Frame(self, bg=self.BG)
        row.pack(fill="x")
        self.what = tk.Label(row, text="Find", font="small_bold", fg=C["ink"], bg=self.BG, width=9, anchor="w")
        self.what.pack(side="left")
        self.entry = self._entry(row)
        self.entry.pack(side="left", fill="x", expand=True, ipady=2)
        self.prev_btn = PButton(row, "◂", self.prev, kind="secondary", font="small_bold", padx=8, pady=1)
        self.next_btn = PButton(row, "▸", self.next, kind="secondary", font="small_bold", padx=8, pady=1)
        self.prev_btn.pack(side="left", padx=(6, 0))
        self.next_btn.pack(side="left", padx=(2, 0))
        self.count = tk.Label(row, text="", font="small", fg=C["muted"], bg=self.BG, width=11)
        self.count.pack(side="left", padx=(6, 0))
        PButton(row, "✗", self.close, kind="secondary", font="small_bold", padx=8, pady=1).pack(side="right")

        self.rep_row = tk.Frame(self, bg=self.BG)
        tk.Label(self.rep_row, text="Replace with", font="small_bold", fg=C["ink"], bg=self.BG, width=9,
                 anchor="w").pack(side="left")
        self.rep_entry = self._entry(self.rep_row)
        self.rep_entry.pack(side="left", fill="x", expand=True, ipady=2)
        PButton(self.rep_row, "Replace", self.replace_one, kind="secondary", font="small_bold", padx=8,
                pady=1).pack(side="left", padx=(6, 0))
        PButton(self.rep_row, "Replace all", self.replace_all, kind="secondary", font="small_bold", padx=8,
                pady=1).pack(side="left", padx=(2, 0))

        self.entry.bind("<Return>", lambda e: (self.go(), "break")[1])
        self.entry.bind("<KP_Enter>", lambda e: (self.go(), "break")[1])
        self.entry.bind("<Shift-Return>", lambda e: (self.prev(), "break")[1])
        self.entry.bind("<KeyRelease>", self._typed)
        self.rep_entry.bind("<Return>", lambda e: (self.replace_one(), "break")[1])
        for w in (self.entry, self.rep_entry):
            w.bind("<Escape>", lambda e: (self.close(), "break")[1])

    def _entry(self, master) -> tk.Entry:
        return tk.Entry(master, font="code_ui", bg="#FFFFFF", fg=C["ink"], insertbackground=C["ink"],
                        relief="sunken", bd=2, highlightthickness=0, selectbackground=C["select"],
                        selectforeground="#FFFFFF")

    # ---------------------------------------------------------------- open / close
    def open(self, mode: str = "find"):
        self.mode = mode
        t = self.ed.text
        if mode == "line":
            self.what.configure(text="Go to line")
            for w in (self.prev_btn, self.next_btn, self.count):
                w.pack_forget()
            self.rep_row.pack_forget()
            self.entry.delete(0, "end")
            self.entry.insert(0, t.index("insert").split(".")[0])
        else:
            self.what.configure(text="Find")
            self.prev_btn.pack(side="left", padx=(6, 0), after=self.entry)
            self.next_btn.pack(side="left", padx=(2, 0), after=self.prev_btn)
            self.count.pack(side="left", padx=(6, 0), after=self.next_btn)
            if mode == "replace":
                self.rep_row.pack(fill="x", pady=(4, 0))
            else:
                self.rep_row.pack_forget()
            if t.tag_ranges("sel"):
                picked = t.get("sel.first", "sel.last")
                if picked and "\n" not in picked:
                    self.entry.delete(0, "end")
                    self.entry.insert(0, picked)
        if not self.is_open:
            self.is_open = True
            self.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.entry.focus_set()
        self.entry.select_range(0, "end")
        if mode != "line":
            self.search(keep_place=True)
        return "break"

    def close(self, focus: bool = True):
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        if self.is_open:
            self.is_open = False
            self.grid_remove()
            for tag in ("found", "found_now"):
                self.ed.text.tag_remove(tag, "1.0", "end")
            self.matches, self.current = [], -1
        if focus:
            self.ed.text.focus_set()
        return "break"

    # ---------------------------------------------------------------- searching
    def _typed(self, e):
        if self.mode != "line" and e.keysym not in ("Return", "KP_Enter", "Escape", "Shift_L", "Shift_R"):
            self.search(keep_place=True)

    def text_changed(self):
        """The code changed: refresh the highlights (a little later, not on every key)."""
        if self.is_open and self.mode != "line" and self._job is None:
            self._job = self.after(300, lambda: (setattr(self, "_job", None), self.search(keep_place=True)))

    def search(self, keep_place: bool = False):
        t = self.ed.text
        for tag in ("found", "found_now"):
            t.tag_remove(tag, "1.0", "end")
        q = self.entry.get()
        self.matches, self.current = [], -1
        if not q:
            self.count.configure(text="")
            return
        code = self.ed.get_code()
        flags = 0 if any(c.isupper() for c in q) else re.IGNORECASE
        idx = _indexer(code)
        here = len(t.get("1.0", "insert"))
        for m in re.finditer(re.escape(q), code, flags):
            self.matches.append((idx(m.start()), idx(m.end())))
            t.tag_add("found", idx(m.start()), idx(m.end()))
            if self.current < 0 and m.start() >= (here - len(q) if keep_place else here):
                self.current = len(self.matches) - 1
        if self.matches and self.current < 0:
            self.current = 0
        self._show_current()

    def _show_current(self):
        t = self.ed.text
        t.tag_remove("found_now", "1.0", "end")
        if not self.matches:
            self.count.configure(text="not found")
            return
        a, b = self.matches[self.current]
        t.tag_add("found_now", a, b)
        t.see(a)
        self.count.configure(text=f"{self.current + 1} of {len(self.matches)}")

    def go(self):
        if self.mode == "line":
            try:
                n = int(self.entry.get().strip())
            except ValueError:
                return
            self.close(focus=False)
            self.ed.goto_line(n)
        else:
            self.next()

    def next(self):
        if self.matches:
            self.current = (self.current + 1) % len(self.matches)
            self._show_current()
        else:
            self.search()

    def prev(self):
        if self.matches:
            self.current = (self.current - 1) % len(self.matches)
            self._show_current()

    # ---------------------------------------------------------------- replacing
    def replace_one(self):
        if not self.matches:
            self.search()
            return
        t = self.ed.text
        a, b = self.matches[self.current]
        new = self.rep_entry.get()
        self.ed._block(lambda: (t.delete(a, b), t.insert(a, new)))
        t.mark_set("insert", f"{a}+{len(new)}c")
        self.search(keep_place=False)

    def replace_all(self):
        q = self.entry.get()
        if not q:
            return
        new = self.rep_entry.get()
        code = self.ed.get_code()
        flags = 0 if any(c.isupper() for c in q) else re.IGNORECASE
        changed, n = re.subn(re.escape(q), lambda m: new, code, flags=flags)
        if not n:
            self.count.configure(text="not found")
            return
        t = self.ed.text
        where = t.index("insert")
        self.ed._block(lambda: (t.delete("1.0", "end-1c"), t.insert("1.0", changed)))
        t.mark_set("insert", where)
        self.search(keep_place=True)
        self.count.configure(text=f"{n} replaced")
