import json
import threading
import customtkinter as ctk
from analyzer import record_and_analyze

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Matches the Phasmophobia journal Evidence page order
EVIDENCE_LIST = [
    "EMF 5",
    "D.O.T.S",
    "Ultraviolet",
    "Freezing Temps",
    "Ghost Orb",
    "Ghost Writing",
    "Spirit Box",
]

SPEED_LIST = ["Normal", "Fast", "Variable"]

SPECIAL_LIST = [
    "Steps in Salt",
    "Candle = Crucifix",
    "3-Candle Hunt",
    "Double Blowout (<20s)",
    "No Light On",
    "Instant Light Off",
    "Breaker On Required",
    "No Breaker Off",
    "No Breaker On",
    "6-Finger UV",
    "Photo Disappears",
    "Always Knows Location",
    "Single Target",
    "180s Smudge",
    "60s Smudge",
    "Multi-Throw",
    "Full Door Close",
    "Camera-Only D.O.T.S",
    "Quiet Hunt (<12m)",
    "Teleports to Player",
]


class PhasmophobiaAssistant(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Phasmophobia AI Companion")
        self.geometry("1320x800")

        with open("data/ghosts.json", "r", encoding="utf-8") as f:
            self.ghosts = sorted(json.load(f), key=lambda g: g["name"])

        self.ghost_by_name = {g["name"]: g for g in self.ghosts}

        # Filter states: 0 = Neutral, 1 = Require/Confirm (Green), -1 = Rule Out (Red)
        self.evidence_states = {ev: 0 for ev in EVIDENCE_LIST}
        self.speed_states = {sp: 0 for sp in SPEED_LIST}
        self.special_states = {sc: 0 for sc in SPECIAL_LIST}

        # Manual journal ghost mark: 0 = Normal, 1 = Circled (Suspect), -1 = Crossed Out
        self.manual_ghost_marks = {g["name"]: 0 for g in self.ghosts}
        self.selected_ghost_name = self.ghosts[0]["name"] if self.ghosts else None
        self.is_recording = False

        self.setup_ui()
        self.update_ghost_grid()
        self.show_ghost_details(self.selected_ghost_name)

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=0, minsize=255)
        self.grid_columnconfigure(1, weight=2)
        self.grid_columnconfigure(2, weight=1, minsize=310)
        self.grid_rowconfigure(0, weight=1)

        # LEFT COLUMN: Journal Evidence + Speed + Specials
        left_frame = ctk.CTkFrame(self)
        left_frame.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")

        ctk.CTkLabel(left_frame, text="EVIDENCE", font=("Arial", 15, "bold")).pack(pady=(8, 4))
        self.ev_buttons = {}
        for ev in EVIDENCE_LIST:
            btn = ctk.CTkButton(
                left_frame,
                text=ev,
                fg_color="#333333",
                height=28,
                command=lambda e=ev: self.cycle_filter(e, self.evidence_states, self.ev_buttons),
            )
            btn.pack(pady=2, padx=12, fill="x")
            self.ev_buttons[ev] = btn

        ctk.CTkLabel(left_frame, text="HUNT SPEED", font=("Arial", 14, "bold")).pack(pady=(10, 3))
        self.sp_buttons = {}
        for sp in SPEED_LIST:
            btn = ctk.CTkButton(
                left_frame,
                text=sp,
                fg_color="#333333",
                height=26,
                command=lambda s=sp: self.cycle_filter(s, self.speed_states, self.sp_buttons),
            )
            btn.pack(pady=2, padx=12, fill="x")
            self.sp_buttons[sp] = btn

        ctk.CTkLabel(left_frame, text="SPECIALS & TESTS", font=("Arial", 14, "bold")).pack(pady=(10, 3))
        special_scroll = ctk.CTkScrollableFrame(left_frame, height=160)
        special_scroll.pack(pady=2, padx=10, fill="both", expand=True)

        self.sc_buttons = {}
        for sc in SPECIAL_LIST:
            btn = ctk.CTkButton(
                special_scroll,
                text=sc,
                fg_color="#333333",
                height=25,
                command=lambda c=sc: self.cycle_filter(c, self.special_states, self.sc_buttons),
            )
            btn.pack(pady=2, padx=2, fill="x")
            self.sc_buttons[sc] = btn

        ctk.CTkButton(
            left_frame,
            text="Reset All",
            fg_color="#4a4a4a",
            hover_color="#5c5c5c",
            height=30,
            command=self.reset_all,
        ).pack(pady=(8, 10), padx=12, fill="x")

        # CENTER COLUMN: 3-Column Phasmo Book Ghost Grid + Selected Ghost Info
        center_frame = ctk.CTkFrame(self)
        center_frame.grid(row=0, column=1, padx=8, pady=8, sticky="nsew")
        center_frame.grid_rowconfigure(1, weight=1)
        center_frame.grid_columnconfigure(0, weight=1)

        self.book_header = ctk.CTkLabel(
            center_frame,
            text="GHOSTS (Left-Click: Info | Right-Click: Circle / Cross)",
            font=("Arial", 14, "bold"),
        )
        self.book_header.grid(row=0, column=0, padx=10, pady=(8, 4))

        self.grid_container = ctk.CTkFrame(center_frame, fg_color="transparent")
        self.grid_container.grid(row=1, column=0, padx=10, pady=4, sticky="nsew")
        for c in range(3):
            self.grid_container.grid_columnconfigure(c, weight=1, uniform="ghost_col")

        self.ghost_buttons = {}
        for idx, g in enumerate(self.ghosts):
            row = idx // 3
            col = idx % 3
            self.grid_container.grid_rowconfigure(row, weight=1, uniform="ghost_row")
            name = g["name"]
            btn = ctk.CTkButton(
                self.grid_container,
                text=name,
                fg_color="#2b2b2b",
                hover_color="#3d3d3d",
                font=("Arial", 13),
                command=lambda n=name: self.on_ghost_left_click(n),
            )
            btn.grid(row=row, column=col, padx=4, pady=3, sticky="nsew")
            btn.bind("<Button-3>", lambda event, n=name: self.on_ghost_right_click(n))
            self.ghost_buttons[name] = btn

        self.detail_box = ctk.CTkTextbox(center_frame, height=165, font=("Arial", 12))
        self.detail_box.grid(row=2, column=0, padx=10, pady=(6, 10), sticky="ew")

        # RIGHT COLUMN: AI Gameplay Recorder & Log
        right_frame = ctk.CTkFrame(self)
        right_frame.grid(row=0, column=2, padx=8, pady=8, sticky="nsew")

        ctk.CTkLabel(right_frame, text="LOCAL AI GAMEPLAY ANALYZER", font=("Arial", 14, "bold")).pack(pady=(8, 4))

        self.rec_btn = ctk.CTkButton(
            right_frame,
            text="Start 15s Loop Recording",
            fg_color="#1f6aa5",
            command=self.toggle_recording,
        )
        self.rec_btn.pack(pady=8, padx=12, fill="x")

        self.log_box = ctk.CTkTextbox(right_frame)
        self.log_box.pack(pady=(0, 8), padx=10, fill="both", expand=True)

    def cycle_filter(self, key, state_dict, btn_dict):
        new_state = 1 if state_dict[key] == 0 else (-1 if state_dict[key] == 1 else 0)
        state_dict[key] = new_state

        color = "#2e7d32" if new_state == 1 else ("#c62828" if new_state == -1 else "#333333")
        prefix = "[✓] " if new_state == 1 else ("[X] " if new_state == -1 else "")
        btn_dict[key].configure(fg_color=color, text=f"{prefix}{key}")
        self.update_ghost_grid()
        if self.selected_ghost_name:
            self.show_ghost_details(self.selected_ghost_name)

    def reset_all(self):
        for d, b in [
            (self.evidence_states, self.ev_buttons),
            (self.speed_states, self.sp_buttons),
            (self.special_states, self.sc_buttons),
        ]:
            for k in d:
                d[k] = 0
                b[k].configure(fg_color="#333333", text=k)
        for name, btn in self.ghost_buttons.items():
            self.manual_ghost_marks[name] = 0
            btn.configure(text=name)
        self.update_ghost_grid()
        if self.selected_ghost_name:
            self.show_ghost_details(self.selected_ghost_name)

    def on_ghost_left_click(self, name):
        self.selected_ghost_name = name
        self.show_ghost_details(name)
        self.update_ghost_grid()

    def on_ghost_right_click(self, name):
        cur = self.manual_ghost_marks[name]
        nxt = 1 if cur == 0 else (-1 if cur == 1 else 0)
        self.manual_ghost_marks[name] = nxt
        self.selected_ghost_name = name
        self.show_ghost_details(name)
        self.update_ghost_grid()

    def get_possible_ghosts(self):
        req_ev = [k for k, v in self.evidence_states.items() if v == 1]
        ban_ev = [k for k, v in self.evidence_states.items() if v == -1]

        req_sp = [k for k, v in self.speed_states.items() if v == 1]
        ban_sp = [k for k, v in self.speed_states.items() if v == -1]

        req_sc = [k for k, v in self.special_states.items() if v == 1]
        ban_sc = [k for k, v in self.special_states.items() if v == -1]

        possible = set()
        for g in self.ghosts:
            ev = g["evidence"]
            sp = g["speed"]
            sc = g["specials"]

            if not all(e in ev for e in req_ev):
                continue
            if any(e in ev for e in ban_ev):
                continue
            if req_sp and not any(s in sp for s in req_sp):
                continue
            if any(s in sp for s in ban_sp):
                continue
            if not all(c in sc for c in req_sc):
                continue
            if any(c in sc for c in ban_sc):
                continue

            possible.add(g["name"])
        return possible

    def update_ghost_grid(self):
        possible = self.get_possible_ghosts()
        self.book_header.configure(
            text=f"POSSIBLE GHOSTS: {len(possible)} / {len(self.ghosts)}  (Right-Click: Circle / Cross)"
        )

        for name, btn in self.ghost_buttons.items():
            is_possible = name in possible
            mark = self.manual_ghost_marks[name]
            is_selected = name == self.selected_ghost_name

            if mark == -1:
                label = f"✕ {name}"
                fg = "#3a1d1d"
                text_color = "#888888"
            elif mark == 1:
                label = f"( {name} )"
                fg = "#1b5e20"
                text_color = "#ffffff"
            elif not is_possible:
                label = name
                fg = "#222222"
                text_color = "#5c5c5c"
            else:
                label = name
                fg = "#2d4c70" if is_selected else "#2e353d"
                text_color = "#ffffff"

            border_color = "#64b5f6" if is_selected else "#444444"
            btn.configure(
                text=label,
                fg_color=fg,
                text_color=text_color,
                border_width=2 if is_selected else 1,
                border_color=border_color,
            )

    def show_ghost_details(self, name):
        g = self.ghost_by_name.get(name)
        if not g:
            return
        possible = name in self.get_possible_ghosts()
        status = "POSSIBLE" if possible else "RULED OUT BY FILTERS"
        forced = f" | Forced: {g['forced_evidence']}" if g.get("forced_evidence") else ""

        self.detail_box.configure(state="normal")
        self.detail_box.delete("1.0", "end")
        self.detail_box.insert(
            "end",
            f"{g['name']}  —  {status}{forced}\n"
            f"Evidence: {', '.join(g['evidence'])}\n"
            f"Speed ({g['speed']}): {g['speed_detail']}\n"
            f"Specials: {', '.join(g['specials'])}\n"
            f"Tells: {g['tells']}",
        )
        self.detail_box.configure(state="disabled")

    def toggle_recording(self):
        self.is_recording = not self.is_recording
        if self.is_recording:
            self.rec_btn.configure(text="Stop Recording Loop", fg_color="#c62828")
            threading.Thread(target=self.recording_loop, daemon=True).start()
        else:
            self.rec_btn.configure(text="Start 15s Loop Recording", fg_color="#1f6aa5")

    def recording_loop(self):
        while self.is_recording:
            record_and_analyze(clip_duration=15, callback=self.append_log)

    def append_log(self, text):
        self.after(0, lambda: self.log_box.insert("end", text + "\n"))
        self.after(0, lambda: self.log_box.see("end"))


if __name__ == "__main__":
    app = PhasmophobiaAssistant()
    app.mainloop()