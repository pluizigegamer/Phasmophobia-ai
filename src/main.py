import json
import threading
import customtkinter as ctk
from analyzer import record_and_analyze

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

EVIDENCE_LIST = [
    "EMF 5",
    "Ultraviolet",
    "Ghost Writing",
    "Freezing Temps",
    "D.O.T.S",
    "Ghost Orb",
    "Spirit Box",
]

SPEED_LIST = ["Normal", "Fast", "Variable"]

SPECIAL_LIST = [
    "Steps in Salt",
    "Never Steps in Salt",
    "Candle = Crucifix",
    "3-Candle Hunt",
    "Double Blowout (<20s)",
    "No Light On",
    "Instant Light Off",
    "Breaker On Required",
    "No Breaker Off",
    "6-Finger UV",
    "Photo Disappears",
    "Always Knows Location",
    "Single Target",
    "180s Smudge",
    "60s Smudge",
]


class PhasmophobiaAssistant(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Phasmophobia AI Companion")
        self.geometry("1220x760")

        with open("data/ghosts.json", "r", encoding="utf-8") as f:
            self.ghosts = json.load(f)

        # 0 = Neutral, 1 = Confirmed (Green), -1 = Ruled Out (Red)
        self.evidence_states = {ev: 0 for ev in EVIDENCE_LIST}
        self.speed_states = {sp: 0 for sp in SPEED_LIST}
        self.special_states = {sc: 0 for sc in SPECIAL_LIST}
        self.is_recording = False

        self.setup_ui()
        self.update_ghost_list()

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # COLUMN 1: Evidence & Speed
        col1 = ctk.CTkFrame(self)
        col1.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")

        ctk.CTkLabel(col1, text="EVIDENCE", font=("Arial", 14, "bold")).pack(pady=(8, 4))
        self.ev_buttons = {}
        for ev in EVIDENCE_LIST:
            btn = ctk.CTkButton(
                col1,
                text=ev,
                fg_color="#333333",
                height=28,
                command=lambda e=ev: self.cycle_filter(e, self.evidence_states, self.ev_buttons),
            )
            btn.pack(pady=2, padx=14, fill="x")
            self.ev_buttons[ev] = btn

        ctk.CTkLabel(col1, text="HUNT SPEED", font=("Arial", 14, "bold")).pack(pady=(12, 4))
        self.sp_buttons = {}
        for sp in SPEED_LIST:
            btn = ctk.CTkButton(
                col1,
                text=sp,
                fg_color="#333333",
                height=28,
                command=lambda s=sp: self.cycle_filter(s, self.speed_states, self.sp_buttons),
            )
            btn.pack(pady=2, padx=14, fill="x")
            self.sp_buttons[sp] = btn

        ctk.CTkButton(
            col1,
            text="Reset All Filters",
            fg_color="#4a4a4a",
            hover_color="#5c5c5c",
            height=30,
            command=self.reset_filters,
        ).pack(pady=(14, 8), padx=14, fill="x")

        # COLUMN 2: Specials / Tests & Possible Ghosts
        col2 = ctk.CTkFrame(self)
        col2.grid(row=0, column=1, padx=8, pady=8, sticky="nsew")

        ctk.CTkLabel(col2, text="SPECIALS & TESTS", font=("Arial", 14, "bold")).pack(pady=(8, 4))
        special_scroll = ctk.CTkScrollableFrame(col2, height=220)
        special_scroll.pack(pady=2, padx=10, fill="x")

        self.sc_buttons = {}
        for sc in SPECIAL_LIST:
            btn = ctk.CTkButton(
                special_scroll,
                text=sc,
                fg_color="#333333",
                height=26,
                command=lambda c=sc: self.cycle_filter(c, self.special_states, self.sc_buttons),
            )
            btn.pack(pady=2, padx=4, fill="x")
            self.sc_buttons[sc] = btn

        self.ghost_header = ctk.CTkLabel(col2, text="POSSIBLE GHOSTS", font=("Arial", 14, "bold"))
        self.ghost_header.pack(pady=(10, 4))

        self.ghost_textbox = ctk.CTkTextbox(col2)
        self.ghost_textbox.pack(pady=(0, 8), padx=10, fill="both", expand=True)

        # COLUMN 3: AI Gameplay Recorder & Log
        col3 = ctk.CTkFrame(self)
        col3.grid(row=0, column=2, padx=8, pady=8, sticky="nsew")

        ctk.CTkLabel(col3, text="LOCAL AI GAMEPLAY ANALYZER", font=("Arial", 14, "bold")).pack(pady=(8, 4))

        self.rec_btn = ctk.CTkButton(
            col3,
            text="Start 15s Loop Recording",
            fg_color="#1f6aa5",
            command=self.toggle_recording,
        )
        self.rec_btn.pack(pady=8, padx=14, fill="x")

        self.log_box = ctk.CTkTextbox(col3)
        self.log_box.pack(pady=(0, 8), padx=10, fill="both", expand=True)

    def cycle_filter(self, key, state_dict, btn_dict):
        # Cycle: 0 (Neutral) -> 1 (Confirmed/Require) -> -1 (Rule Out) -> 0
        new_state = 1 if state_dict[key] == 0 else (-1 if state_dict[key] == 1 else 0)
        state_dict[key] = new_state

        color = "#2e7d32" if new_state == 1 else ("#c62828" if new_state == -1 else "#333333")
        prefix = "[✓] " if new_state == 1 else ("[X] " if new_state == -1 else "")
        btn_dict[key].configure(fg_color=color, text=f"{prefix}{key}")
        self.update_ghost_list()

    def reset_filters(self):
        for d, b in [
            (self.evidence_states, self.ev_buttons),
            (self.speed_states, self.sp_buttons),
            (self.special_states, self.sc_buttons),
        ]:
            for k in d:
                d[k] = 0
                b[k].configure(fg_color="#333333", text=k)
        self.update_ghost_list()

    def update_ghost_list(self):
        self.ghost_textbox.delete("1.0", "end")

        req_ev = [k for k, v in self.evidence_states.items() if v == 1]
        ban_ev = [k for k, v in self.evidence_states.items() if v == -1]

        req_sp = [k for k, v in self.speed_states.items() if v == 1]
        ban_sp = [k for k, v in self.speed_states.items() if v == -1]

        req_sc = [k for k, v in self.special_states.items() if v == 1]
        ban_sc = [k for k, v in self.special_states.items() if v == -1]

        matches = []
        for g in self.ghosts:
            ev = g["evidence"]
            sp = g["speed"]
            sc = g["specials"]

            # Evidence checks
            if not all(e in ev for e in req_ev):
                continue
            if any(e in ev for e in ban_ev):
                continue

            # Speed checks
            if req_sp and not any(s in sp for s in req_sp):
                continue
            if any(s in sp for s in ban_sp):
                continue

            # Special checks
            if not all(c in sc for c in req_sc):
                continue
            if any(c in sc for c in ban_sc):
                continue

            matches.append(g)

        self.ghost_header.configure(text=f"POSSIBLE GHOSTS ({len(matches)})")
        for g in matches:
            forced = f" | Forced: {g['forced_evidence']}" if g.get("forced_evidence") else ""
            specials_str = ", ".join(g["specials"])
            self.ghost_textbox.insert(
                "end",
                f"• {g['name']} [{g['speed']}{forced}]\n"
                f"  Speed: {g['speed_detail']}\n"
                f"  Specials: {specials_str}\n"
                f"  Tell: {g['tells']}\n\n",
            )

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