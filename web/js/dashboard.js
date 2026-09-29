
function showToast(msg, isError=false) {
  const container = document.getElementById("toastContainer");
  if (!container) {
    console.error("Toast container not found!");
    return;
  }
  const t = document.createElement("div");
  t.className = "toast" + (isError ? " toast-error" : "");
  t.innerText = msg;
  container.appendChild(t);
  setTimeout(() => {
    t.style.opacity = "0";
    t.style.transform = "translateY(20px)";
    setTimeout(() => t.remove(), 300);
  }, 3000);
}

// ============================================================
// User info carried over from login.html
// ============================================================
try {
  const u = JSON.parse(sessionStorage.getItem("voca_user") || "null");
  if (u && u.fullname) {
    document.getElementById("footerUser").textContent = "User: " + u.fullname;
  }
  if (u && u.role) {
    document.getElementById("footerRole").textContent = u.role;
  }
} catch (e) { /* no session info yet — fine, defaults stay */ }

document.getElementById("logoutBtn").addEventListener("click", async () => {
  stopAllCameras();
  try { await eel.stop_recording()(); } catch (e) {}
  sessionStorage.removeItem("voca_user");
  window.location.href = "login.html";
});

// ============================================================
// Sidebar navigation
// ============================================================
const navBtns   = document.querySelectorAll(".nav-list .nav-btn");
const pages     = document.querySelectorAll(".page");
const pageTitle = document.getElementById("pageTitle");

navBtns.forEach(btn => {
  btn.addEventListener("click", () => {
    stopAllCameras();
    navBtns.forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const target = btn.dataset.page;
    pages.forEach(p => p.hidden = (p.id !== "page-" + target));
    pageTitle.textContent = target === "dashboard"
      ? "MONITORING WORKSPACE"
      : btn.textContent.toUpperCase();

    if (target === "dashboard") refreshDashboard();
    if (target === "faculty") loadFacultyList();
    if (target === "session") loadSessionSetup();
    if (target === "reports") loadReports();
    if (target === "settings") refreshSettingsPage();
  });
});

// ============================================================
// Live clock in the topbar
// ============================================================
function updateClock() {
  const now = new Date();
  const days = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];
  const day = days[now.getDay()];
  const date = now.toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" });
  const time = now.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  document.getElementById("topbarClock").textContent = `${day}, ${date} | ${time}`;
}
updateClock();
setInterval(updateClock, 1000 * 30);

// ============================================================
// Camera helpers (shared by Faculty page and Dashboard card)
// ============================================================
let camStream = null;      // Faculty page camera
let dashCamStream = null;  // Dashboard profile card camera

function stopStream(s) { if (s) s.getTracks().forEach(t => t.stop()); }

function stopAllCameras() {
  stopStream(camStream);     camStream = null;
  stopStream(dashCamStream); dashCamStream = null;
  const v1 = document.getElementById("camVideo");
  const v2 = document.getElementById("dashCamVideo");
  if (v1) { v1.hidden = true; v1.srcObject = null; }
  if (v2) { v2.hidden = true; v2.srcObject = null; }
  const p1 = document.getElementById("photoPreviewImg");
  const p2 = document.getElementById("dashAvatarImg");
  if (p1) p1.hidden = false;
  const cap = document.getElementById("captureBtn");
  if (cap) cap.hidden = true;
}

// ============================================================
// DASHBOARD PAGE
// ============================================================
const cameraStatus  = document.getElementById("cameraStatus");
const statActive    = document.getElementById("statActive");
const statDuration  = document.getElementById("statDuration");
const statLog       = document.getElementById("statLog");
const elapsedText   = document.getElementById("elapsedText");
const remainingText = document.getElementById("remainingText");
const startBtn      = document.getElementById("startBtn");
const dashAvatarImg = document.getElementById("dashAvatarImg");
const dashTakeBtn   = document.getElementById("dashTakeBtn");
const dashUploadBtn = document.getElementById("dashUploadBtn");
const dashUploadInput = document.getElementById("dashUploadInput");

// Same three activities (and colours) the detector / original app use.
const ACTIVITIES = [
  { name: "Writing on Board",        bar: "barWriting",   pct: "pctWriting",   color: "#5aa9ff" },
  { name: "Instructional Gesturing", bar: "barGesturing", pct: "pctGesturing", color: "#4dd0e1" },
  { name: "Active Roving",           bar: "barRoving",    pct: "pctRoving",    color: "#66b5a4" },
  { name: "Seated Instruction",      bar: "barSeated",    pct: "pctSeated",    color: "#5ba0d9" },
  { name: "Ambient / Idle",          bar: "barIdle",      pct: "pctIdle",      color: "#c3cdd6" },
];
ACTIVITIES.forEach(a => { document.getElementById(a.bar).style.background = a.color; });

let dashActiveFaculty = null;
let pollTimer = null;
let feedWin = null;
let lastEndedShown = "";

function loggedInName() {
  try { return (JSON.parse(sessionStorage.getItem("voca_user") || "null") || {}).fullname || ""; }
  catch (e) { return ""; }
}

function fmtTime(sec) {
  sec = Math.max(0, Math.floor(sec));
  const h = String(Math.floor(sec / 3600)).padStart(2, "0");
  const m = String(Math.floor((sec % 3600) / 60)).padStart(2, "0");
  const s = String(sec % 60).padStart(2, "0");
  return `${h}:${m}:${s}`;
}

function limitText(h, m) { return (h || m) ? `${h}h ${String(m).padStart(2, "0")}m` : "Unlimited"; }

