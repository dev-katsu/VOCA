"""
VOCA - PDF Export
File: pdf_export.py

The Summary/Full-Log PDF builders from the original Tkinter dashboard.py,
pulled out into their own module so the Eel app (app.py) can use them
without importing tkinter/PIL.

export_summary_pdf() draws the branded "Teaching Activity Summary Report"
layout (title bar, session-detail pills, instructor photo, activity
distribution table, recording line) to match the VOCA mockup pixel-for-
pixel as closely as reportlab allows. export_full_pdf() keeps the plain
tabular log layout used for the Full Log export.
"""

import os
import re

# PDF EXPORT  (pip install reportlab)
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas as pdfcanvas
    from reportlab.lib.utils import ImageReader
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False


# ---------------------------------------------------------------
# Shared palette / helpers for the summary report
# ---------------------------------------------------------------
_PAGE_BG   = None
_CARD_BG   = None
_PILL_BG   = None
_ROW_BG    = None
_INK       = None
_MUTED     = None
_NAVY      = None
_WHITE_A   = None

if REPORTLAB_OK:
    _PAGE_BG = colors.HexColor("#9CA9B2")
    _CARD_BG = colors.HexColor("#A7B2B9")
    _PILL_BG = colors.HexColor("#AEB8BE")
    _ROW_BG  = colors.HexColor("#B3BDC3")
    _INK     = colors.HexColor("#1B2430")
    _MUTED   = colors.HexColor("#E4E8EB")
    _NAVY    = colors.HexColor("#1F3050")


IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "img")


def _img(name):
    """ImageReader for an asset in web/img, or None if it's missing."""
    path = os.path.join(IMG_DIR, name)
    if os.path.exists(path):
        try:
            return ImageReader(path)
        except Exception:
            return None
    return None


def _fit_text(c, text, font, size, max_w):
    text = text or ""
    if c.stringWidth(text, font, size) <= max_w:
        return text
    while text and c.stringWidth(text + "...", font, size) > max_w:
        text = text[:-1]
    return (text + "...") if text else ""


def _field_pill(c, x, y, w, h, label, value, radius=13):
    """A single 'Label:   -- ' rounded field, as in the Session Details column."""
    c.setFillColor(_PILL_BG)
    c.setStrokeColor(colors.Color(1, 1, 1, alpha=0.35))
    c.setLineWidth(0.75)
    c.roundRect(x, y, w, h, radius, fill=1, stroke=1)
    c.setFillColor(_INK)
    c.setFont("Helvetica", 10.5)
    c.drawString(x + 16, y + h / 2 - 4, label)
    value = _fit_text(c, value if value else "--", "Helvetica-Bold", 12, w - 100)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x + 90, y + h / 2 - 4, value)


def get_dominant_activity_text(pct_dict):
    if not pct_dict:
        return "No activity data available for this session."
        
    main_acts = ["Writing on Board", "Instructional Gesturing", "Ambient / Idle"]
    valid_pcts = {k: v for k, v in pct_dict.items() if k in main_acts}
    
    if not valid_pcts:
        return "No standard instructional activities were detected during this session."
        
    max_act = max(valid_pcts.items(), key=lambda x: x[1])
    name, pct = max_act
    
    sorted_pcts = sorted(valid_pcts.values(), reverse=True)
    if len(sorted_pcts) >= 3 and (sorted_pcts[0] - sorted_pcts[2] < 15):
        return f"The session showed a relatively balanced distribution of recognized activities, with Instructional Gesturing ({pct_dict.get('Instructional Gesturing',0)}%), Writing on the Board ({pct_dict.get('Writing on Board',0)}%), and Ambient / Idle ({pct_dict.get('Ambient / Idle',0)}%) accounting for similar portions of the monitored session."
        
    if name == "Instructional Gesturing":
        return f"The dominant activity was Instructional Gesturing ({pct}%). This indicates that visible instructional gestures and body movements accounted for the largest portion of the monitored session."
    elif name == "Writing on Board":
        return f"The dominant activity was Writing on the Board ({pct}%). This indicates that board-based activity accounted for the largest portion of the monitored session."
    elif name == "Ambient / Idle":
        return f"The dominant activity was Ambient / Idle ({pct}%). This indicates that the faculty member was not performing one of the predefined instructional activities for the largest portion of the monitored session."
    
    return f"The dominant activity was {name} ({pct}%)."

