import tkinter as tk
from tkinter import messagebox, ttk, filedialog
import datetime, queue, os, platform, copy, shutil
from PIL import Image, ImageTk

# --- PDF EXPORT ---
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False


def _pdf_meta_table(session_info):
    return [
        ["Instructor:", session_info.get("instructor",""), "Subject:", session_info.get("subject","")],
        ["Section:",    session_info.get("section",""),    "Room:",    session_info.get("room","")],
        ["Date:",       session_info.get("date",""),       "Duration:",session_info.get("duration","")],
        ["Semester:",   f"{session_info.get('semester','')} {session_info.get('school_year','')}","",""],
    ]

def _pdf_table_style():
    return TableStyle([
        ("FONTNAME",      (0,0),(-1,-1),"Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,-1),9),
        ("TEXTCOLOR",     (0,0),(0,-1), colors.HexColor("#64748B")),
        ("TEXTCOLOR",     (2,0),(2,-1), colors.HexColor("#64748B")),
        ("BOTTOMPADDING", (0,0),(-1,-1),4),
    ])

def export_summary_pdf(session_info, activity_counts, total_frames, output_path):
    if not REPORTLAB_OK: raise Exception("Run: pip install reportlab")
    styles = getSampleStyleSheet()
    doc    = SimpleDocTemplate(output_path, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story  = []
    title_style = ParagraphStyle("T", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=18, textColor=colors.HexColor("#0F172A"), spaceAfter=12)
    story.append(Paragraph("VOCA - Teaching Activity Summary Report", title_style))
    story.append(Spacer(1, 10))
    t = Table(_pdf_meta_table(session_info), colWidths=[80,180,80,180])
    t.setStyle(_pdf_table_style()); story.append(t); story.append(Spacer(1, 15))
    story.append(Paragraph("Activity Distribution", styles["Heading2"])); story.append(Spacer(1, 8))
    rows = [["Activity", "Frames", "Percentage"]]
    for act, count in activity_counts.items():
        pct = round(count / total_frames * 100) if total_frames > 0 else 0
        rows.append([act, str(count), f"{pct}%"])
    t2 = Table(rows, colWidths=[240,140,140])
    t2.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1E293B")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("BOTTOMPADDING",(0,0),(-1,0),6),("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#CBD5E1")),("FONTNAME",(0,1),(-1,-1),"Helvetica"),("FONTSIZE",(0,0),(-1,-1),9)]))
    story.append(t2); doc.build(story)

def export_full_pdf(session_info, activity_counts, total_frames, session_log, output_path):
    if not REPORTLAB_OK: raise Exception("Run: pip install reportlab")
    styles = getSampleStyleSheet()
    doc    = SimpleDocTemplate(output_path, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story  = []
    title_style = ParagraphStyle("T", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=18, textColor=colors.HexColor("#0F172A"), spaceAfter=12)
    story.append(Paragraph("VOCA - Full Teaching Activity Report", title_style)); story.append(Spacer(1, 10))
    t = Table(_pdf_meta_table(session_info), colWidths=[80,180,80,180])
    t.setStyle(_pdf_table_style()); story.append(t); story.append(Spacer(1, 15))
    story.append(Paragraph("Complete Activity Log", styles["Heading2"])); story.append(Spacer(1, 8))
    rows = [["Timestamp", "Activity", "Instructor"]]
    for ts, act in session_log:
        rows.append([ts, act, session_info.get("instructor","")])
    t2 = Table(rows, colWidths=[140,240,140])
    t2.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1E293B")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("BOTTOMPADDING",(0,0),(-1,0),6),("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#CBD5E1")),("FONTNAME",(0,1),(-1,-1),"Helvetica"),("FONTSIZE",(0,0),(-1,-1),8)]))
    story.append(t2); doc.build(story)


# --- DATABASE ---
try:
    from database import init_db, save_session, save_faculty, load_faculty_list, delete_faculty, load_faculty_photos
    init_db()
    DB_OK = True
except Exception as e:
    print(f"[DB] Not available: {e}")
    DB_OK = False


# --- ASSET LOADER ---
_IMG_CACHE = {}
def _load_img(filename, size):
    key = (filename, size)
    if key in _IMG_CACHE: return _IMG_CACHE[key]
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if not os.path.exists(path): return None
    try:
        img = Image.open(path).resize(size, Image.LANCZOS)
        tk_img = ImageTk.PhotoImage(img)
        _IMG_CACHE[key] = tk_img
        return tk_img
    except: return None


# ============================================================
# LIVE FEED WINDOW
# ============================================================
class LiveFeedWindow(tk.Toplevel):

    BG      = "#0B1120"
    CARD_BG = "#111827"
    BORDER  = "#1E293B"
    MUTED   = "#64748B"
    TEXT    = "#F1F5F9"
    ERROR   = "#EF4444"
    ACCENT  = "#3B82F6"

    def __init__(self, master, on_result=None, on_close=None,
                 camera_source=0, act_colors=None, limit_sec=0,
                 faculty_photo=None, faculty_name=None):
        super().__init__(master)
        self.title("VOCA  -  Live Feed")
        self.geometry("800x560"); self.minsize(600, 440)
        self.configure(bg=self.BG)
        self._on_result     = on_result
        self._on_close      = on_close
        self.camera_source  = camera_source
        self.act_colors     = act_colors or {}
        self._limit_sec     = limit_sec or 0
        self._faculty_photo = faculty_photo
        self._faculty_name  = faculty_name
        self._detector      = None
        self._det_queue     = queue.Queue(maxsize=5)
        self._tk_img        = None
        self.camera_on      = False
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build_ui(); self._start()

    def _build_ui(self):
        top = tk.Frame(self, bg=self.CARD_BG, height=44, highlightbackground=self.BORDER, highlightthickness=1)
        top.pack(fill="x"); top.pack_propagate(False)
        tk.Label(top, text="  VOCA  -  LIVE FEED", font=("Arial",10,"bold"), fg=self.ACCENT, bg=self.CARD_BG).pack(side="left", padx=16, pady=10)
        tk.Button(top, text="Stop & Close", font=("Arial",9), bg=self.ERROR, fg=self.TEXT, activebackground="#B91C1C", bd=0, padx=12, pady=6, cursor="hand2", command=self._close).pack(side="right", padx=16, pady=8)
        self.cam_canvas = tk.Canvas(self, bg="#000000", highlightthickness=0)
        self.cam_canvas.pack(fill="both", expand=True)
        self._draw_placeholder()
        bot = tk.Frame(self, bg=self.CARD_BG, height=44, highlightbackground=self.BORDER, highlightthickness=1)
        bot.pack(fill="x"); bot.pack_propagate(False)
        tk.Label(bot, text="Detected:", font=("Arial",8), fg=self.MUTED, bg=self.CARD_BG).pack(side="left", padx=12, pady=12)
        self.act_lbl = tk.Label(bot, text="Initialising...", font=("Arial",10,"bold"), fg=self.MUTED, bg=self.CARD_BG)
        self.act_lbl.pack(side="left")
        self.fps_lbl = tk.Label(bot, text="", font=("Arial",8), fg=self.MUTED, bg=self.CARD_BG)
        self.fps_lbl.pack(side="right", padx=16)

    def _draw_placeholder(self):
        self.cam_canvas.delete("all")
        cw = self.cam_canvas.winfo_width() or 780
        ch = self.cam_canvas.winfo_height() or 440
        self.cam_canvas.create_rectangle(0,0,cw,ch, fill=self.BG, outline="")
        self.cam_canvas.create_text(cw//2, ch//2-16, text="Camera", font=("Arial",36), fill=self.MUTED)
        self.cam_canvas.create_text(cw//2, ch//2+28, text="Opening camera...", font=("Arial",10), fill=self.MUTED)

    def _start(self):
        from detector import Detector
        self.camera_on = True
        self._detector = Detector(self._det_queue, camera_source=self.camera_source, limit_sec=self._limit_sec, faculty_photo=self._faculty_photo, faculty_name=self._faculty_name)
        self._detector.start(); self._poll()

    def _poll(self):
        if not self.camera_on: return
        try:
            while True:
                msg = self._det_queue.get_nowait()
                if "timeout" in msg:
                    if self._on_close: self._on_close()
                    self.camera_on = False
                    if self._detector: self._detector.stop(); self._detector = None
                    self.destroy(); return
                if "error" in msg:
                    messagebox.showerror("Camera Error", msg["error"], parent=self)
                    self._close(); return
                if "status" in msg:
                    try: self.act_lbl.config(text=msg["status"], fg=self.MUTED)
                    except: pass
                    continue
                activity   = msg.get("activity", "Ambient / Idle")
                fps        = msg.get("fps", 0.0)
                frame_bgr  = msg.get("frame")
                ts         = msg.get("timestamp", "")
                recordable = msg.get("recordable", True)
                color      = self.act_colors.get(activity, self.MUTED)
                try:
                    self.act_lbl.config(text=activity, fg=color)
                    self.fps_lbl.config(text=f"FPS: {fps:.1f}")
                except: pass
                if frame_bgr is not None: self._show_frame(frame_bgr)
                if self._on_result: self._on_result(activity, fps, ts, frame_bgr, recordable)
        except queue.Empty: pass
        self.after(33, self._poll)

    def _show_frame(self, frame_bgr):
        try:
            import cv2
            cw = self.cam_canvas.winfo_width() or 780
            ch = self.cam_canvas.winfo_height() or 440
            fh, fw = frame_bgr.shape[:2]
            scale = min(cw/fw, ch/fh)
            nw, nh = int(fw*scale), int(fh*scale)
            rgb = cv2.cvtColor(cv2.resize(frame_bgr,(nw,nh)), cv2.COLOR_BGR2RGB)
            self._tk_img = ImageTk.PhotoImage(image=Image.fromarray(rgb))
            self.cam_canvas.delete("all")
            self.cam_canvas.create_image((cw-nw)//2, (ch-nh)//2, anchor="nw", image=self._tk_img)
        except: pass

    def _close(self):
        self.camera_on = False
        if self._detector: self._detector.stop(); self._detector = None
        if self._on_close: self._on_close()
        self.destroy()


# ============================================================
# DASHBOARD
# ============================================================
class DashboardApp(tk.Toplevel):

    # --- mockup color palette ---
    BG         = "#8a97a3"   # mid gray-blue (matches gradient midpoint)
    GRAD_TOP   = "#bdc3c9"
    GRAD_BOT   = "#39475c"
    SIDEBAR_BG = "#7a8896"
    CARD_BG    = "#a3b1b3"
    PANEL_BG   = "#8d9da6"
    NAV_ACTIVE = "#6b7f8e"
    NAV_HOVER  = "#7d8f9c"
    ACCENT     = "#3B82F6"
    SUCCESS    = "#22C55E"
    WARNING    = "#F59E0B"
    ERROR      = "#EF4444"
    TEXT       = "#1c1e1f"
    TEXT_DARK  = "#16233a"
    MUTED      = "#4a5665"
    BORDER     = "rgba(0,0,0,0.12)"
    WHITE      = "#ffffff"
    INPUT_BG   = "#a3b1b3"

    ACT_COLORS = {
        "Writing on Board":        "#2563EB",
        "Instructional Gesturing": "#0891B2",
        "Ambient / Idle":          "#64748B",
    }

    CAMERA_SOURCE = 0

    DEFAULT_SCHEDULE = [
        {"period":"Prelim",  "week":"Week 6",  "date":"","time_start":"07:30","time_end":"09:00","status":"Pending"},
        {"period":"Midterm", "week":"Week 11", "date":"","time_start":"07:30","time_end":"09:00","status":"Pending"},
        {"period":"Finals",  "week":"Week 17", "date":"","time_start":"07:30","time_end":"09:00","status":"Pending"},
    ]

    def __init__(self, root, username="admin"):
        super().__init__(root)
        self.root     = root
        self.username = username.title()

        self.session_subject    = tk.StringVar(value="")
        self.session_section    = tk.StringVar(value="")
        self.session_instructor = tk.StringVar(value=self.username)
        self.session_room       = tk.StringVar(value="")
        self.session_semester   = tk.StringVar(value="1st Semester")
        self.session_school_yr  = tk.StringVar(value="2024-2025")
        self.session_date       = tk.StringVar(value=datetime.date.today().strftime("%B %d, %Y"))
        self.duration_limit_h   = tk.IntVar(value=0)
        self.duration_limit_m   = tk.IntVar(value=0)

        self.schedule_rows = copy.deepcopy(self.DEFAULT_SCHEDULE)

        self.camera_on            = False
        self.elapsed_sec          = 0
        self.activity_counts      = {k: 0 for k in self.ACT_COLORS}
        self.total_frames         = 0
        self.session_log          = []
        self.current_act          = "--"
        self.current_fps          = 0.0
        self._live_win            = None
        self._limit_sec           = 0
        self._bar_refs            = {}
        self.active_faculty_name  = None
        self.active_faculty_photo = None
        self._nav_img_refs        = []   # keep image refs alive

        self.title("VOCA - Dashboard")
        self.geometry("1280x720")
        self.minsize(960, 600)
        self.configure(bg=self.BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._center_window()
        self._build_ui()
        self._refresh_clock()

    def _center_window(self):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"1280x720+{(sw-1280)//2}+{(sh-720)//2}")

    # --------------------------------------------------------
    # GRADIENT CANVAS BACKGROUND
    # --------------------------------------------------------
    def _draw_gradient(self, canvas, w, h, top, bot):
        """Draw a vertical gradient on a canvas."""
        def hex_to_rgb(h):
            h = h.lstrip("#")
            return tuple(int(h[i:i+2],16) for i in (0,2,4))
        r1,g1,b1 = hex_to_rgb(top)
        r2,g2,b2 = hex_to_rgb(bot)
        steps = h
        for i in range(steps):
            t = i/max(steps-1,1)
            r = int(r1 + (r2-r1)*t)
            g = int(g1 + (g2-g1)*t)
            b = int(b1 + (b2-b1)*t)
            color = f"#{r:02x}{g:02x}{b:02x}"
            canvas.create_line(0, i, w, i, fill=color)

    # --------------------------------------------------------
    # MAIN LAYOUT
    # --------------------------------------------------------
    def _build_ui(self):
        # Root frame with gradient background
        self.root_frame = tk.Frame(self, bg=self.BG)
        self.root_frame.pack(fill="both", expand=True)

        # Gradient background canvas
        self.bg_canvas = tk.Canvas(self.root_frame, highlightthickness=0, bd=0)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.bg_canvas.bind("<Configure>", lambda e: self._draw_gradient(
            self.bg_canvas, e.width, e.height, self.GRAD_TOP, self.GRAD_BOT))

        # Sidebar
        self._build_sidebar()

        # Main content area
        self.main_frame = tk.Frame(self.root_frame, bg=self.BG, highlightthickness=0)
        self.main_frame.place(x=310, y=0, relwidth=1, relheight=1, width=-310)
        self._build_topbar()

        self.content_frame = tk.Frame(self.main_frame, bg=self.BG)
        self.content_frame.place(x=0, y=70, relwidth=1, relheight=1, height=-70)

        # Open Faculty page first (as per requirement)
        self._show_faculty()

    # --------------------------------------------------------
    # SIDEBAR
    # --------------------------------------------------------
    def _build_sidebar(self):
        sb = tk.Frame(self.root_frame, bg=self.BG, highlightthickness=0, width=310)
        sb.place(x=0, y=0, width=310, relheight=1)

        # Semi-transparent sidebar canvas
        self.sb_canvas = tk.Canvas(sb, highlightthickness=0, bd=0, width=310)
        self.sb_canvas.place(x=0, y=0, relwidth=1, relheight=1)

        def _draw_sb(e=None):
            self.sb_canvas.delete("all")
            w = sb.winfo_width() or 310
            h = sb.winfo_height() or 720
            self._draw_gradient(self.sb_canvas, w, h, "#bdc3c9", "#5e6b7b")
            # right border
            self.sb_canvas.create_line(w-1, 0, w-1, h, fill="rgba(0,0,0,0.15)" if False else "#b0b8c1")

        self.sb_canvas.bind("<Configure>", _draw_sb)
        sb.bind("<Configure>", lambda e: _draw_sb())

        # --- VOCA logo + wordmark ---
        logo_frame = tk.Frame(sb, bg=self.BG)
        logo_frame.place(x=20, y=18, width=270, height=90)

        # wordmark image
        wm_img = _load_img("voca-wordmark.png", (200, 60))
        if wm_img:
            self._nav_img_refs.append(wm_img)
            tk.Label(logo_frame, image=wm_img, bg=self.GRAD_TOP,
                     highlightthickness=0).pack(anchor="w")
        else:
            tk.Label(logo_frame, text="VOCA", font=("Poppins",22,"bold"),
                     fg=self.TEXT_DARK, bg=self.GRAD_TOP).pack(anchor="w")

        # separator line
        tk.Frame(sb, bg="#b0b8c1", height=1).place(x=20, y=105, width=270)

        # --- nav buttons ---
        self.nav_btns  = {}
        self.nav_frame = tk.Frame(sb, bg=self.BG)
        self.nav_frame.place(x=20, y=115, width=270)

        nav_items = [
            ("Faculty",       self._show_faculty),
            ("Dashboard",     self._show_dashboard),
            ("Session Setup", self._show_session_setup),
            ("Reports",       self._show_reports),
            ("Settings",      self._show_settings),
        ]

        for label, cmd in nav_items:
            btn = tk.Button(self.nav_frame,
                            text=f"  {label}",
                            font=("Poppins", 11),
                            bg=self.CARD_BG, fg=self.TEXT_DARK,
                            activebackground=self.NAV_ACTIVE,
                            activeforeground=self.TEXT_DARK,
                            relief="flat", bd=0,
                            anchor="w", padx=16, pady=10,
                            cursor="hand2",
                            highlightthickness=1,
                            highlightbackground="#c0c8d0",
                            command=cmd)
            btn.pack(fill="x", pady=4, ipady=2)
            # rounded look via custom relief
            self.nav_btns[label] = btn

        self._set_nav("Faculty")

        # separator
        tk.Frame(sb, bg="#b0b8c1", height=1).place(x=20, y=530, width=270)

        # --- user info at bottom ---
        user_frame = tk.Frame(sb, bg=self.BG)
        user_frame.place(x=20, y=540, width=270, height=120)

        # shield icon
        shield_img = _load_img("shield_pfp_icon.png", (32, 32))
        if shield_img:
            self._nav_img_refs.append(shield_img)
            tk.Label(user_frame, image=shield_img, bg=self.CARD_BG,
                     highlightthickness=0).pack(side="left", padx=(0,10))
        else:
            tk.Label(user_frame, text="👤", font=("Arial",18),
                     bg=self.CARD_BG).pack(side="left", padx=(0,10))

        info = tk.Frame(user_frame, bg=self.BG); info.pack(side="left", fill="y")
        tk.Label(info, text=f"User: {self.username}",
                 font=("Poppins",10,"bold"), fg=self.TEXT_DARK,
                 bg=self.BG).pack(anchor="w")
        tk.Label(info, text="Authorized Personnel",
                 font=("Poppins",8), fg=self.MUTED,
                 bg=self.BG).pack(anchor="w")

        # Logout button
        tk.Button(sb, text="Logout",
                  font=("Poppins",10),
                  bg=self.CARD_BG, fg=self.TEXT_DARK,
                  activebackground=self.ERROR, activeforeground=self.WHITE,
                  relief="flat", bd=0,
                  padx=20, pady=8,
                  cursor="hand2",
                  highlightthickness=1,
                  highlightbackground="#c0c8d0",
                  command=self._logout).place(x=20, y=650, width=270)

    def _set_nav(self, active):
        for label, btn in self.nav_btns.items():
            if label == active:
                btn.config(bg=self.NAV_ACTIVE, fg=self.WHITE,
                           font=("Poppins",11,"bold"),
                           highlightbackground=self.NAV_ACTIVE)
            else:
                btn.config(bg=self.CARD_BG, fg=self.TEXT_DARK,
                           font=("Poppins",11),
                           highlightbackground="#c0c8d0")

    # --------------------------------------------------------
    # TOP BAR
    # --------------------------------------------------------
    def _build_topbar(self):
        self.topbar = tk.Frame(self.main_frame, bg=self.CARD_BG,
                               highlightbackground="#c0c8d0", highlightthickness=1)
        self.topbar.place(x=20, y=10, relwidth=1, height=52, width=-40)

        self.page_title_var = tk.StringVar(value="FACULTY")
        tk.Label(self.topbar, textvariable=self.page_title_var,
                 font=("Poppins",13,"bold"), fg=self.TEXT_DARK,
                 bg=self.CARD_BG).pack(side="left", padx=20, pady=14)

        self.clock_var = tk.StringVar()
        tk.Label(self.topbar, textvariable=self.clock_var,
                 font=("Poppins",9), fg=self.MUTED,
                 bg=self.CARD_BG).pack(side="right", padx=20)

    # --------------------------------------------------------
    # SCROLL HELPER
    # --------------------------------------------------------
    def _make_scroll_area(self, parent):
        outer = tk.Frame(parent, bg=self.BG); outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=self.BG, highlightthickness=0)
        vsb    = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        sf    = tk.Frame(canvas, bg=self.BG); sf_id = canvas.create_window((0,0), window=sf, anchor="nw")
        sf.bind("<Configure>",     lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(sf_id, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))
        return sf

    # --------------------------------------------------------
    # SECTION LABEL
    # --------------------------------------------------------
    def _sec_label(self, parent, text):
        tk.Label(parent, text=text, font=("Poppins",10,"bold"),
                 fg=self.TEXT_DARK, bg=self.BG).pack(anchor="w", pady=(14,4))

    # --------------------------------------------------------
    # PILL CARD (matches mockup rounded cards)
    # --------------------------------------------------------
    def _pill_card(self, parent, pady=8):
        c = tk.Frame(parent, bg=self.PANEL_BG,
                     highlightbackground="#c0c8d0", highlightthickness=1)
        c.pack(fill="x", padx=20, pady=pady)
        return c

    # --------------------------------------------------------
    # FACULTY PAGE  (default/first page shown)
    # --------------------------------------------------------
    def _show_faculty(self):
        self._clear_content()
        self._set_nav("Faculty")
        self.page_title_var.set("FACULTY")
        sf = self._make_scroll_area(self.content_frame)

        # --- page heading ---
        hdr = tk.Frame(sf, bg=self.BG); hdr.pack(fill="x", padx=20, pady=(16,4))
        tk.Label(hdr, text="FACULTY MANAGEMENT", font=("Poppins",13,"bold"),
                 fg=self.TEXT_DARK, bg=self.BG).pack(anchor="w")
        tk.Label(hdr, text="Register faculty members with their photo. Set one as Active before recording so the system only detects that professor.",
                 font=("Poppins",8), fg=self.MUTED, bg=self.BG,
                 wraplength=860, justify="left").pack(anchor="w", pady=(2,0))

        # --- active faculty banner ---
        active_name  = getattr(self, "active_faculty_name", None)
        active_photo = getattr(self, "active_faculty_photo", None)

        active_card = tk.Frame(sf, bg=self.PANEL_BG,
                               highlightbackground="#c0c8d0", highlightthickness=1)
        active_card.pack(fill="x", padx=20, pady=(10,4))

        inner = tk.Frame(active_card, bg=self.PANEL_BG, pady=12, padx=16)
        inner.pack(fill="x")

        # pfp icon for active banner
        pfp_white = _load_img("pfp_icon_white.png", (38, 38))
        if active_name and active_photo and os.path.exists(active_photo):
            try:
                thumb = Image.open(active_photo).resize((38,38), Image.LANCZOS)
                tk_thumb = ImageTk.PhotoImage(thumb)
                self._nav_img_refs.append(tk_thumb)
                tk.Label(inner, image=tk_thumb, bg=self.PANEL_BG).pack(side="left", padx=(0,12))
            except:
                if pfp_white:
                    self._nav_img_refs.append(pfp_white)
                    tk.Label(inner, image=pfp_white, bg=self.PANEL_BG).pack(side="left", padx=(0,12))
        else:
            if pfp_white:
                self._nav_img_refs.append(pfp_white)
                tk.Label(inner, image=pfp_white, bg=self.PANEL_BG).pack(side="left", padx=(0,12))

        lbl_text = f"ACTIVE FACULTY:  {active_name}" if active_name else "ACTIVE FACULTY:  None"
        tk.Label(inner, text=lbl_text,
                 font=("Poppins",11,"bold"), fg=self.TEXT_DARK,
                 bg=self.PANEL_BG).pack(side="left")

        if active_name:
            tk.Button(inner, text="Clear",
                      font=("Poppins",8), bg=self.CARD_BG, fg=self.ERROR,
                      activebackground=self.ERROR, activeforeground=self.WHITE,
                      bd=0, padx=10, pady=4, cursor="hand2",
                      highlightthickness=1, highlightbackground="#c0c8d0",
                      command=self._clear_active_faculty).pack(side="right", padx=(0,4))

        # --- REGISTERED FACULTY section ---
        self._sec_label(sf, "REGISTERED FACULTY")
        reg_card = tk.Frame(sf, bg=self.PANEL_BG,
                            highlightbackground="#c0c8d0", highlightthickness=1)
        reg_card.pack(fill="x", padx=20, pady=4)
        inner_reg = tk.Frame(reg_card, bg=self.PANEL_BG, pady=16, padx=20)
        inner_reg.pack(fill="x")

        # left: form | right: photo preview
        form_row = tk.Frame(inner_reg, bg=self.PANEL_BG); form_row.pack(fill="x")
        left  = tk.Frame(form_row, bg=self.PANEL_BG); left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(form_row, bg=self.PANEL_BG, padx=20); right.pack(side="right")

        # Faculty name field
        tk.Label(left, text="FACULTY NAME", font=("Poppins",9,"bold"),
                 fg=self.TEXT_DARK, bg=self.PANEL_BG).pack(anchor="w", pady=(0,4))
        self._fac_name_var = tk.StringVar()
        name_entry = tk.Entry(left, textvariable=self._fac_name_var,
                              font=("Poppins",11), bg=self.INPUT_BG, fg=self.TEXT_DARK,
                              insertbackground=self.TEXT_DARK, relief="flat",
                              highlightthickness=1, highlightbackground="#c0c8d0",
                              highlightcolor="#8a9ba8")
        name_entry.pack(fill="x", ipady=9, pady=(0,12))

        # Photo preview box
        tk.Label(right, text="PHOTO PREVIEW", font=("Poppins",9,"bold"),
                 fg=self.TEXT_DARK, bg=self.PANEL_BG).pack(anchor="w", pady=(0,4))
        preview_outer = tk.Frame(right, bg=self.CARD_BG,
                                 highlightbackground="#c0c8d0", highlightthickness=1,
                                 width=130, height=130)
        preview_outer.pack(); preview_outer.pack_propagate(False)

        # default pfp icon in preview
        pfp_dark = _load_img("pfp_icon.png", (80, 80))
        if pfp_dark:
            self._nav_img_refs.append(pfp_dark)
            self._fac_photo_lbl = tk.Label(preview_outer, image=pfp_dark,
                                            bg=self.CARD_BG)
        else:
            self._fac_photo_lbl = tk.Label(preview_outer, text="No photo",
                                            font=("Poppins",8), fg=self.MUTED,
                                            bg=self.CARD_BG)
        self._fac_photo_lbl.pack(expand=True)
        self._fac_photo_path = None
        self._fac_tk_img     = None

        # msg label
        self._fac_msg_var = tk.StringVar(value="")
        fac_msg = tk.Label(inner_reg, textvariable=self._fac_msg_var,
                           font=("Poppins",8), fg=self.SUCCESS, bg=self.PANEL_BG)
        fac_msg.pack(anchor="w", pady=(4,8))

        def _pick():
            path = filedialog.askopenfilename(
                title="Select Faculty Photo",
                filetypes=[("Image files","*.jpg *.jpeg *.png *.bmp")])
            if not path: return
            self._fac_photo_path = path
            try:
                img = Image.open(path).resize((120,120), Image.LANCZOS)
                self._fac_tk_img = ImageTk.PhotoImage(img)
                self._nav_img_refs.append(self._fac_tk_img)
                self._fac_photo_lbl.config(image=self._fac_tk_img, text="")
            except:
                self._fac_photo_lbl.config(text=os.path.basename(path), image="")

        def _save():
            name = self._fac_name_var.get().strip()
            if not name:
                self._fac_msg_var.set("Please enter the faculty name."); fac_msg.config(fg=self.ERROR); return
            if not self._fac_photo_path:
                self._fac_msg_var.set("Please select a photo first."); fac_msg.config(fg=self.ERROR); return
            if not DB_OK:
                self._fac_msg_var.set("Database not available."); fac_msg.config(fg=self.ERROR); return
            try:
                ext  = os.path.splitext(self._fac_photo_path)[1]
                dest = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    f"faculty_{name.replace(' ','_')}{ext}")
                shutil.copy2(self._fac_photo_path, dest)
                save_faculty(name, dest)
                self._fac_msg_var.set(f"Faculty {name} saved successfully.")
                fac_msg.config(fg=self.SUCCESS)
                self._fac_name_var.set("")
                self._fac_photo_path = None
                self._show_faculty()
            except Exception as e:
                self._fac_msg_var.set(f"Error: {e}"); fac_msg.config(fg=self.ERROR)

        # action buttons row
        btn_row = tk.Frame(inner_reg, bg=self.PANEL_BG); btn_row.pack(anchor="w", pady=(0,4))

        def _pill_btn(parent, text, cmd, bg=None, fg=None):
            bg = bg or self.CARD_BG; fg = fg or self.TEXT_DARK
            return tk.Button(parent, text=text, font=("Poppins",9),
                             bg=bg, fg=fg,
                             activebackground=self.NAV_ACTIVE, activeforeground=self.WHITE,
                             relief="flat", bd=0, padx=14, pady=8, cursor="hand2",
                             highlightthickness=1, highlightbackground="#c0c8d0",
                             command=cmd)

        _pill_btn(btn_row, "TAKE A PHOTO",  lambda: messagebox.showinfo("Camera","Camera capture coming soon.")).pack(side="left", padx=(0,8))
        _pill_btn(btn_row, "UPLOAD PHOTO",  _pick).pack(side="left", padx=(0,8))
        _pill_btn(btn_row, "SAVE FACULTY",  _save, bg=self.NAV_ACTIVE, fg=self.WHITE).pack(side="left")

        # --- REGISTERED FACULTY LIST ---
        self._sec_label(sf, "REGISTERED FACULTY (CLICK SET ACTIVE TO USE FOR RECORDING)")
        list_card = tk.Frame(sf, bg=self.PANEL_BG,
                             highlightbackground="#c0c8d0", highlightthickness=1)
        list_card.pack(fill="x", padx=20, pady=(4,16))

        try:
            faculty_list = load_faculty_list() if DB_OK else []
        except:
            faculty_list = []

        if not faculty_list:
            tk.Label(list_card, text="No faculty registered yet. Add one above.",
                     font=("Poppins",9), fg=self.MUTED, bg=self.PANEL_BG,
                     pady=16).pack(anchor="w", padx=20)
        else:
            for fid, fname, fphoto in faculty_list:
                is_active = (fname == getattr(self,"active_faculty_name",None))
                row_bg    = self.PANEL_BG
                row = tk.Frame(list_card, bg=row_bg, pady=10, padx=16)
                row.pack(fill="x")

                # thumbnail
                pfp_dark2 = _load_img("pfp_icon.png", (52, 52))
                if fphoto and os.path.exists(fphoto):
                    try:
                        thumb  = Image.open(fphoto).resize((52,52), Image.LANCZOS)
                        tkimg  = ImageTk.PhotoImage(thumb)
                        self._nav_img_refs.append(tkimg)
                        lbl    = tk.Label(row, image=tkimg, bg=row_bg)
                        lbl.pack(side="left", padx=(0,14))
                    except:
                        if pfp_dark2:
                            self._nav_img_refs.append(pfp_dark2)
                            tk.Label(row, image=pfp_dark2, bg=row_bg).pack(side="left", padx=(0,14))
                else:
                    if pfp_dark2:
                        self._nav_img_refs.append(pfp_dark2)
                        tk.Label(row, image=pfp_dark2, bg=row_bg).pack(side="left", padx=(0,14))

                # name + status
                info = tk.Frame(row, bg=row_bg); info.pack(side="left", fill="both", expand=True)
                tk.Label(info, text=f"({fname})", font=("Poppins",11,"bold"),
                         fg=self.TEXT_DARK, bg=row_bg).pack(anchor="w")
                if is_active:
                    tk.Label(info, text="ACTIVE - Camera will only detect this person",
                             font=("Poppins",8), fg=self.SUCCESS, bg=row_bg).pack(anchor="w")
                else:
                    tk.Label(info, text="Not active",
                             font=("Poppins",8), fg=self.MUTED, bg=row_bg).pack(anchor="w")

                # buttons
                btn_f = tk.Frame(row, bg=row_bg); btn_f.pack(side="right", padx=(0,4))
                if not is_active:
                    tk.Button(btn_f, text="Set Active",
                              font=("Poppins",9),
                              bg=self.CARD_BG, fg=self.TEXT_DARK,
                              activebackground=self.NAV_ACTIVE, activeforeground=self.WHITE,
                              relief="flat", bd=0, padx=12, pady=6, cursor="hand2",
                              highlightthickness=1, highlightbackground="#c0c8d0",
                              command=lambda n=fname, p=fphoto: self._set_active_faculty(n,p)
                              ).pack(side="left", padx=(0,8))
                tk.Button(btn_f, text="DELETE",
                          font=("Poppins",9),
                          bg=self.CARD_BG, fg=self.TEXT_DARK,
                          activebackground=self.ERROR, activeforeground=self.WHITE,
                          relief="flat", bd=0, padx=12, pady=6, cursor="hand2",
                          highlightthickness=1, highlightbackground="#c0c8d0",
                          command=lambda i=fid, n=fname: self._delete_faculty(i,n)
                          ).pack(side="left")

                tk.Frame(list_card, bg="#c0c8d0", height=1).pack(fill="x", padx=16)

        # footer
        tk.Label(sf, text="© 2026 VOCA System · BS Computer Science",
                 font=("Poppins",8), fg=self.MUTED, bg=self.BG).pack(pady=(8,16))

    def _set_active_faculty(self, name, photo):
        self.active_faculty_name  = name
        self.active_faculty_photo = photo
        self.session_instructor.set(name)
        messagebox.showinfo("Active Faculty Set",
                            f"{name} is now the active faculty.\n"
                            "The camera will only detect and record this person.")
        self._show_faculty()

    def _clear_active_faculty(self):
        self.active_faculty_name  = None
        self.active_faculty_photo = None
        self._show_faculty()

    def _delete_faculty(self, fid, name):
        if not messagebox.askyesno("Delete", f"Delete {name} from the system?"): return
        try:
            delete_faculty(fid)
            if getattr(self,"active_faculty_name",None) == name:
                self.active_faculty_name  = None
                self.active_faculty_photo = None
            self._show_faculty()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # --------------------------------------------------------
    # DASHBOARD PAGE
    # --------------------------------------------------------
    def _show_dashboard(self):
        self._bar_refs = {}
        self._clear_content()
        self._set_nav("Dashboard")
        self.page_title_var.set("DASHBOARD")
        sf = self._make_scroll_area(self.content_frame)

        hdr = tk.Frame(sf, bg=self.BG); hdr.pack(fill="x", padx=20, pady=(16,8))
        tk.Label(hdr, text="DASHBOARD  -  Overview", font=("Poppins",13,"bold"),
                 fg=self.TEXT_DARK, bg=self.BG).pack(anchor="w")

        # session info chips
        info = tk.Frame(sf, bg=self.PANEL_BG,
                        highlightbackground="#c0c8d0", highlightthickness=1)
        info.pack(fill="x", padx=20, pady=4)
        inner_info = tk.Frame(info, bg=self.PANEL_BG, padx=16, pady=12); inner_info.pack(fill="x")
        r1 = tk.Frame(inner_info, bg=self.PANEL_BG); r1.pack(fill="x")
        self._chip(r1, "Subject",    self.session_subject.get()    or "--")
        self._chip(r1, "Section",    self.session_section.get()    or "--")
        self._chip(r1, "Instructor", self.session_instructor.get() or "--")
        r2 = tk.Frame(inner_info, bg=self.PANEL_BG); r2.pack(fill="x", pady=(6,0))
        self._chip(r2, "Room",     self.session_room.get() or "--")
        self._chip(r2, "Date",     self.session_date.get() or "--")
        self._chip(r2, "Semester", f"{self.session_semester.get()} {self.session_school_yr.get()}")
        h, m = self.duration_limit_h.get(), self.duration_limit_m.get()
        self._chip(r2, "Duration Limit", f"{h}h {m:02d}m" if (h or m) else "Unlimited")
        tk.Button(inner_info, text="Edit Session Info", font=("Poppins",8),
                  bg=self.CARD_BG, fg=self.TEXT_DARK,
                  activebackground=self.NAV_ACTIVE, activeforeground=self.WHITE,
                  relief="flat", bd=0, padx=10, pady=5, cursor="hand2",
                  highlightthickness=1, highlightbackground="#c0c8d0",
                  command=self._show_session_setup).pack(anchor="e", pady=(8,0))

        # status banner
        bb  = "#22C55E" if self.camera_on else self.PANEL_BG
        bt  = (f"LIVE  -  {self.current_act}  |  FPS: {self.current_fps:.1f}"
               if self.camera_on else "Camera not started  -  Press Start Recording below")
        banner = tk.Frame(sf, bg=bb, highlightbackground="#c0c8d0", highlightthickness=1)
        banner.pack(fill="x", padx=20, pady=4)
        tk.Label(banner, text=bt, font=("Poppins",9,"bold"),
                 fg=self.WHITE if self.camera_on else self.MUTED, bg=bb,
                 pady=10).pack()

        # stat cards
        row = tk.Frame(sf, bg=self.BG); row.pack(fill="x", padx=20, pady=8)
        self._stat_card(row, "Active Teaching",
                        f"{self._active_pct()}%" if self.camera_on else "--",
                        "#22C55E", "Writing + Gesturing")
        self._stat_card(row, "Session Duration",
                        self._fmt_elapsed() if self.camera_on else "--",
                        "#2563EB", "HH:MM:SS")
        self._stat_card(row, "Log Entries",
                        str(len(self.session_log)) if self.session_log else "--",
                        "#D97706", "Detected activities")

        # activity bars
        self._sec_label(sf, "Activity Distribution")
        mon = tk.Frame(sf, bg=self.PANEL_BG, highlightbackground="#c0c8d0", highlightthickness=1)
        mon.pack(fill="x", padx=20, pady=4)
        inner_mon = tk.Frame(mon, bg=self.PANEL_BG, padx=16, pady=14); inner_mon.pack(fill="x")
        bars = tk.Frame(inner_mon, bg=self.PANEL_BG); bars.pack(fill="x", pady=4)
        for act in self.ACT_COLORS:
            self._act_bar(bars, act, self._pct_for(act))

        # timer row
        trow = tk.Frame(inner_mon, bg=self.PANEL_BG); trow.pack(fill="x", pady=(10,4))
        tk.Label(trow, text="Elapsed:", font=("Poppins",9), fg=self.MUTED, bg=self.PANEL_BG).pack(side="left")
        self.timer_lbl = tk.Label(trow,
                                  text=self._fmt_elapsed() if self.camera_on else "--",
                                  font=("Poppins",9,"bold"), fg="#2563EB", bg=self.PANEL_BG)
        self.timer_lbl.pack(side="left", padx=(4,24))

        lim_sec = self.duration_limit_h.get()*3600 + self.duration_limit_m.get()*60
        if lim_sec > 0:
            remaining = max(0, lim_sec - self.elapsed_sec)
            cd_color  = (self.ERROR if remaining <= lim_sec*0.10 else
                         self.WARNING if remaining <= lim_sec*0.30 else "#22C55E")
            tk.Label(trow, text="Remaining:", font=("Poppins",9), fg=self.MUTED, bg=self.PANEL_BG).pack(side="left")
            self.countdown_lbl = tk.Label(trow,
                text=self._fmt_sec(remaining) if self.camera_on else self._fmt_sec(lim_sec),
                font=("Poppins",9,"bold"), fg=cd_color, bg=self.PANEL_BG)
            self.countdown_lbl.pack(side="left", padx=(4,0))
            tk.Label(trow, text=f"/ {self._fmt_sec(lim_sec)} limit",
                     font=("Poppins",8), fg=self.MUTED, bg=self.PANEL_BG).pack(side="left", padx=(6,0))
        else:
            self.countdown_lbl = None

        if not self.camera_on:
            tk.Button(inner_mon, text="START RECORDING  (opens live feed window)",
                      font=("Poppins",11,"bold"), bg=self.NAV_ACTIVE, fg=self.WHITE,
                      activebackground="#22C55E", activeforeground=self.WHITE,
                      relief="flat", bd=0, pady=12, cursor="hand2",
                      highlightthickness=1, highlightbackground="#c0c8d0",
                      command=self._start_camera).pack(fill="x", pady=(8,0))
        else:
            tk.Button(inner_mon, text="STOP RECORDING",
                      font=("Poppins",11,"bold"), bg=self.ERROR, fg=self.WHITE,
                      activebackground="#B91C1C", relief="flat", bd=0, pady=12,
                      cursor="hand2", command=self._stop_camera).pack(fill="x", pady=(8,0))
            tk.Button(inner_mon, text="Show Live Feed Window",
                      font=("Poppins",9), bg=self.CARD_BG, fg=self.TEXT_DARK,
                      activebackground=self.NAV_ACTIVE, activeforeground=self.WHITE,
                      relief="flat", bd=0, pady=8, cursor="hand2",
                      highlightthickness=1, highlightbackground="#c0c8d0",
                      command=self._raise_feed).pack(fill="x", pady=(6,0))

        self._sec_label(sf, "Scheduled Monitoring Periods")
        self._build_schedule_view(sf)

        self._sec_label(sf, "Recent Activity Log")
        self._build_log_view(sf)

        tk.Label(sf, text="© 2026 VOCA System · BS Computer Science",
                 font=("Poppins",8), fg=self.MUTED, bg=self.BG).pack(pady=(8,16))

    # --------------------------------------------------------
    # WIDGET HELPERS
    # --------------------------------------------------------
    def _chip(self, parent, label, value):
        f = tk.Frame(parent, bg=self.CARD_BG,
                     highlightbackground="#c0c8d0", highlightthickness=1)
        f.pack(side="left", padx=(0,8), pady=2)
        inner = tk.Frame(f, bg=self.CARD_BG, padx=10, pady=6); inner.pack()
        tk.Label(inner, text=label.upper(), font=("Poppins",7),
                 fg=self.MUTED, bg=self.CARD_BG).pack(anchor="w")
        tk.Label(inner, text=value, font=("Poppins",9,"bold"),
                 fg=self.TEXT_DARK, bg=self.CARD_BG).pack(anchor="w")

    def _stat_card(self, parent, title, value, color, subtitle):
        c = tk.Frame(parent, bg=self.PANEL_BG, padx=16, pady=14,
                     highlightbackground="#c0c8d0", highlightthickness=1)
        c.pack(side="left", fill="both", expand=True, padx=4)
        tk.Label(c, text=title,    font=("Poppins",8),          fg=self.MUTED,    bg=self.PANEL_BG).pack(anchor="w")
        tk.Label(c, text=value,    font=("Poppins",22,"bold"),  fg=color,         bg=self.PANEL_BG).pack(anchor="w")
        tk.Label(c, text=subtitle, font=("Poppins",7),          fg=self.MUTED,    bg=self.PANEL_BG).pack(anchor="w")

    def _act_bar(self, parent, activity, pct):
        row   = tk.Frame(parent, bg=self.PANEL_BG, pady=5); row.pack(fill="x")
        color = self.ACT_COLORS.get(activity, "#2563EB")
        name_lbl = tk.Label(row, text=activity, font=("Poppins",8),
                            fg=self.TEXT_DARK if pct > 0 else self.MUTED,
                            bg=self.PANEL_BG, width=26, anchor="w")
        name_lbl.pack(side="left")
        bar_bg = tk.Frame(row, bg="#c0c8d0", height=14, width=220)
        bar_bg.pack(side="left", padx=(6,6)); bar_bg.pack_propagate(False)
        fill_bar = tk.Frame(bar_bg, bg=color, height=14,
                            width=max(4, int(220*pct/100)) if pct > 0 else 0)
        if pct > 0: fill_bar.place(x=0, y=0)
        pct_lbl = tk.Label(row, text=f"{pct}%", font=("Poppins",8,"bold"),
                           fg=color if pct > 0 else self.MUTED,
                           bg=self.PANEL_BG, width=5, anchor="e")
        pct_lbl.pack(side="left")
        self._bar_refs[activity] = {"fill": fill_bar, "pct_lbl": pct_lbl, "name_lbl": name_lbl}

    def _build_schedule_view(self, parent):
        card = tk.Frame(parent, bg=self.PANEL_BG, highlightbackground="#c0c8d0", highlightthickness=1)
        card.pack(fill="x", padx=20, pady=4)
        inner = tk.Frame(card, bg=self.PANEL_BG, padx=16, pady=12); inner.pack(fill="x")
        headers    = ["Period","Week","Date","Start","End","Status"]
        col_widths = [9, 9, 14, 8, 8, 12]
        hrow = tk.Frame(inner, bg="#c0c8d0"); hrow.pack(fill="x", pady=(0,4))
        for h, w in zip(headers, col_widths):
            tk.Label(hrow, text=h, font=("Poppins",8,"bold"), fg=self.MUTED,
                     bg="#c0c8d0", width=w, anchor="w", padx=6, pady=6).pack(side="left")
        self._dash_sched_vars = []
        for i, rd in enumerate(self.schedule_rows):
            bg = self.PANEL_BG if i % 2 == 0 else self.CARD_BG
            dr = tk.Frame(inner, bg=bg, pady=3); dr.pack(fill="x")
            tk.Label(dr, text=rd["period"], font=("Poppins",9,"bold"),
                     fg=self.TEXT_DARK, bg=bg, width=9, anchor="w", padx=6).pack(side="left")
            vs = {}
            for key, width, default in [
                ("week",9,rd.get("week","")),("date",14,rd.get("date","")),
                ("time_start",8,rd.get("time_start","07:30")),("time_end",8,rd.get("time_end","09:00"))]:
                vs[key] = tk.StringVar(value=default)
                tk.Entry(dr, textvariable=vs[key], font=("Poppins",9),
                         bg=self.INPUT_BG, fg=self.TEXT_DARK,
                         insertbackground=self.TEXT_DARK, relief="flat",
                         width=width).pack(side="left", padx=2, ipady=4)
            vs["status"] = tk.StringVar(value=rd.get("status","Pending"))
            ttk.Combobox(dr, textvariable=vs["status"], values=["Pending","Done","Skipped"],
                         font=("Poppins",9), state="readonly", width=10).pack(side="left", padx=4)
            self._dash_sched_vars.append(vs)
        def _save():
            for i, vs in enumerate(self._dash_sched_vars):
                for key in ["week","date","time_start","time_end","status"]:
                    self.schedule_rows[i][key] = vs[key].get()
            save_btn.config(text="Saved!", bg="#22C55E", fg=self.WHITE)
            inner.after(1500, lambda: save_btn.config(text="Save Schedule", bg=self.CARD_BG, fg=self.TEXT_DARK))
        save_btn = tk.Button(inner, text="Save Schedule", font=("Poppins",9,"bold"),
                             bg=self.CARD_BG, fg=self.TEXT_DARK,
                             activebackground="#22C55E", activeforeground=self.WHITE,
                             relief="flat", bd=0, padx=12, pady=7, cursor="hand2",
                             highlightthickness=1, highlightbackground="#c0c8d0",
                             command=_save)
        save_btn.pack(anchor="e", pady=(10,0))

    def _build_log_view(self, parent):
        card = tk.Frame(parent, bg=self.PANEL_BG, highlightbackground="#c0c8d0", highlightthickness=1)
        card.pack(fill="x", padx=20, pady=4)
        inner = tk.Frame(card, bg=self.PANEL_BG, padx=16, pady=12); inner.pack(fill="x")
        if not self.session_log:
            tk.Label(inner, text="No activity recorded yet. Press Start Recording to begin.",
                     font=("Poppins",9), fg=self.MUTED, bg=self.PANEL_BG, pady=12).pack()
            return
        hrow = tk.Frame(inner, bg="#c0c8d0"); hrow.pack(fill="x", pady=(0,4))
        for h, w in [("Time",10),("Activity",28),("User",16)]:
            tk.Label(hrow, text=h, font=("Poppins",8,"bold"), fg=self.MUTED,
                     bg="#c0c8d0", width=w, anchor="w", padx=8, pady=6).pack(side="left")
        for ts, act in reversed(self.session_log[-8:]):
            row = tk.Frame(inner, bg=self.PANEL_BG, pady=4); row.pack(fill="x")
            color = self.ACT_COLORS.get(act, "#2563EB")
            tk.Label(row, text=ts,            font=("Poppins",8), fg=self.MUTED,
                     bg=self.PANEL_BG, width=10, anchor="w", padx=8).pack(side="left")
            tk.Label(row, text=act,           font=("Poppins",9,"bold"), fg=color,
                     bg=self.PANEL_BG, width=28, anchor="w").pack(side="left")
            tk.Label(row, text=self.username, font=("Poppins",8), fg=self.MUTED,
                     bg=self.PANEL_BG, width=16, anchor="w").pack(side="left")
            tk.Frame(inner, bg="#c0c8d0", height=1).pack(fill="x")

    # --------------------------------------------------------
    # SESSION SETUP PAGE
    # --------------------------------------------------------
    def _show_session_setup(self):
        self._clear_content(); self._set_nav("Session Setup")
        self.page_title_var.set("SESSION SETUP")
        sf = self._make_scroll_area(self.content_frame)

        hdr = tk.Frame(sf, bg=self.BG); hdr.pack(fill="x", padx=20, pady=(16,8))
        tk.Label(hdr, text="SESSION SETUP  -  Configure Before Recording",
                 font=("Poppins",13,"bold"), fg=self.TEXT_DARK, bg=self.BG).pack(anchor="w")

        def field(parent, label, var, hint="", row=0, col=0, colspan=1):
            f = tk.Frame(parent, bg=self.PANEL_BG)
            f.grid(row=row, column=col, columnspan=colspan, sticky="ew", padx=(0,16), pady=6)
            tk.Label(f, text=label.upper(), font=("Poppins",8,"bold"),
                     fg=self.MUTED, bg=self.PANEL_BG).pack(anchor="w")
            e = tk.Entry(f, textvariable=var, font=("Poppins",11),
                         bg=self.INPUT_BG, fg=self.TEXT_DARK,
                         insertbackground=self.TEXT_DARK, relief="flat",
                         highlightthickness=1, highlightbackground="#c0c8d0",
                         highlightcolor="#8a9ba8")
            e.pack(fill="x", ipady=7, pady=(3,0))
            if hint:
                tk.Label(f, text=hint, font=("Poppins",7), fg=self.MUTED, bg=self.PANEL_BG).pack(anchor="w")

        def dropdown(parent, label, var, options, row=0, col=0):
            f = tk.Frame(parent, bg=self.PANEL_BG)
            f.grid(row=row, column=col, sticky="ew", padx=(0,16), pady=6)
            tk.Label(f, text=label.upper(), font=("Poppins",8,"bold"),
                     fg=self.MUTED, bg=self.PANEL_BG).pack(anchor="w")
            style = ttk.Style(); style.theme_use("clam")
            style.configure("V.TCombobox",
                            fieldbackground=self.INPUT_BG, background=self.INPUT_BG,
                            foreground=self.TEXT_DARK, selectbackground="#8a9ba8",
                            selectforeground=self.TEXT_DARK, arrowcolor=self.MUTED)
            ttk.Combobox(f, textvariable=var, values=options, style="V.TCombobox",
                         font=("Poppins",11), state="readonly").pack(fill="x", ipady=4, pady=(3,0))

        c1 = tk.Frame(sf, bg=self.PANEL_BG, padx=20, pady=16,
                      highlightbackground="#c0c8d0", highlightthickness=1)
        c1.pack(fill="x", padx=20, pady=4); c1.columnconfigure((0,1,2), weight=1)

        dropdown(c1,"Course",self.session_section,["Computer Science","Information Technology","Psychology","Accountancy"],row=0,col=0)
        dropdown(c1,"Subject / Course Code",self.session_subject,["CEEL 301","CEEL 311","CS 301","CS 321","RIZAL 301","CS 311","SQ 301","HCI"],row=0,col=1)
        field(c1,"Instructor",self.session_instructor,"Full name",row=0,col=2)
        dropdown(c1,"Room / Venue",self.session_room,["1JCM CL-1","1JCM CL-2","1JCM CL-3","1JCM CL-4","R-1","R-2","R-3","R-4","R-5","R-6","R-7","R-8","R-9","R-10","R-11","R-12"],row=1,col=0)
        field(c1,"Date",self.session_date,"e.g. May 22, 2025",row=1,col=1)
        field(c1,"School Year",self.session_school_yr,"e.g. 2024-2025",row=1,col=2)
        dropdown(c1,"Semester",self.session_semester,["1st Semester","2nd Semester"],row=2,col=0)

        # Duration limit
        tk.Label(sf, text="RECORDING DURATION LIMIT", font=("Poppins",10,"bold"),
                 fg=self.TEXT_DARK, bg=self.BG).pack(anchor="w", padx=20, pady=(14,4))
        c2 = tk.Frame(sf, bg=self.PANEL_BG, padx=20, pady=16,
                      highlightbackground="#c0c8d0", highlightthickness=1)
        c2.pack(fill="x", padx=20, pady=4); c2.columnconfigure((0,1,2), weight=1)
        tk.Label(c2, text="Set a maximum recording time (0 = unlimited).",
                 font=("Poppins",8), fg=self.MUTED, bg=self.PANEL_BG
                 ).grid(row=0,column=0,columnspan=3,sticky="w",pady=(0,8))
        for col, label, var, to in [(0,"HOURS",self.duration_limit_h,8),(1,"MINUTES",self.duration_limit_m,59)]:
            f = tk.Frame(c2, bg=self.PANEL_BG); f.grid(row=1,column=col,sticky="ew",padx=(0,16))
            tk.Label(f,text=label,font=("Poppins",8,"bold"),fg=self.MUTED,bg=self.PANEL_BG).pack(anchor="w")
            tk.Spinbox(f,from_=0,to=to,textvariable=var,font=("Poppins",13,"bold"),
                       bg=self.INPUT_BG,fg="#2563EB",buttonbackground=self.INPUT_BG,
                       relief="flat",width=5,justify="center").pack(fill="x",ipady=8,pady=(3,0))
        pf = tk.Frame(c2, bg=self.PANEL_BG); pf.grid(row=1,column=2,sticky="ew")
        tk.Label(pf,text="PREVIEW",font=("Poppins",8,"bold"),fg=self.MUTED,bg=self.PANEL_BG).pack(anchor="w")
        prev_lbl = tk.Label(pf,text="",font=("Poppins",13,"bold"),fg=self.WARNING,bg=self.PANEL_BG)
        prev_lbl.pack(anchor="w",pady=(6,0))
        def _upd(*_):
            h,m=self.duration_limit_h.get(),self.duration_limit_m.get()
            prev_lbl.config(text=f"{h}h {m:02d}m limit" if (h or m) else "Unlimited")
        self.duration_limit_h.trace_add("write",_upd); self.duration_limit_m.trace_add("write",_upd); _upd()

        btn_row = tk.Frame(sf, bg=self.BG); btn_row.pack(fill="x", padx=20, pady=16)
        tk.Button(btn_row, text="Save Session Setup",
                  font=("Poppins",11,"bold"), bg=self.NAV_ACTIVE, fg=self.WHITE,
                  activebackground="#22C55E", activeforeground=self.WHITE,
                  relief="flat", bd=0, pady=12, padx=24, cursor="hand2",
                  command=self._save_session).pack(side="left")
        tk.Button(btn_row, text="Back to Dashboard",
                  font=("Poppins",9), bg=self.CARD_BG, fg=self.TEXT_DARK,
                  activebackground=self.NAV_ACTIVE, activeforeground=self.WHITE,
                  relief="flat", bd=0, pady=8, padx=16, cursor="hand2",
                  highlightthickness=1, highlightbackground="#c0c8d0",
                  command=self._show_dashboard).pack(side="left", padx=12)

        tk.Label(sf, text="© 2026 VOCA System · BS Computer Science",
                 font=("Poppins",8), fg=self.MUTED, bg=self.BG).pack(pady=(8,16))

    def _save_session(self):
        messagebox.showinfo("Saved", "Session setup saved.")
        self._show_dashboard()

    # --------------------------------------------------------
    # REPORTS PAGE
    # --------------------------------------------------------
    def _report_detail_row(self, parent, label, value):
        row = tk.Frame(parent, bg=self.CARD_BG,
                       highlightbackground="#c0c8d0", highlightthickness=1)
        row.pack(fill="x", pady=4)
        inner = tk.Frame(row, bg=self.CARD_BG); inner.pack(fill="x", padx=16, pady=9)
        tk.Label(inner, text=label, font=("Poppins",9),
                 fg=self.TEXT_DARK, bg=self.CARD_BG).pack(side="left")
        tk.Label(inner, text=value, font=("Poppins",10,"bold"),
                 fg=self.TEXT_DARK, bg=self.CARD_BG).pack(side="left", padx=(36,0))

    def _report_activity_row(self, parent, name, pct_text, color):
        row = tk.Frame(parent, bg=self.CARD_BG,
                       highlightbackground="#c0c8d0", highlightthickness=1)
        row.pack(fill="x", pady=4)
        inner = tk.Frame(row, bg=self.CARD_BG); inner.pack(fill="x", padx=16, pady=10)
        tk.Label(inner, text=name, font=("Poppins",9),
                 fg=self.TEXT_DARK, bg=self.CARD_BG).pack(side="left")
        tk.Label(inner, text=pct_text, font=("Poppins",10,"bold"),
                 fg=color, bg=self.CARD_BG).pack(side="right")

    def _show_reports(self):
        self._clear_content(); self._set_nav("Reports")
        self.page_title_var.set("TEACHING ACTIVITY REPORTS")
        sf = self._make_scroll_area(self.content_frame)

        has_data = bool(self.session_log)

        # --- two-column layout: Session Details | Activity Summary ---
        row = tk.Frame(sf, bg=self.BG); row.pack(fill="x", padx=20, pady=(16,4))
        left_col  = tk.Frame(row, bg=self.BG); left_col.pack(side="left", fill="both", expand=True, padx=(0,10))
        right_col = tk.Frame(row, bg=self.BG); right_col.pack(side="left", fill="both", expand=True, padx=(10,0))

        # ---- Session Details card ----
        details_card = tk.Frame(left_col, bg=self.PANEL_BG,
                                highlightbackground="#c0c8d0", highlightthickness=1)
        details_card.pack(fill="both", expand=True)
        inner_d = tk.Frame(details_card, bg=self.PANEL_BG, padx=18, pady=16); inner_d.pack(fill="both", expand=True)
        tk.Label(inner_d, text="Session Details", font=("Poppins",12,"bold"),
                 fg=self.TEXT_DARK, bg=self.PANEL_BG).pack(anchor="w", pady=(0,10))

        for lbl, val in [
            ("Subject:",    self.session_subject.get()    or "--"),
            ("Section:",    self.session_section.get()    or "--"),
            ("Instructor:", self.session_instructor.get() or "--"),
            ("Room:",       self.session_room.get()       or "--"),
            ("Date:",       self.session_date.get()       or "--"),
            ("Semester:",   self.session_semester.get()   or "--"),
            ("Duration:",   self._fmt_elapsed() if has_data else "--"),
        ]:
            self._report_detail_row(inner_d, lbl, val)

        # ---- Activity Summary card ----
        summary_card = tk.Frame(right_col, bg=self.PANEL_BG,
                                highlightbackground="#c0c8d0", highlightthickness=1)
        summary_card.pack(fill="both", expand=True)
        inner_s = tk.Frame(summary_card, bg=self.PANEL_BG, padx=18, pady=16); inner_s.pack(fill="both", expand=True)
        tk.Label(inner_s, text="Activity Summary", font=("Poppins",12,"bold"),
                 fg=self.TEXT_DARK, bg=self.PANEL_BG).pack(pady=(0,10))

        for act, color in self.ACT_COLORS.items():
            pct_text = f"{self._pct_for(act)}%" if has_data else "-- %"
            self._report_activity_row(inner_s, act, pct_text, color)

        btns = tk.Frame(inner_s, bg=self.PANEL_BG); btns.pack(fill="x", pady=(12,0))
        tk.Button(btns, text="\u2b07  Export Summary PDF", font=("Poppins",9,"bold"),
                  bg=self.NAV_ACTIVE, fg=self.WHITE,
                  activebackground="#22C55E", activeforeground=self.WHITE,
                  relief="flat", bd=0, pady=8, padx=12, cursor="hand2",
                  command=lambda: self._export_pdf(full=False)
                  ).pack(side="left", fill="x", expand=True, padx=(0,6))
        tk.Button(btns, text="\U0001F5C4  Save To Database", font=("Poppins",9,"bold"),
                  bg=self.CARD_BG, fg=self.TEXT_DARK,
                  activebackground=self.NAV_ACTIVE, activeforeground=self.WHITE,
                  relief="flat", bd=0, pady=8, padx=12, cursor="hand2",
                  highlightthickness=1, highlightbackground="#c0c8d0",
                  command=self._save_to_db
                  ).pack(side="left", fill="x", expand=True, padx=(6,0))

        tk.Button(inner_s, text="Export Full Log PDF", font=("Poppins",8),
                  bg=self.PANEL_BG, fg=self.MUTED,
                  activebackground=self.CARD_BG, activeforeground=self.TEXT_DARK,
                  relief="flat", bd=0, pady=4, cursor="hand2",
                  command=lambda: self._export_pdf(full=True)
                  ).pack(anchor="e", pady=(8,0))

        # --- Session Recording card (full width, video is a placeholder) ---
        rec_card = tk.Frame(sf, bg=self.PANEL_BG,
                            highlightbackground="#c0c8d0", highlightthickness=1)
        rec_card.pack(fill="x", padx=20, pady=(14,4))
        inner_r = tk.Frame(rec_card, bg=self.PANEL_BG, padx=20, pady=16); inner_r.pack(fill="x")

        hdr = tk.Frame(inner_r, bg=self.PANEL_BG); hdr.pack(anchor="w")
        icon_cv = tk.Canvas(hdr, width=34, height=22, bg=self.PANEL_BG, highlightthickness=0)
        icon_cv.pack(side="left", padx=(0,8))
        icon_cv.create_rectangle(2, 3, 23, 19, fill=self.TEXT_DARK, outline=self.TEXT_DARK)
        icon_cv.create_polygon(23,7, 32,2, 32,20, 23,15, fill=self.TEXT_DARK, outline=self.TEXT_DARK)
        icon_cv.create_polygon(9,7, 9,15, 18,11, fill=self.WHITE, outline=self.WHITE)
        tk.Label(hdr, text="Session Recording", font=("Poppins",12,"bold"),
                 fg=self.TEXT_DARK, bg=self.PANEL_BG).pack(side="left")

        body = tk.Frame(inner_r, bg=self.PANEL_BG); body.pack(fill="x", pady=(16,0))

        video_box = tk.Frame(body, bg=self.CARD_BG,
                             highlightbackground="#c0c8d0", highlightthickness=1,
                             width=280, height=150)
        video_box.pack(side="left"); video_box.pack_propagate(False)
        tk.Label(video_box, text="(video recording)", font=("Poppins",10),
                 fg=self.MUTED, bg=self.CARD_BG).pack(expand=True)

        info_col = tk.Frame(body, bg=self.PANEL_BG, padx=30); info_col.pack(side="left", fill="both", expand=True)

        rec_date = self.session_date.get() if has_data else "M/D/Y"
        rec_dur  = self._fmt_elapsed() if has_data else "00:00:00"
        rec_file = (f"VOCA_Session_{datetime.date.today()}_01.mp4"
                    if has_data else "(No recording available)")

        for lbl, val in [("Recorded Date:", rec_date),
                         ("Duration:",      rec_dur),
                         ("Video File:",    rec_file)]:
            f = tk.Frame(info_col, bg=self.PANEL_BG); f.pack(anchor="w", pady=(0,12))
            tk.Label(f, text=lbl, font=("Poppins",9,"bold"),
                     fg=self.TEXT_DARK, bg=self.PANEL_BG).pack(anchor="w")
            tk.Label(f, text=val, font=("Poppins",9),
                     fg=self.MUTED, bg=self.PANEL_BG).pack(anchor="w", pady=(2,0))

        btn_col = tk.Frame(body, bg=self.PANEL_BG); btn_col.pack(side="right", padx=(10,0), fill="y")
        tk.Button(btn_col, text="\u25b6  View Recording", font=("Poppins",9,"bold"),
                  bg=self.NAV_ACTIVE, fg=self.WHITE,
                  activebackground="#22C55E", activeforeground=self.WHITE,
                  relief="flat", bd=0, pady=9, padx=14, cursor="hand2",
                  ).pack(fill="x", pady=(0,8))
        tk.Button(btn_col, text="\u2b07  Save Recording", font=("Poppins",9,"bold"),
                  bg=self.CARD_BG, fg=self.TEXT_DARK,
                  activebackground=self.NAV_ACTIVE, activeforeground=self.WHITE,
                  relief="flat", bd=0, pady=9, padx=14, cursor="hand2",
                  highlightthickness=1, highlightbackground="#c0c8d0",
                  ).pack(fill="x")

        tk.Label(sf, text="© 2026 VOCA System · BS Computer Science",
                 font=("Poppins",8), fg=self.MUTED, bg=self.BG).pack(pady=(14,16))

    # --------------------------------------------------------
    # SETTINGS PAGE
    # --------------------------------------------------------
    def _show_settings(self):
        self._clear_content(); self._set_nav("Settings")
        self.page_title_var.set("SETTINGS")
        sf = self._make_scroll_area(self.content_frame)
        tk.Label(sf, text="SYSTEM SETTINGS", font=("Poppins",13,"bold"),
                 fg=self.TEXT_DARK, bg=self.BG).pack(anchor="w", padx=20, pady=(16,8))

        card = tk.Frame(sf, bg=self.PANEL_BG, padx=24, pady=20,
                        highlightbackground="#c0c8d0", highlightthickness=1)
        card.pack(fill="x", padx=20, pady=4)
        tk.Label(card,text="CAMERA SOURCE",font=("Poppins",8,"bold"),fg=self.MUTED,bg=self.PANEL_BG).pack(anchor="w")
        self._cam_src_var = tk.StringVar(value=str(self.CAMERA_SOURCE))
        tk.Entry(card,textvariable=self._cam_src_var,font=("Poppins",11),
                 bg=self.INPUT_BG,fg=self.TEXT_DARK,insertbackground=self.TEXT_DARK,
                 relief="flat",highlightthickness=1,highlightbackground="#c0c8d0",
                 highlightcolor="#8a9ba8").pack(fill="x",ipady=7,pady=(4,4))
        tk.Label(card,text="0 = webcam   1 = USB cam   rtsp://... = IP camera",
                 font=("Poppins",7),fg=self.MUTED,bg=self.PANEL_BG).pack(anchor="w",pady=(0,12))
        def _save():
            val=self._cam_src_var.get().strip()
            try: self.CAMERA_SOURCE=int(val)
            except: self.CAMERA_SOURCE=val
            messagebox.showinfo("Settings",f"Camera source set to: {self.CAMERA_SOURCE}")
        tk.Button(card,text="Save Settings",font=("Poppins",9,"bold"),
                  bg=self.NAV_ACTIVE,fg=self.WHITE,activebackground="#22C55E",
                  activeforeground=self.WHITE,relief="flat",bd=0,pady=8,padx=16,
                  cursor="hand2",command=_save).pack(anchor="w")

        tk.Label(sf, text="© 2026 VOCA System · BS Computer Science",
                 font=("Poppins",8), fg=self.MUTED, bg=self.BG).pack(pady=(8,16))

    # --------------------------------------------------------
    # CAMERA CONTROL
    # --------------------------------------------------------
    def _rebind_scroll(self):
        for w in self.content_frame.winfo_children():
            if isinstance(w, tk.Frame):
                for c in w.winfo_children():
                    if isinstance(c, tk.Canvas):
                        c.bind_all("<MouseWheel>", lambda e, cv=c: cv.yview_scroll(-1*(e.delta//120),"units"))
                        return

    def _show_privacy_notice(self):
        popup = tk.Toplevel(self)
        popup.title("Privacy Notice"); popup.geometry("520x500")
        popup.resizable(False, False); popup.configure(bg=self.PANEL_BG)
        popup.grab_set(); popup.focus_force()
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        popup.geometry(f"520x500+{(sw-520)//2}+{(sh-500)//2}")
        self._privacy_agreed = False
        self.unbind_all("<MouseWheel>")
        def _restore():
            try: self._rebind_scroll()
            except: pass
        popup.protocol("WM_DELETE_WINDOW", lambda: (setattr(self,"_privacy_agreed",False),_restore(),popup.destroy()))
        h = tk.Frame(popup, bg=self.NAV_ACTIVE, pady=16); h.pack(fill="x")
        tk.Label(h,text="Privacy Notice",font=("Poppins",14,"bold"),fg=self.WHITE,bg=self.NAV_ACTIVE).pack()
        tk.Label(h,text="Please read carefully before starting the recording session.",font=("Poppins",8),fg="#e0e8f0",bg=self.NAV_ACTIVE).pack(pady=(4,0))
        tf = tk.Frame(popup,bg=self.CARD_BG,highlightbackground="#c0c8d0",highlightthickness=1)
        tf.pack(fill="x",padx=20,pady=(12,4)); tf.pack_propagate(False); tf.configure(height=260)
        tb = tk.Text(tf,font=("Poppins",9),bg=self.CARD_BG,fg=self.TEXT_DARK,wrap="word",relief="flat",padx=14,pady=14,state="normal",cursor="arrow")
        sb2 = tk.Scrollbar(tf,command=tb.yview); tb.configure(yscrollcommand=sb2.set)
        sb2.pack(side="right",fill="y"); tb.pack(fill="both",expand=True)
        def _scroll(e): tb.yview_scroll(-1*(e.delta//120),"units"); return "break"
        tb.bind("<MouseWheel>",_scroll); popup.bind("<MouseWheel>",_scroll)
        notice = (
            "VOCA - Vision of Classroom Activity\nCity College of Calamba\nDepartment of Computing and Informatics\n\n"
            "DATA PRIVACY NOTICE\n\nIn compliance with Republic Act No. 10173 (Data Privacy Act of 2012), this system collects the following data during a monitoring session:\n\n"
            "  - Live video feed from the classroom camera\n  - Body pose keypoints of the faculty member\n  - Teaching activity classifications and timestamps\n  - Session details (instructor, subject, section, room)\n\n"
            "PURPOSE OF COLLECTION\n\nData is used solely for academic quality assurance monitoring. It is not used for disciplinary action without proper institutional review.\n\n"
            "DATA RETENTION\n\nSession records are stored locally on this device only. No data is transmitted to external servers or third parties.\n\n"
            "RIGHTS OF THE DATA SUBJECT\n\nThe faculty member has the right to:\n  - Be informed of the monitoring session\n  - Access their session records upon request\n  - Request correction of inaccurate records\n\n"
            "CONSENT\n\nBy clicking I Agree and Start Recording, the authorized personnel confirms:\n  1. The faculty member has been informed of this session.\n  2. This recording is for academic purposes only.\n  3. All data will be handled with confidentiality.\n"
        )
        tb.insert("1.0",notice)
        tb.tag_configure("bold",font=("Poppins",9,"bold"),foreground="#2563EB")
        for kw in ["DATA PRIVACY NOTICE","PURPOSE OF COLLECTION","DATA RETENTION","RIGHTS OF THE DATA SUBJECT","CONSENT"]:
            pos="1.0"
            while True:
                p=tb.search(kw,pos,stopindex="end")
                if not p: break
                tb.tag_add("bold",p,f"{p}+{len(kw)}c"); pos=f"{p}+{len(kw)}c"
        tb.config(state="disabled")
        chk_frame = tk.Frame(popup, bg=self.PANEL_BG); chk_frame.pack(fill="x", padx=20, pady=(4,0))
        btn_row   = tk.Frame(popup, bg=self.PANEL_BG); btn_row.pack(fill="x", padx=20, pady=(6,16))
        def _agree(): self._privacy_agreed=True; _restore(); popup.destroy()
        def _cancel(): self._privacy_agreed=False; _restore(); popup.destroy()
        agree_btn = tk.Button(btn_row,text="I Agree and Start Recording",font=("Poppins",10,"bold"),
                              bg="#c0c8d0",fg=self.MUTED,activebackground="#22C55E",activeforeground=self.WHITE,
                              relief="flat",bd=0,pady=10,padx=16,cursor="hand2",state="disabled",command=_agree)
        agree_btn.pack(side="left",fill="x",expand=True,padx=(0,8))
        tk.Button(btn_row,text="Cancel",font=("Poppins",9),bg=self.CARD_BG,fg=self.TEXT_DARK,
                  activebackground=self.ERROR,activeforeground=self.WHITE,
                  relief="flat",bd=0,pady=10,padx=16,cursor="hand2",command=_cancel).pack(side="left")
        agreed_var = tk.BooleanVar(value=False)
        def _toggle(*_):
            if agreed_var.get(): agree_btn.config(state="normal",bg="#22C55E",fg=self.WHITE)
            else: agree_btn.config(state="disabled",bg="#c0c8d0",fg=self.MUTED)
        tk.Checkbutton(chk_frame,text="  I have read and understood the Privacy Notice.",
                       variable=agreed_var,command=_toggle,
                       bg=self.PANEL_BG,fg=self.TEXT_DARK,activebackground=self.PANEL_BG,
                       activeforeground=self.TEXT_DARK,selectcolor="#22C55E",
                       font=("Poppins",10,"bold"),cursor="hand2").pack(anchor="w",pady=(4,6))
        self.wait_window(popup)
        return self._privacy_agreed

    def _start_camera(self):
        if self.camera_on: return
        if not self._show_privacy_notice(): return
        self.camera_on=True; self.elapsed_sec=0
        self.activity_counts={k:0 for k in self.ACT_COLORS}
        self.total_frames=0; self.session_log=[]; self.current_act="Starting..."; self.current_fps=0.0
        h,m=self.duration_limit_h.get(),self.duration_limit_m.get()
        self._limit_sec=h*3600+m*60
        self._live_win=LiveFeedWindow(master=self,on_result=self._on_detection,on_close=self._on_feed_closed,
                                      camera_source=self.CAMERA_SOURCE,act_colors=self.ACT_COLORS,
                                      limit_sec=self._limit_sec,faculty_photo=self.active_faculty_photo,
                                      faculty_name=self.active_faculty_name)
        self._show_dashboard(); self._tick_timer()

    def _stop_camera(self):
        self.camera_on=False
        if self._live_win:
            try: self._live_win._close()
            except: pass
            self._live_win=None
        self._show_dashboard()

    def _raise_feed(self):
        if self._live_win and self._live_win.winfo_exists():
            self._live_win.lift(); self._live_win.focus_force()

    def _on_detection(self, activity, fps, ts, frame_bgr, recordable=True):
        self.current_act=activity; self.current_fps=fps
        if recordable:
            if activity in self.activity_counts:
                self.activity_counts[activity]+=1; self.total_frames+=1
            if not self.session_log or self.session_log[-1][1]!=activity:
                self.session_log.append((ts,activity))
        self._refresh_bars()

    def _refresh_bars(self):
        for act, refs in self._bar_refs.items():
            pct=self._pct_for(act); color=self.ACT_COLORS.get(act,"#2563EB")
            try:
                refs["fill"].place(x=0,y=0,width=max(0,int(220*pct/100)),height=14)
                refs["pct_lbl"].config(text=f"{pct}%",fg=color if pct>0 else self.MUTED)
                refs["name_lbl"].config(fg=self.TEXT_DARK if pct>0 else self.MUTED)
            except: pass

    def _on_feed_closed(self):
        self.camera_on=False; self._live_win=None
        if self.session_log and DB_OK:
            try:
                save_session(session_info=self._get_session_info(),activity_counts=self.activity_counts,total_frames=self.total_frames,session_log=self.session_log)
                print("[DB] Session auto-saved.")
            except Exception as e: print(f"[DB] Auto-save failed: {e}")
        self._show_dashboard()

    def _tick_timer(self):
        if not self.camera_on: return
        self.elapsed_sec+=1
        try: self.timer_lbl.config(text=self._fmt_elapsed())
        except: pass
        if self._limit_sec>0:
            remaining=max(0,self._limit_sec-self.elapsed_sec)
            cd_color=(self.ERROR if remaining<=self._limit_sec*0.10 else
                      self.WARNING if remaining<=self._limit_sec*0.30 else "#22C55E")
            try: self.countdown_lbl.config(text=self._fmt_sec(remaining),fg=cd_color)
            except: pass
            if remaining<=0:
                messagebox.showinfo("Session Complete",f"Recording limit reached: {self.duration_limit_h.get()}h {self.duration_limit_m.get():02d}m\nSession stopped automatically.")
                self.after(0,self._stop_camera); return
        self.after(1000,self._tick_timer)

    # --------------------------------------------------------
    # DB + PDF
    # --------------------------------------------------------
    def _get_session_info(self):
        return {"instructor":self.session_instructor.get(),"subject":self.session_subject.get(),
                "section":self.session_section.get(),"room":self.session_room.get(),
                "date":self.session_date.get(),"semester":self.session_semester.get(),
                "school_year":self.session_school_yr.get(),"duration":self._fmt_elapsed()}

    def _save_to_db(self):
        if not DB_OK: messagebox.showerror("Database","database.py not found."); return
        if not self.session_log: messagebox.showwarning("No Data","No session data to save yet."); return
        try:
            sid=save_session(session_info=self._get_session_info(),activity_counts=self.activity_counts,total_frames=self.total_frames,session_log=self.session_log)
            messagebox.showinfo("Saved",f"Session saved. ID: {sid}")
        except Exception as e: messagebox.showerror("Save Error",str(e))

    def _open_pdf(self, path):
        try:
            if platform.system()=="Windows": os.startfile(path)
            elif platform.system()=="Darwin": __import__("subprocess").Popen(["open",path])
            else: __import__("subprocess").Popen(["xdg-open",path])
        except: pass

    def _export_pdf(self, full=False):
        if not self.session_log: messagebox.showwarning("No Data","No session data to export yet."); return
        name=self.session_instructor.get() or "Report"
        fname=f"VOCA_{'Full' if full else 'Summary'}_{name}_{datetime.date.today()}.pdf"
        path=filedialog.asksaveasfilename(defaultextension=".pdf",filetypes=[("PDF","*.pdf")],initialfile=fname,title="Save PDF")
        if not path: return
        try:
            if full: export_full_pdf(self._get_session_info(),self.activity_counts,self.total_frames,self.session_log,path)
            else: export_summary_pdf(self._get_session_info(),self.activity_counts,self.total_frames,path)
            messagebox.showinfo("Exported",f"PDF saved:\n{path}"); self._open_pdf(path)
        except Exception as e: messagebox.showerror("Export Error",str(e))

    # --------------------------------------------------------
    # UTILITIES
    # --------------------------------------------------------
    def _clear_content(self):
        for w in self.content_frame.winfo_children(): w.destroy()

    def _refresh_clock(self):
        try: self.clock_var.set(datetime.datetime.now().strftime("%A, %d %b %Y  |  %I:%M:%S %p"))
        except: return
        self.after(1000, self._refresh_clock)

    def _logout(self):
        if messagebox.askyesno("Logout","Are you sure you want to logout?"):
            self._stop_camera(); self.destroy(); self.root.deiconify()

    def _on_close(self):
        if messagebox.askyesno("Exit","Close VOCA?"):
            self._stop_camera(); self.root.destroy()

    def _pct_for(self, act):
        if self.total_frames==0: return 0
        return round(self.activity_counts.get(act,0)/self.total_frames*100)

    def _active_pct(self):
        if self.total_frames==0: return 0
        return round(sum(self.activity_counts.get(k,0) for k in ["Writing on Board","Instructional Gesturing"])/self.total_frames*100)

    def _fmt_elapsed(self):
        h=self.elapsed_sec//3600; m=(self.elapsed_sec%3600)//60; s=self.elapsed_sec%60
        return f"{h:02d}:{m:02d}:{s:02d}"

    @staticmethod
    def _fmt_sec(sec):
        sec=max(0,int(sec))
        return f"{sec//3600:02d}:{(sec%3600)//60:02d}:{sec%60:02d}"


if __name__ == "__main__":
    root = tk.Tk(); root.withdraw()
    DashboardApp(root=root, username="Admin").mainloop()