function renderStatus(st) {
  const total = st.total || 0;
  const c = st.counts || {};

  ACTIVITIES.forEach(a => {
    const pct = total > 0 ? Math.round(((c[a.name] || 0) / total) * 100) : 0;
    document.getElementById(a.bar).style.width = pct + "%";
    document.getElementById(a.pct).textContent = pct + "%";
  });

  if (st.running) {
    // Active Teaching = (Writing + Gesturing) / all frames, as in the original
    const active = total > 0
      ? Math.round((((c["Writing on Board"] || 0) + (c["Instructional Gesturing"] || 0)) / total) * 100)
      : 0;

    cameraStatus.textContent = st.status
      ? st.status
      : `LIVE  -  ${st.current_activity}  |  FPS: ${Number(st.fps).toFixed(1)}`;
    cameraStatus.classList.add("live");
    startBtn.textContent = "STOP RECORDING";
    startBtn.classList.add("recording");

    statActive.textContent   = active + "%";
    statDuration.textContent = fmtTime(st.elapsed);
    statLog.textContent      = st.log_entries ? String(st.log_entries) : "--";
    elapsedText.textContent  = "Elapsed: " + fmtTime(st.elapsed);

    if (st.limit_sec > 0) {
      const rem = st.remaining ?? 0;
      remainingText.textContent = `Remaining: ${fmtTime(rem)} / ${fmtTime(st.limit_sec)} limit`;
      remainingText.className = "remaining " +
        (rem <= st.limit_sec * 0.10 ? "low" : rem <= st.limit_sec * 0.30 ? "warn" : "ok");
    } else {
      remainingText.textContent = "";
    }
  } else {
    cameraStatus.textContent = "Camera not started - Press Start Recording Below";
    cameraStatus.classList.remove("live");
    startBtn.textContent = "START RECORDING (opens live feed window)";
    startBtn.classList.remove("recording");
    remainingText.textContent = "";

    if (st.last_elapsed) {
      // Session just ended: keep the final numbers on screen
      const active = total > 0
        ? Math.round((((c["Writing on Board"] || 0) + (c["Instructional Gesturing"] || 0)) / total) * 100)
        : 0;
      statActive.textContent   = active + "%";
      statDuration.textContent = fmtTime(st.last_elapsed);
      statLog.textContent      = st.log_entries ? String(st.log_entries) : "--";
      elapsedText.textContent  = "Elapsed: " + fmtTime(st.last_elapsed);
    } else {
      statActive.textContent = "--";
      statDuration.textContent = "--";
      statLog.textContent = "--";
      elapsedText.textContent = "Elapsed: --";
    }

    // One-time messages when a session ends
    const endKey = st.ended_reason + ":" + st.last_elapsed;
    if (st.ended_reason && endKey !== lastEndedShown) {
      lastEndedShown = endKey;
      if (st.ended_reason === "limit") {
        cameraStatus.textContent = "Session Complete - recording limit reached, session stopped automatically.";
      } else if (st.ended_reason === "error") {
        cameraStatus.textContent = "Camera Error: " + (st.error || "unknown error");
      } else if (st.saved_id) {
        cameraStatus.textContent = "Session saved (ID " + st.saved_id + ").";
      }
    }
  }
}

