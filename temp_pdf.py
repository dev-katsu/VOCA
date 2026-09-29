import os
import re

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas as pdfcanvas
    from reportlab.lib import colors
    from reportlab.lib.utils import ImageReader
except ImportError:
    pass

def _img(filename):
    path = os.path.join(os.path.dirname(__file__), "web", "img", filename)
    return path if os.path.exists(path) else None

def get_dominant_activity_text(pct_dict):
    if not pct_dict:
        return "No activity data available for this session."
        
    main_acts = ["Writing on Board", "Instructional Gesturing", "Active Roving", "Seated Instruction", "Ambient / Idle"]
    valid_pcts = {k: v for k, v in pct_dict.items() if k in main_acts}
    
    if not valid_pcts:
        return "No standard instructional activities were detected during this session."
        
    max_act = max(valid_pcts.items(), key=lambda x: x[1])
    name, pct = max_act
    
    sorted_pcts = sorted(valid_pcts.values(), reverse=True)
    if len(sorted_pcts) >= 3 and (sorted_pcts[0] - sorted_pcts[2] < 15):
        return f"The session showed a relatively balanced distribution of recognized activities, with Instructional Gesturing ({pct_dict.get('Instructional Gesturing',0)}%), Writing on the Board ({pct_dict.get('Writing on Board',0)}%), Active Roving ({pct_dict.get('Active Roving',0)}%), Seated Instruction ({pct_dict.get('Seated Instruction',0)}%), and Ambient / Idle ({pct_dict.get('Ambient / Idle',0)}%) accounting for similar portions of the monitored session."
        
    if name == "Instructional Gesturing":
        return f"The dominant activity was Instructional Gesturing ({pct}%). This indicates that visible instructional gestures and body movements accounted for the largest portion of the monitored session."
    elif name == "Writing on Board":
        return f"The dominant activity was Writing on the Board ({pct}%). This indicates that board-based activity accounted for the largest portion of the monitored session."
    elif name == "Active Roving":
        return f"The dominant activity was Active Roving ({pct}%). This indicates that the faculty member spent the largest portion of the monitored session moving within the camera’s field of view."
    elif name == "Seated Instruction":
        return f"The dominant activity was Seated Instruction ({pct}%). This indicates that the faculty member spent the largest portion of the monitored session in a seated teaching position."
    elif name == "Ambient / Idle":
        return f"The dominant activity was Ambient / Idle ({pct}%). This indicates that the faculty member was not performing one of the predefined instructional activities for the largest portion of the monitored session."
    
    return f"The dominant activity was {name} ({pct}%)."

def export_summary_pdf(session_info, activity_counts, total_frames, output_path,
                        instructor_photo_path=None, recording_filename=None):
    W, H = letter
    c = pdfcanvas.Canvas(output_path, pagesize=letter)
    
    # Fonts
    c.setFont("Helvetica-Bold", 14)
    
    # 1. Header
    wordmark = _img("voca-wordmark.png")
    logo = _img("voca-logo.png")
    
    if wordmark:
        c.drawImage(ImageReader(wordmark), 200, H - 70, width=170, height=45, preserveAspectRatio=True, mask="auto")
    elif logo:
        c.drawImage(ImageReader(logo), 200, H - 70, width=170, height=45, preserveAspectRatio=True, mask="auto")
        
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.black)
    c.drawString(400, H - 45, "VOCA - VISION OF CLASSROOM ACTIVITY")
    c.setFont("Helvetica", 7)
    c.drawString(400, H - 55, "CONFIDENTIAL ACADEMIC MONITORING RECORD")
    c.drawString(400, H - 65, "FOR ACADEMIC REVIEW AND DOCUMENTATION")
    
    # Thin gray line
    c.setStrokeColorRGB(0.8, 0.8, 0.8)
    c.setLineWidth(1)
    c.line(40, H - 75, W - 40, H - 75)
    
    # TEACHING ACTIVITY SUMMARY REPORTS
    c.setFont("Helvetica-Bold", 12)
    c.setFillColorRGB(0.1, 0.18, 0.28) # Dark blue text
    c.drawCentredString(W / 2, H - 95, "TEACHING ACTIVITY SUMMARY REPORTS")
    
    # 2. SESSION INFORMATION
    y = H - 120
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
    
    acts = ["Writing on Board", "Instructional Gesturing", "Active Roving", "Seated Instruction", "Ambient / Idle"]
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