def export_summary_pdf(session_info, activity_counts, total_frames, output_path,
                        instructor_photo_path=None, recording_filename=None):
    W, H = letter
    c = pdfcanvas.Canvas(output_path, pagesize=letter)
    
    # Fonts
    c.setFont("Helvetica-Bold", 14)
    
    # 0. Background Template
    bg_template = _img("report_bg.png")
    if bg_template:
        c.drawImage(ImageReader(bg_template), 0, 0, width=W, height=H, mask="auto")
    
    # 2. SESSION INFORMATION
    y = H - 160
    c.setFillColorRGB(0.2, 0.28, 0.38) # Dark blue bar #364862
    c.rect(0, y, W, 20, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y + 6, "SESSION INFORMATION")
    
    y -= 30
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    labels = ["FACULTY:", "SUBJECT:", "SECTION:", "ROOM:", "SEMESTER:", "DATE:", "DURATION:"]
    
    val_fac = session_info.get("instructor", "N/A")
    val_sub = session_info.get("subject", "N/A")
    val_sec = session_info.get("section", "N/A")
    val_roo = session_info.get("room", "N/A")
    val_sem = session_info.get("semester", "N/A")
    val_dat = session_info.get("date", "N/A")
    val_dur = session_info.get("duration", "N/A")
    vals = [val_fac, val_sub, val_sec, val_roo, val_sem, val_dat, val_dur]
    
    for i, lbl in enumerate(labels):
        c.drawString(60, y - i * 22, lbl)
        # Draw underline
        c.setStrokeColorRGB(0.6, 0.6, 0.6)
        c.line(140, y - i * 22 - 2, 450, y - i * 22 - 2)
        # Draw value
        c.setFont("Helvetica", 9)
        c.drawString(145, y - i * 22, vals[i])
        c.setFont("Helvetica-Bold", 9)
        
    # Draw photo box
    photo_size = 100
    px = 460
    py = y - 4 * 22 - 10
    c.setStrokeColorRGB(0.2, 0.28, 0.38)
    c.setLineWidth(2)
    c.roundRect(px, py, photo_size, photo_size, 8, fill=0, stroke=1)
    if instructor_photo_path and os.path.exists(instructor_photo_path):
        try:
            c.drawImage(ImageReader(instructor_photo_path), px+2, py+2, width=photo_size-4, height=photo_size-4, preserveAspectRatio=True)
        except Exception:
            pass
            
    # 3. TEACHING ACTIVITY SUMMARY
    y = y - 6 * 22 - 30
    c.setFillColorRGB(0.2, 0.28, 0.38)
    c.rect(0, y, W, 20, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y + 6, "TEACHING ACTIVITY SUMMARY")
    
    y -= 25
    box_w = (W - 100) / 2
    box_h = 160
    
    # Left box (Activity table)
    c.setStrokeColorRGB(0.6, 0.6, 0.6)
    c.setLineWidth(1.5)
    c.roundRect(40, y - box_h, box_w, box_h, 10, fill=0, stroke=1)
    
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(70, y - 20, "ACTIVITY")
    c.drawString(220, y - 20, "PERCENTAGE")
    
    acts = ["Writing on Board", "Instructional Gesturing", "Ambient / Idle"]
    pct_dict = {}
    for act in acts:
        pct_dict[act] = round(activity_counts.get(act, 0) / total_frames * 100) if total_frames else 0
        
    row_y = y - 45
    for act in acts:
        # Draw pill
        c.setStrokeColorRGB(0.6, 0.6, 0.6)
        c.setLineWidth(1)
        c.roundRect(50, row_y - 12, box_w - 20, 20, 10, fill=0, stroke=1)
        c.setFont("Helvetica", 8)
        c.drawString(65, row_y - 6, act)
        c.drawString(240, row_y - 6, f"-- {pct_dict[act]} %")
        row_y -= 25
        
    # Right box
    c.setStrokeColorRGB(0.6, 0.6, 0.6)
    c.setLineWidth(1.5)
    c.roundRect(40 + box_w + 20, y - box_h, box_w, box_h, 10, fill=0, stroke=1)
    
    # Inner dark gray box
    c.setFillColorRGB(0.4, 0.45, 0.5)
    c.roundRect(40 + box_w + 30, y - 55, box_w - 20, 45, 6, fill=1, stroke=0)
    
    c.setFillColor(colors.white)
    c.setFont("Helvetica", 7)
    # manual text wrap for simplicity
    c.drawString(40 + box_w + 55, y - 25, "This summary provides objective, behavior-")
    c.drawString(40 + box_w + 55, y - 35, "based documentation of classroom activities to")
    c.drawString(40 + box_w + 55, y - 45, "assist academic administrators in faculty monitoring.")
    
    # Exclamation icon
    c.setStrokeColor(colors.white)
    c.circle(40 + box_w + 42, y - 30, 8, stroke=1, fill=0)
    c.drawString(40 + box_w + 41, y - 33, "!")
    
    # Inner text box
    c.setFillColor(colors.white)
    c.setStrokeColorRGB(0.6, 0.6, 0.6)
    c.roundRect(40 + box_w + 30, y - 145, box_w - 20, 85, 6, fill=1, stroke=1)
    
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)
    
    summary_text = get_dominant_activity_text(pct_dict)
    
    try:
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph
        styles = getSampleStyleSheet()
        style = styles["Normal"]
        style.fontSize = 8
        style.leading = 12
        p = Paragraph(summary_text, style)
        p.wrapOn(c, box_w - 40, 80)
        p.drawOn(c, 40 + box_w + 40, y - 135)
    except Exception:
        c.drawString(40 + box_w + 40, y - 90, "Summary data loaded.")
    
    # 4. COMMENTS AND RECOMMENDATIONS
    y = y - box_h - 30
    c.setFillColorRGB(0.2, 0.28, 0.38)
    c.rect(0, y, W, 20, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y + 6, "COMMENTS AND RECOMENDATIONS")
    
    y -= 30
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "Comments / Observation")
    c.drawString(300, y, "Recommendation for Improvement")
    c.setFont("Helvetica", 7)
    c.drawString(40, y - 10, "Enter comments or observation here...")
    c.drawString(300, y - 10, "Enter recommendation here...")
    
    c.setStrokeColorRGB(0.6, 0.6, 0.6)
    for i in range(5):
        c.line(40, y - 30 - i * 15, 260, y - 30 - i * 15)
        c.line(300, y - 30 - i * 15, 520, y - 30 - i * 15)
        
    y -= 120
    c.setFont("Helvetica-Bold", 8)
    c.drawString(40, y, "REVIEWED BY:")
    
    c.line(60, y - 25, 200, y - 25)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(130, y - 35, "Name and Signature")
    c.setFont("Helvetica", 8)
    c.drawCentredString(130, y - 45, "Dean / Program Head / Authorized Personnel")
    
    c.setFont("Helvetica-Bold", 8)
    c.drawString(340, y - 40, "Date Reviewed:")
    c.line(410, y - 40, 520, y - 40)
    
    c.save()