async function pollStatus() {
  try {
    const st = await eel.get_recording_status()();
    renderStatus(st);
    if (!st.running && pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  } catch (e) { console.error(e); }
}

function startPolling() {
  if (!pollTimer) pollTimer = setInterval(pollStatus, 500);
}

async function refreshDashboard() {
  try {
    const info = await eel.get_session_setup()(); dashActiveFaculty = await eel.get_active_faculty()();
    const instructor = (dashActiveFaculty && dashActiveFaculty.name) ? dashActiveFaculty.name : (info.instructor || loggedInName());
    document.getElementById("infoSubject").textContent    = info.subject    || "--";
    document.getElementById("infoSection").textContent    = info.section || "--";
    document.getElementById("infoInstructor").textContent = instructor      || "--";
    document.getElementById("infoRoom").textContent       = info.room       || "--";
    document.getElementById("infoDate").textContent       = info.date       || "--";
    
    if (document.getElementById("infoSchoolYear")) document.getElementById("infoSchoolYear").textContent = info.school_year || "--";
    
  if (document.getElementById("infoTerm")) {
    const dates = await eel.get_term_dates()();
    let currentSem = "1st Semester"; // default
    const pickedDate = document.getElementById("setDate") ? document.getElementById("setDate").value : "";
    const compareDate = pickedDate || new Date().toISOString().split("T")[0];
    if (dates.date_sem2 && compareDate >= dates.date_sem2) {
      currentSem = "2nd Semester";
    }
    document.getElementById("infoTerm").textContent = currentSem;
    if (document.getElementById("repTerm")) document.getElementById("repTerm").textContent = currentSem;
  }

    document.getElementById("infoLimit").textContent      = limitText(info.limit_h, info.limit_m);
    if (info.save_video !== undefined) document.getElementById("setSaveVideo").checked = info.save_video;

    dashActiveFaculty = await eel.get_active_faculty()();
    // Profile picture stays blank until a photo exists
    if (dashActiveFaculty && dashActiveFaculty.photo) {
      dashAvatarImg.src = dashActiveFaculty.photo;
      dashAvatarImg.hidden = false;
    } else {
      dashAvatarImg.src = "img/pfp_icon.png";
      dashAvatarImg.hidden = false;
    }

    const st = await eel.get_recording_status()();
    renderStatus(st);
    if (st.running) startPolling();
  } catch (e) { console.error(e); }
}

// ---- Privacy notice (must be accepted before every recording) ----
const privacyModal  = document.getElementById("privacyModal");
const privacyCheck  = document.getElementById("privacyCheck");
const privacyAgree  = document.getElementById("privacyAgree");
const privacyCancel = document.getElementById("privacyCancel");

function askPrivacy() {
  return new Promise(resolve => {
    privacyCheck.checked = false;
    privacyAgree.disabled = true;
    document.getElementById("privacyBody").scrollTop = 0;
    privacyModal.hidden = false;

    const done = (val) => {
      privacyModal.hidden = true;
      privacyAgree.onclick = privacyCancel.onclick = null;
      resolve(val);
    };
    privacyCheck.onchange = () => { privacyAgree.disabled = !privacyCheck.checked; };
    // Open the live-feed window right inside the click so the browser allows the popup
    privacyAgree.onclick = () => {
      feedWin = window.open("livefeed.html", "voca_feed", "width=820,height=600");
      done(true);
    };
    privacyCancel.onclick = () => done(false);
  });
}

// ---- Start / Stop recording ----
document.getElementById("setSaveVideo").addEventListener("change", (e) => {
  eel.set_session_setup({ save_video: e.target.checked });
});

startBtn.addEventListener("click", async () => {
  startBtn.disabled = true;
  try {
    const st = await eel.get_recording_status()();

    if (st.running) {
      await eel.stop_recording()();
      await pollStatus();
    } else {
      if (!(await askPrivacy())) { startBtn.disabled = false; return; }
      lastEndedShown = "";
      const res = await eel.start_recording()();
      if (!res.ok) {
        if (feedWin && !feedWin.closed) feedWin.close();
        cameraStatus.textContent = res.msg || "Could not start recording.";
        cameraStatus.classList.remove("live");
      } else {
        await pollStatus();
        startPolling();
      }
    }
  } catch (e) {
    cameraStatus.textContent = "Could not reach the application backend.";
    console.error(e);
  }
  startBtn.disabled = false;
});

// ---- Profile card: save photo for the Active faculty ----
async function saveDashPhoto(dataUri) {
  if (!dashActiveFaculty) {
    cameraStatus.textContent = "Set an Active faculty on the Faculty page first.";
    return;
  }
  const res = await eel.save_faculty_photo(dashActiveFaculty.name, dataUri)();
  showToast(res.msg, !res.ok);
  if (res.ok) refreshDashboard();
}

dashUploadBtn.addEventListener("click", () => dashUploadInput.click());
dashUploadInput.addEventListener("change", () => {
  const file = dashUploadInput.files[0];
  if (!file) return;
  stopAllCameras();
  const reader = new FileReader();
  reader.onload = () => saveDashPhoto(reader.result);
  reader.readAsDataURL(file);
  dashUploadInput.value = "";
});

// ---- Take a Photo: camera window -> Capture -> Save (for the Active faculty) ----
const photoModal   = document.getElementById("photoModal");
const photoVideo   = document.getElementById("photoVideo");
const photoStill   = document.getElementById("photoStill");
const photoMsg     = document.getElementById("photoMsg");
const photoSub     = document.getElementById("photoSub");
const photoCapture = document.getElementById("photoCapture");
const photoSave    = document.getElementById("photoSave");
const photoRetake  = document.getElementById("photoRetake");
const photoCancel  = document.getElementById("photoCancel");
let photoData = null;

function photoShowLive() {
  photoData = null;
  photoStill.hidden = true;  photoVideo.hidden = false;
  photoCapture.hidden = false; photoSave.hidden = true; photoRetake.hidden = true;
  photoSub.textContent = "Face the camera, then press Capture.";
}

function closePhotoModal() {
  stopStream(dashCamStream); dashCamStream = null;
  photoVideo.srcObject = null;
  photoModal.hidden = true;
}

dashTakeBtn.addEventListener("click", async () => {
  photoMsg.textContent = "";
  photoShowLive();
  photoModal.hidden = false;

  // The photo is saved to the Active faculty member, so make sure one is set
  try { dashActiveFaculty = await eel.get_active_faculty()(); } catch (e) {}
  if (!dashActiveFaculty) {
    photoMsg.textContent = "Set an Active faculty on the Faculty page first.";
    photoCapture.disabled = true;
    return;
  }
  photoCapture.disabled = false;
  photoSub.textContent = `Photo for ${dashActiveFaculty.name}. Face the camera, then press Capture.`;

  try {
    dashCamStream = await navigator.mediaDevices.getUserMedia({ video: true });
    photoVideo.srcObject = dashCamStream;
  } catch (err) {
    photoMsg.textContent = "Could not access the camera. Check the camera permission and that no other app is using it.";
    photoCapture.disabled = true;
  }
});

photoCapture.addEventListener("click", () => {
  if (!photoVideo.videoWidth) { photoMsg.textContent = "Camera is still starting - try again."; return; }
  const c = document.getElementById("camCanvas");
  c.width  = photoVideo.videoWidth;
  c.height = photoVideo.videoHeight;
  c.getContext("2d").drawImage(photoVideo, 0, 0);
  photoData = c.toDataURL("image/jpeg", 0.9);

  photoStill.src = photoData;
  photoStill.hidden = false; photoVideo.hidden = true;
  photoCapture.hidden = true; photoSave.hidden = false; photoRetake.hidden = false;
  photoSub.textContent = "Happy with it? Save the photo or retake.";
  photoMsg.textContent = "";
});

photoRetake.addEventListener("click", photoShowLive);
photoCancel.addEventListener("click", closePhotoModal);

photoSave.addEventListener("click", async () => {
  if (!photoData || !dashActiveFaculty) return;
  photoSave.disabled = true;
  const res = await eel.save_faculty_photo(dashActiveFaculty.name, photoData)();
  photoSave.disabled = false;
  if (res.ok) {
    closePhotoModal();
    cameraStatus.textContent = res.msg;
    refreshDashboard();
  } else {
    photoMsg.textContent = res.msg || "Could not save the photo.";
  }
});

// ============================================================
// SESSION SETUP PAGE
// ============================================================
const setEls = {
  course: document.getElementById("setCourse"),
  year: document.getElementById("setYear"),
  section: document.getElementById("setSection"),
    semester: document.getElementById("setSemester"),
  subject: document.getElementById("setSubject"),
  instructor: document.getElementById("setInstructor"),
  room: document.getElementById("setRoom"),
  date: document.getElementById("setDate"),
  school_year: document.getElementById("setSchoolYear"),
};

const SUBJECTS_MAP = {
  "BSCS": {
    "1st Year": {
      "1st Semester": [
        "IT 101: Introduction to Computing with Laboratory",
        "CS 101: Fundamentals of Programming with Laboratory",
        "MATH 101: Mathematics in the Modern World",
        "US 101: Understanding the Self",
        "IE 101: Interactive English",
        "SEC 101: Security Awareness",
        "ALG 101: Linear Algebra",
        "PATHFit 1: Movements Competency Training",
        "NSTP 101: National Service Training Program 1"
      ],
      "2nd Semester": [
        "CS 102: Object Oriented Programming",
        "IT 102: Information Management",
        "IT 201: Data Structures and Algorithms with Laboratory",
        "NC 102: Networks and Communication",
        "NUM 102: Number Theory",
        "PCOM 102: Purposive Communication",
        "CALC 102: Mechanics",
        "PATHFit 2: Exercise-Based Fitness Activities",
        "NSTP 102: National Service Training Program 2"
      ]
    },
    "2nd Year": {
      "1st Semester": [
        "DIS 201: Discrete Mathematics",
        "ENV 201: Environmental Science",
        "RPH 201: Readings in Philippine History",
        "CS 201: Database Management System",
        "CS 211: Web Design and Programming",
        "CS 221: Programming Language",
        "CS 231: Advanced Object-Oriented Programming",
        "ACCTG 201: Accounting",
        "PATHFit 3: Choice of Dance, Sports, Martial Arts, Group Exercise, Outdoor, and Adventure Activities"
      ],
      "2nd Semester": [
        "CS 202: Design and Analysis of Algorithms",
        "CS 212: Modeling and Simulation",
        "CS 333: Application Development & Emerging Technologies",
        "CS 222: Theory of Automata & Formal Language",
        "CS 232: Software Engineering 1",
        "CS 242: Operating System",
        "CS 252: Web Systems and Technologies",
        "CS 262: Fundamentals of Data Science",
        "PATHFit 4: Choice of Dance, Sports, Martial Arts, Group Exercise, Outdoor, and Adventure Activities"
      ]
    },
    "3rd Year": {
      "1st Semester": [
        "HCI 301: Human Computer Interaction",
        "CS 301: Computer Organization & Assembly Language",
        "SQ 301: Software Quality Assurance",
        "CS 311: Software Engineering 2",
        "CS 321: Visual Programming",
        "CEEL 301: Graphics Design",
        "CEEL 311: Mobile Application Development",
        "RIZAL 301: The Life and Works of Rizal"
      ],
      "2nd Semester": [
        "CEEL 302: Introduction to Cyber Security",
        "Ethics 302: Professional Ethics",
        "TECH 302: Technopreneurship",
        "CS 302: Thesis 1",
        "GCE 302: Glocal Citizenship Education"
      ]
    }
  },
  "BSIT": {
    "1st Year": {
      "1st Semester": [
        "IT 101: Introduction to Computing with Laboratory",
        "CS 101: Fundamentals of Programming with Laboratory",
        "MATH 101: Mathematics in the Modern World",
        "US 101: Understanding the Self",
        "IE 101: Interactive English",
        "SEC 101: Security Awareness",
        "ALG 101: Linear Algebra",
        "PE 101: Physical Fitness, Gymnastics and Aerobics",
        "NSTP 101: National Service Training Program 1"
      ],
      "2nd Semester": [
        "CS 102: Object Oriented Programming",
        "IT 102: Information Management",
        "NET 102: Computer Programming 1 with Laboratory",
        "IT 202: Data Structures and Algorithms with Laboratory",
        "PCOM 102: Purposive Communication",
        "IT 231: Operating System",
        "CALC 102: Mechanics",
        "PE 102: Rhythm Activities",
        "NSTP 102: National Service Training Program 2"
      ]
    },
    "2nd Year": {
      "1st Semester": [
        "DIS 201: Discrete Mathematics",
        "IT 211: Database Management System",
        "RPH 201: Readings in Philippine History",
        "ENV 201: Environmental Science",
        "IT 221: Web Design and Programming",
        "NET 201: Computer Networking 2",
        "RIZAL 201: The Life and Works of Rizal",
        "ACCTG 201: Accounting",
        "PE 201: Individual/Dual Sports"
      ],
      "2nd Semester": [
        "IAS 202: Information Assurance and Security",
        "SAM 202: System Administration and Maintenance",
        "CS 333: Application Development & Emerging Technologies",
        "LDS 202: Logic Design and Switching",
        "CS 232: Software Engineering 1",
        "NET 202: Computer Networking 3",
        "HCI 302: Human Computer Interaction",
        "PE 202: Team Sports"
      ]
    },
    "3rd Year": {
      "1st Semester": [
        "IAS 301: Advanced Information Assurance & Security",
        "SIA 301: System Integration & Architectural with Laboratory",
        "IT 301: Software Engineering 2",
        "NET 301: Computer Networking 4",
        "CEEL 301: Graphics Design",
        "SQA 302: Software Quality Assurance",
        "ETHICS 301: Professional Ethics",
        "TECH 301: Technopreneurship"
      ],
      "2nd Semester": [
        "CEEL 311: Internet of Things",
        "CEEL 302: Multimedia",
        "CEEL 312: Cloud Computing",
        "CAP 302: Capstone Project 1"
      ]
    }
  }
};

function updateSectionDropdown() {
  const c = setEls.course.value;
  const y = setEls.year.value;
  const currentSec = setEls.section.value;
  setEls.section.innerHTML = "<option value='></option>";
  
  if (c && y) {
    let courseCode = "";
    if (c === "BSCS") courseCode = "CS";
    else if (c === "BSIT") courseCode = "IT";
    else courseCode = c; // Fallback
    
    let yearNum = "1";
    if (y === "1st Year") yearNum = "1";
    else if (y === "2nd Year") yearNum = "2";
    else if (y === "3rd Year") yearNum = "3";
    let maxSec = (c === "BSIT") ? 12 : 5;
      for (let i = 1; i <= maxSec; i++) {
      const opt = document.createElement("option");
      const val = `${yearNum}${courseCode}-${i}`;
      opt.value = val;
      opt.textContent = val;
      setEls.section.appendChild(opt);
    }
  }
  setEls.section.value = currentSec;
}
setEls.course.addEventListener("change", updateSectionDropdown);
setEls.year.addEventListener("change", updateSectionDropdown);

function updateSubjectDropdown() {
  const c = setEls.course.value;
  const y = setEls.year.value;
  const s = setEls.semester ? setEls.semester.value : "1st Semester";
  const currentSubj = setEls.subject.value;
  setEls.subject.innerHTML = '<option value=""></option>';
  
  const courseData = SUBJECTS_MAP[c];
  if (courseData && courseData[y] && courseData[y][s]) {
    courseData[y][s].forEach(subj => {
      const opt = document.createElement("option");
      opt.value = subj;
      opt.textContent = subj;
      setEls.subject.appendChild(opt);
    });
  }
  // Try to restore previous selection if it still exists
  setEls.subject.value = currentSubj;
}
setEls.year.addEventListener("change", updateSubjectDropdown);
setEls.course.addEventListener("change", updateSubjectDropdown);
if (setEls.semester) setEls.semester.addEventListener("change", updateSubjectDropdown);


const setLimitH = document.getElementById("setLimitH");
const setLimitM = document.getElementById("setLimitM");
const limitPreview = document.getElementById("limitPreview");
const setupMsg = document.getElementById("setupMsg");

function updateLimitPreview() {
  const h = parseInt(setLimitH.value) || 0, m = parseInt(setLimitM.value) || 0;
  limitPreview.textContent = limitText(h, m) + ((h || m) ? " limit" : "");
}
setLimitH.addEventListener("input", updateLimitPreview);
setLimitM.addEventListener("input", updateLimitPreview);

// ---- Hours / Minutes stepper buttons ----
const STEP_BOUNDS = { setLimitH: [0, 8], setLimitM: [0, 59] };
document.querySelectorAll(".ss-step-up, .ss-step-down").forEach(btn => {
  btn.addEventListener("click", () => {
    const input = document.getElementById(btn.dataset.target);
    const [lo, hi] = STEP_BOUNDS[btn.dataset.target] || [0, 99];
    const dir = btn.classList.contains("ss-step-up") ? 1 : -1;
    let val = (parseInt(input.value) || 0) + dir;
    val = Math.max(lo, Math.min(hi, val));
    input.value = val;
    input.dispatchEvent(new Event("input"));
  });
});

function isoFromDisplay(str) {   // "September 19, 2026" -> "2026-09-19"
  const d = new Date(str);
  if (isNaN(d)) return "";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function displayFromIso(iso) {   // "2026-09-19" -> "September 19, 2026"
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
}

async function loadSessionSetup() {
  const today = new Date().toISOString().split("T")[0];
  if (setEls.date && !setEls.date.dataset.semListener) {
    setEls.date.dataset.semListener = "true";
    setEls.date.addEventListener("change", refreshDashboard);
  }
  if (setEls.date && !setEls.date.dataset.semListener) {
    setEls.date.dataset.semListener = "true";
    setEls.date.addEventListener("change", refreshDashboard);
  }
  if (document.getElementById("setDate")) document.getElementById("setDate").setAttribute("min", today);
  if (document.getElementById("date-sem1")) document.getElementById("date-sem1").setAttribute("min", today);
  if (document.getElementById("date-sem2")) document.getElementById("date-sem2").setAttribute("min", today);
  setupMsg.textContent = "";
  const info = await eel.get_session_setup()(); dashActiveFaculty = await eel.get_active_faculty()();
  Object.entries(setEls).forEach(([key, el]) => {
    if (key === "date") el.value = isoFromDisplay(info.date);
    else if (key === "instructor") el.value = (dashActiveFaculty && dashActiveFaculty.name) ? dashActiveFaculty.name : (info.instructor || loggedInName());
    else el.value = info[key] || "";
  });
  setLimitH.value = info.limit_h || 0; if (document.getElementById("setSaveVideo")) document.getElementById("setSaveVideo").checked = info.save_video || false;
  setLimitM.value = info.limit_m || 0;
  updateLimitPreview(); updateSectionDropdown(); setEls.section.value = info.section || ""; updateSubjectDropdown(); setEls.subject.value = info.subject || "";
}

document.getElementById("saveSetupBtn").addEventListener("click", async () => {
  const payload = {
    course: setEls.course.value, year: setEls.year.value, section: setEls.section.value, subject: setEls.subject.value,
    instructor: setEls.instructor.value, room: setEls.room.value,
    date: displayFromIso(setEls.date.value),
    school_year: setEls.school_year.value,
    semester: setEls.semester ? setEls.semester.value : "1st Semester",
      limit_h: parseInt(setLimitH.value) || 0, limit_m: parseInt(setLimitM.value) || 0, save_video: document.getElementById("setSaveVideo") ? document.getElementById("setSaveVideo").checked : false,
  };
  try {
    await eel.set_session_setup(payload)();
    showToast("Session setup saved successfully!");
  } catch (e) {
    showToast("Could not save session setup.", true);
  }
});

// ============================================================
// FACULTY PAGE
// ============================================================
const facultyNameInput = document.getElementById("facultyNameInput");
const photoPreviewImg  = document.getElementById("photoPreviewImg");
const camVideo         = document.getElementById("camVideo");
const camCanvas        = document.getElementById("camCanvas");
const takePhotoBtn     = document.getElementById("takePhotoBtn");
const captureBtn       = document.getElementById("captureBtn");
const uploadPhotoBtn   = document.getElementById("uploadPhotoBtn");
const uploadPhotoInput = document.getElementById("uploadPhotoInput");
const saveFacultyBtn   = document.getElementById("saveFacultyBtn");
const facultyFormMsg   = document.getElementById("facultyFormMsg");
const facultyListEl    = document.getElementById("facultyList");
const facultyEmptyNote = document.getElementById("facultyEmptyNote");
const activeFacultyImg = document.getElementById("activeFacultyImg");
const activeFacultyName= document.getElementById("activeFacultyName");

let capturedPhoto = null;   // data: URI of whatever photo is staged to save

// ---- Take a Photo (webcam) ----
takePhotoBtn.addEventListener("click", async () => {
  try {
    camStream = await navigator.mediaDevices.getUserMedia({ video: true });
    camVideo.srcObject = camStream;
    camVideo.hidden = false;
    photoPreviewImg.hidden = true;
    captureBtn.hidden = false;
  } catch (err) {
    facultyFormMsg.textContent = "Could not access the camera.";
    facultyFormMsg.className = "form-msg";
  }
});

captureBtn.addEventListener("click", () => {
  camCanvas.width  = camVideo.videoWidth;
  camCanvas.height = camVideo.videoHeight;
  camCanvas.getContext("2d").drawImage(camVideo, 0, 0);
  capturedPhoto = camCanvas.toDataURL("image/jpeg", 0.9);

  photoPreviewImg.src = capturedPhoto;
  photoPreviewImg.hidden = false;
  photoPreviewImg.classList.add("has-photo");
  camVideo.hidden = true;
  captureBtn.hidden = true;

  stopStream(camStream);
  camStream = null;
});

// ---- Upload Photo ----
uploadPhotoBtn.addEventListener("click", () => uploadPhotoInput.click());

uploadPhotoInput.addEventListener("change", () => {
  const file = uploadPhotoInput.files[0];
  if (!file) return;
  stopAllCameras();
  const reader = new FileReader();
  reader.onload = () => {
    capturedPhoto = reader.result;
    photoPreviewImg.src = capturedPhoto;
    photoPreviewImg.hidden = false;
    photoPreviewImg.classList.add("has-photo");
  };
  reader.readAsDataURL(file);
});

// ---- Save Faculty ----
saveFacultyBtn.addEventListener("click", async () => {
  const name = facultyNameInput.value.trim();
  facultyFormMsg.className = "form-msg";

  if (!name) {
    showToast("Please enter a faculty name.", true);
    return;
  }
  if (!capturedPhoto) {
    showToast("Please take or upload a photo first.", true);
    return;
  }

  saveFacultyBtn.disabled = true;
  const result = await eel.save_faculty_photo(name, capturedPhoto)();
  saveFacultyBtn.disabled = false;

  showToast(result.msg, !result.ok);
  if (result.ok) {
    facultyNameInput.value = "";
    capturedPhoto = null;
    photoPreviewImg.src = "img/pfp_icon.png";
    photoPreviewImg.classList.remove("has-photo");
    loadFacultyList();
  }
});

// ---- Faculty list (names set with textContent — no HTML injection) ----
async function loadFacultyList() {
  const list = await eel.get_faculty_list()();

  facultyListEl.innerHTML = "";
  if (!list || list.length === 0) {
    facultyEmptyNote.hidden = false;
    facultyListEl.appendChild(facultyEmptyNote);
  } else {
    facultyEmptyNote.hidden = true;
  }

  let active = null;

  (list || []).forEach(f => {
    if (f.active) active = f;

    const row = document.createElement("div");
    row.className = "faculty-row";

    const thumb = document.createElement("div");
    thumb.className = "faculty-thumb";
    const img = document.createElement("img");
    img.alt = "";
    img.src = f.photo || "img/pfp_icon.png";
    thumb.appendChild(img);

    const info = document.createElement("div");
    info.className = "faculty-info";
    const nameEl = document.createElement("div");
    nameEl.className = "faculty-name";
    nameEl.textContent = f.name;
    const statusEl = document.createElement("div");
    statusEl.className = f.active ? "faculty-status-active" : "faculty-status-inactive";
    statusEl.textContent = f.active ? "ACTIVE - Camera will only detect this person" : "Not active";
    info.append(nameEl, statusEl);

    row.append(thumb, info);

    if (!f.active) {
      const setBtn = document.createElement("button");
      setBtn.className = "set-active-btn";
      setBtn.textContent = "SET ACTIVE";
      setBtn.addEventListener("click", async () => {
        await eel.set_active_faculty(f.id)();
        loadFacultyList();
      });
      row.appendChild(setBtn);
    }

    const delBtn = document.createElement("button");
    delBtn.className = "delete-btn";
    delBtn.textContent = "DELETE";
    delBtn.addEventListener("click", async () => {
      if (!confirm(`Delete faculty "${f.name}"?`)) return;
      await eel.delete_faculty_entry(f.id)();
      loadFacultyList();
    });
    row.appendChild(delBtn);

    facultyListEl.appendChild(row);
  });

  if (active) {
    activeFacultyName.textContent = active.name;
    activeFacultyImg.src = active.photo || "img/pfp_icon_white.png";
  } else {
    activeFacultyName.textContent = "(None)";
    activeFacultyImg.src = "img/pfp_icon_white.png";
  }
}

// ============================================================
// REPORTS PAGE
// ============================================================
const reportsMsg     = document.getElementById("reportsMsg");
const saveToDbBtn    = document.getElementById("saveToDbBtn");
const exportSummaryBtn = document.getElementById("exportSummaryBtn");
const exportFullBtn  = document.getElementById("exportFullBtn");

const REPORT_ROWS = {
  "Writing on Board":        "repPctWriting",
  "Instructional Gesturing": "repPctGesturing",
  "Active Roving":           "repPctRoving",
  "Seated Instruction":      "repPctSeated",
  "Ambient / Idle":          "repPctIdle",
};

async function loadReports() {
  reportsMsg.textContent = "";
  try {
    const rep = await eel.get_latest_report()();
    const info = (rep && rep.ok) ? rep.session_info : {};

    document.getElementById("repSubject").textContent    = info.subject    || "--";
    document.getElementById("repSection").textContent    = info.section || "--";
    document.getElementById("repInstructor").textContent = info.instructor || "--";
    document.getElementById("repRoom").textContent       = info.room       || "--";
    document.getElementById("repDate").textContent       = info.date       || "--";
    document.getElementById("repTerm").textContent   = `${info.semester || ""} ${info.school_year || ""}`.trim() || "--";
    document.getElementById("repDuration").textContent   = info.duration   || "--";
      if (document.getElementById("recDate")) document.getElementById("recDate").textContent = info.date || "--";
      if (document.getElementById("recDuration")) document.getElementById("recDuration").textContent = info.duration || "--";
    
    // Video logic
    const recFileSpan = document.getElementById("recFile");
    const vidBox = document.querySelector(".recording-video-box");
    if (recFileSpan) {
        if (info.video_file) {
            recFileSpan.innerHTML = `Saved <button class="btn btn-primary" onclick="eel.open_video('${info.video_file.split(String.fromCharCode(92)).join('/')}')()" style="margin-left: 10px; padding: 2px 8px; font-size: 0.8rem;">Play</button><br><span style="font-size:0.75rem; color:#888;">${info.video_file}</span>`;
            if (vidBox) {
                eel.get_video_thumbnail(info.video_file)().then(b64 => {
                    if (b64) {
                        vidBox.innerHTML = `<img src="${b64}" style="width:100%; height:100%; object-fit:cover; border-radius: 4px; cursor: pointer;" onclick="eel.open_video('${info.video_file.split(String.fromCharCode(92)).join('/')}')()">`;
                    } else {
                        vidBox.innerHTML = `<span>(Video saved, no preview)</span>`;
                    }
                });
            }
        } else {
            recFileSpan.textContent = "(No recording available)";
            if (vidBox) {
                vidBox.innerHTML = `<span>(No recording available)</span>`;
            }
        }
    }

    const summaryContainer = document.getElementById("summaryRowsContainer");
    summaryContainer.innerHTML = "";
    if (rep && rep.ok && rep.summary) {
        rep.summary.forEach(s => {
            if (s.pct > 0) {  // Only show activities that occurred
                const row = document.createElement("div");
                row.className = "summary-row";
                row.innerHTML = `<span class="summary-label">${s.activity}</span><span class="summary-value">${s.pct} %</span>`;
                summaryContainer.appendChild(row);
            }
        });
        if (summaryContainer.children.length === 0) {
            summaryContainer.innerHTML = "<div class='summary-row'>No activity recorded</div>";
        }
    }
  } catch (e) { console.error(e); }
}

async function runReportAction(btn, fn, busyText) {
  reportsMsg.className = "form-msg";
  reportsMsg.textContent = busyText;
  btn.disabled = true;
  try {
    const res = await fn();
    reportsMsg.textContent = res.msg || (res.ok ? "Done." : "Something went wrong.");
    reportsMsg.className = "form-msg" + (res.ok ? " success" : "");
    if (res.ok) loadReports();
  } catch (e) {
    reportsMsg.textContent = "Could not reach the application backend.";
    console.error(e);
  }
  btn.disabled = false;
}

if(saveToDbBtn) saveToDbBtn.addEventListener("click", () =>
  runReportAction(saveToDbBtn, () => eel.save_report_to_database()(), "Saving..."));

exportSummaryBtn.addEventListener("click", () =>
  runReportAction(exportSummaryBtn, () => eel.export_summary_report_pdf()(), "Exporting..."));

if(exportFullBtn) exportFullBtn.addEventListener("click", () =>
  runReportAction(exportFullBtn, () => eel.export_full_report_pdf()(), "Exporting..."));

// ============================================================
// SETTINGS PAGE
// ============================================================
const camSourceInput = document.getElementById("camSourceInput");
const saveCamBtn = document.getElementById("saveCamBtn");

async function refreshSettingsPage() {
  if (!camSourceInput) return;
  const current = await eel.get_camera_source()();
  camSourceInput.checked = (current == "1");
  document.getElementById("camLabelText").textContent = camSourceInput.checked ? "USB Webcam (On)" : "Built-in Camera (Off)";
  
  camSourceInput.addEventListener("change", () => {
    document.getElementById("camLabelText").textContent = camSourceInput.checked ? "USB Webcam (On)" : "Built-in Camera (Off)";
  });
}

if (saveCamBtn) {
  saveCamBtn.addEventListener("click", async () => {
    const val = camSourceInput.checked ? '1' : '0';
    await eel.set_camera_source(val)();
    saveCamBtn.textContent = "Saved!";
    setTimeout(() => saveCamBtn.textContent = "Save Settings", 2000);
  });
}

// ============================================================
// TERM SETUP PAGE
// ============================================================
async function loadTermSetup() {
  const today = new Date().toISOString().split("T")[0];
  if (document.getElementById("setDate")) document.getElementById("setDate").setAttribute("min", today);
  if (document.getElementById("date-sem1")) document.getElementById("date-sem1").setAttribute("min", today);
  if (document.getElementById("date-sem2")) document.getElementById("date-sem2").setAttribute("min", today);
  const dates = await eel.get_term_dates()();
  
  if (dates.date_sem1) {
    if (document.getElementById("date-sem1")) document.getElementById("date-sem1").value = dates.date_sem1;
    updateBadge("sem1", true);
  } else {
    updateBadge("sem1", false);
  }
  
  if (dates.date_sem2) {
    if (document.getElementById("date-sem2")) document.getElementById("date-sem2").value = dates.date_sem2;
    updateBadge("sem2", true);
  } else {
    updateBadge("sem2", false);
  }
}

function updateBadge(term, isSet) {
  const badge = document.getElementById(`badge-${term}`);
  const col = document.getElementById(`col-${term}`);
  const btn = document.getElementById(`btn-${term}`);
  if (!badge) return;
  if (isSet) {
    badge.textContent = "Scheduled";
    badge.style.background = "#52c589";
    badge.style.color = "#fff";
    badge.style.border = "none";
    if (col) col.style.border = "2px solid #52c589";
    if (btn) {
      btn.classList.remove("btn-light");
      btn.classList.add("btn-dark");
    }
  } else {
    badge.textContent = "Not Set";
    badge.style.background = "#9daaac";
    badge.style.color = "#1c2534";
    badge.style.border = "1px solid rgba(0,0,0,0.1)";
    if (col) col.style.border = "2px solid rgba(255,255,255,0.15)";
    if (btn) {
      btn.classList.remove("btn-dark");
      btn.classList.add("btn-light");
    }
  }
}

if (document.getElementById("btn-sem1")) {
  document.getElementById("btn-sem1").addEventListener("click", async () => {
    const val = document.getElementById("date-sem1").value;
    if (!val) return;
    await eel.save_term_date("date_sem1", val)();
    updateBadge("sem1", true);
  });
}
if (document.getElementById("btn-sem2")) {
  document.getElementById("btn-sem2").addEventListener("click", async () => {
    const val = document.getElementById("date-sem2").value;
    if (!val) return;
    await eel.save_term_date("date_sem2", val)();
    updateBadge("sem2", true);
  });
}

// ============================================================
// Initial load â€” Dashboard is the landing page
// ============================================================
refreshDashboard();
loadTermSetup();
loadFacultyList();
window.addEventListener("beforeunload", stopAllCameras);

// ============================================================
// CAMERA TEST BTN
// ============================================================
const testCamBtn = document.getElementById("testCamBtn");
const testCamResult = document.getElementById("testCamResult");
const testCamImg = document.getElementById("testCamImg");
const testCamText = document.getElementById("testCamText");

if (testCamBtn) {
  testCamBtn.addEventListener("click", async () => {
    const val = document.getElementById("camSourceInput").checked ? '1' : '0';
    testCamBtn.textContent = "Testing...";
    testCamBtn.disabled = true;
    testCamResult.style.display = "none";
    
    const res = await eel.test_camera_source(val)();
    
    if (res.ok) {
        testCamImg.src = res.uri;
        testCamText.textContent = "Success! Native Resolution: " + res.shape;
        testCamText.style.color = "#4dd0e1";
        testCamResult.style.display = "block";
    } else {
        testCamText.textContent = res.msg;
        testCamText.style.color = "#ff6b6b";
        testCamImg.src = "";
        testCamResult.style.display = "block";
    }
    
    testCamBtn.textContent = "Test Camera";
    testCamBtn.disabled = false;
  });
}

const clearSessionBtn = document.getElementById('clearSessionBtn');
if (clearSessionBtn) {
  clearSessionBtn.addEventListener('click', async () => {
    await eel.clear_session_setup()();
    const msg = document.getElementById('clearSessionMsg');
    if (msg) {
      msg.textContent = 'Workspace data cleared successfully!';
      setTimeout(() => msg.textContent = '', 3000);
    }
    loadSessionSetup();
    refreshDashboard();
    loadTermSetup();
  });
}