def export_full_pdf(session_info, activity_counts, total_frames, session_log, output_path):
    if not REPORTLAB_OK:
        raise Exception("Run: pip install reportlab")
    styles = getSampleStyleSheet()
    doc    = SimpleDocTemplate(output_path, pagesize=letter,
                               rightMargin=36, leftMargin=36,
                               topMargin=36, bottomMargin=36)
    story  = []

    title_style = ParagraphStyle("T", parent=styles["Heading1"],
                                 fontName="Helvetica-Bold", fontSize=18,
                                 textColor=colors.HexColor("#0F172A"), spaceAfter=12)
    story.append(Paragraph("VOCA - Full Teaching Activity Report", title_style))
    story.append(Spacer(1, 10))

    t = Table(_pdf_meta_table(session_info), colWidths=[80,180,80,180])
    t.setStyle(_pdf_table_style())
    story.append(t)
    story.append(Spacer(1, 15))

    story.append(Paragraph("Complete Activity Log", styles["Heading2"]))
    story.append(Spacer(1, 8))
    rows = [["Timestamp", "Activity", "Instructor"]]
    for ts, act in session_log:
        rows.append([ts, act, session_info.get("instructor","")])
    t2 = Table(rows, colWidths=[140,240,140])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,0), colors.HexColor("#1E293B")),
        ("TEXTCOLOR",  (0,0),(-1,0), colors.white),
        ("FONTNAME",   (0,0),(-1,0), "Helvetica-Bold"),
        ("BOTTOMPADDING",(0,0),(-1,0),6),
        ("GRID",       (0,0),(-1,-1),0.5, colors.HexColor("#CBD5E1")),
        ("FONTNAME",   (0,1),(-1,-1),"Helvetica"),
        ("FONTSIZE",   (0,0),(-1,-1),8),
    ]))
    story.append(t2)
    doc.build(story)