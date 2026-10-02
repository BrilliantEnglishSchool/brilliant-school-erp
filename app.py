from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3, os
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date

BASE=os.path.dirname(os.path.abspath(__file__))
DATA_DIR=os.environ.get("DATA_DIR", BASE)
os.makedirs(DATA_DIR, exist_ok=True)
DB=os.path.join(DATA_DIR,"school.db")
app=Flask(__name__)
app.secret_key=os.environ.get("SECRET_KEY","change-this-secret-key-local-only")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE","1") == "1",
)

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

@app.route("/health")
def health():
    try:
        c=db()
        c.execute("SELECT 1").fetchone()
        c.close()
        return {"status":"ok"}, 200
    except Exception:
        return {"status":"error"}, 500

def init_db():
    c=db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'admin');
    CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY AUTOINCREMENT,year INTEGER UNIQUE NOT NULL,status TEXT NOT NULL DEFAULT 'Planned');
    CREATE TABLE IF NOT EXISTS classes(
      id INTEGER PRIMARY KEY AUTOINCREMENT,session_id INTEGER NOT NULL,class_name TEXT NOT NULL,section TEXT,
      class_teacher TEXT,status TEXT DEFAULT 'Active',
      UNIQUE(session_id,class_name,section),FOREIGN KEY(session_id) REFERENCES sessions(id));
    CREATE TABLE IF NOT EXISTS promotions(
      id INTEGER PRIMARY KEY AUTOINCREMENT,from_session_id INTEGER NOT NULL,to_session_id INTEGER NOT NULL,
      student_id INTEGER NOT NULL,from_class TEXT,to_class TEXT,from_section TEXT,to_section TEXT,
      promoted_date TEXT NOT NULL,status TEXT DEFAULT 'Promoted',
      FOREIGN KEY(from_session_id) REFERENCES sessions(id),FOREIGN KEY(to_session_id) REFERENCES sessions(id),
      FOREIGN KEY(student_id) REFERENCES students(id));
    CREATE TABLE IF NOT EXISTS students(
      id INTEGER PRIMARY KEY AUTOINCREMENT,session_id INTEGER NOT NULL,admission_no TEXT NOT NULL,
      name TEXT NOT NULL,dob TEXT,gender TEXT,blood_group TEXT,class_name TEXT NOT NULL,section TEXT,
      roll_no TEXT,parent_name TEXT,mother_name TEXT,phone TEXT,email TEXT,address TEXT,
      admission_date TEXT,previous_school TEXT,aadhaar_last4 TEXT,photo TEXT,status TEXT DEFAULT 'Active',
      FOREIGN KEY(session_id) REFERENCES sessions(id));
    CREATE TABLE IF NOT EXISTS student_documents(
      id INTEGER PRIMARY KEY AUTOINCREMENT,student_id INTEGER NOT NULL,document_type TEXT NOT NULL,
      document_no TEXT,remarks TEXT,FOREIGN KEY(student_id) REFERENCES students(id));
    CREATE TABLE IF NOT EXISTS staff(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,role TEXT,department TEXT,status TEXT DEFAULT 'Active');
    CREATE TABLE IF NOT EXISTS attendance(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id INTEGER NOT NULL,student_id INTEGER NOT NULL,date TEXT NOT NULL,status TEXT NOT NULL,FOREIGN KEY(session_id) REFERENCES sessions(id),FOREIGN KEY(student_id) REFERENCES students(id));
    CREATE TABLE IF NOT EXISTS exams(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id INTEGER NOT NULL,name TEXT NOT NULL,class_name TEXT,subject TEXT,max_marks INTEGER,FOREIGN KEY(session_id) REFERENCES sessions(id));
    CREATE TABLE IF NOT EXISTS marks(id INTEGER PRIMARY KEY AUTOINCREMENT,exam_id INTEGER NOT NULL,student_id INTEGER NOT NULL,marks REAL,FOREIGN KEY(exam_id) REFERENCES exams(id),FOREIGN KEY(student_id) REFERENCES students(id));
    CREATE TABLE IF NOT EXISTS fees(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id INTEGER NOT NULL,student_id INTEGER NOT NULL,amount REAL NOT NULL,paid_date TEXT,receipt_no TEXT,fee_type TEXT,remarks TEXT,FOREIGN KEY(session_id) REFERENCES sessions(id),FOREIGN KEY(student_id) REFERENCES students(id));
    """)
    if not c.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        admin_username=os.environ.get("ADMIN_USERNAME","admin")
        admin_password=os.environ.get("ADMIN_PASSWORD","admin123")
        c.execute("INSERT INTO users(username,password,role) VALUES(?,?,?)",(admin_username,generate_password_hash(admin_password),"admin"))
    for y,s in [(2026,"Active"),(2027,"Planned"),(2028,"Planned")]:
        c.execute("INSERT OR IGNORE INTO sessions(year,status) VALUES(?,?)",(y,s))
    if not c.execute("SELECT 1 FROM staff LIMIT 1").fetchone():
        c.execute("INSERT INTO staff(name,role,department) VALUES(?,?,?)",("Md Ahamad Khan","Founder-Principal","Administration"))
        c.execute("INSERT INTO staff(name,role,department) VALUES(?,?,?)",("Md Nasir Khan","Exam Controller","Academic"))
        # V13/V14 support tables
    c.execute("""CREATE TABLE IF NOT EXISTS sections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS staff_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_code TEXT,
        full_name TEXT NOT NULL,
        designation TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS periods (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        period_no INTEGER NOT NULL,
        label TEXT NOT NULL,
        start_time TEXT,
        end_time TEXT,
        UNIQUE(session_id,period_no)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS timetable_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        class_id INTEGER NOT NULL,
        section_id INTEGER,
        day TEXT NOT NULL,
        period_id INTEGER NOT NULL,
        subject_id INTEGER,
        teacher_id INTEGER,
        room TEXT,
        notes TEXT,
        UNIQUE(session_id,class_id,section_id,day,period_id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS academic_calendar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        event_date TEXT NOT NULL,
        title TEXT NOT NULL,
        event_type TEXT NOT NULL DEFAULT 'Academic',
        description TEXT,
        is_holiday INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS portal_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL UNIQUE,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'Parent',
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    # Seed V13/V14 master data
    for _name in ["A","B","C"]:
        c.execute("INSERT OR IGNORE INTO sections(name) VALUES(?)",(_name,))
    for _name in ["English","Hindi","Mathematics","Science","Social Science","Computer","General Knowledge"]:
        c.execute("INSERT OR IGNORE INTO subjects(name) VALUES(?)",(_name,))
    if not c.execute("SELECT 1 FROM staff_profiles LIMIT 1").fetchone():
        for _code,_name,_des in [("BES001","Md Ahamad Khan","Founder-Principal"),("BES002","Md Nasir Khan","Exam Controller")]:
            c.execute("INSERT INTO staff_profiles(employee_code,full_name,designation) VALUES(?,?,?)",(_code,_name,_des))
    # V15 Hostel Management
    c.execute("""CREATE TABLE IF NOT EXISTS hostel_admissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        session_id INTEGER NOT NULL,
        hostel_name TEXT NOT NULL,
        room_no TEXT,
        bed_no TEXT,
        admission_date TEXT NOT NULL,
        guardian_name TEXT,
        guardian_phone TEXT,
        status TEXT NOT NULL DEFAULT 'Active',
        remarks TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS hostel_fee_structures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        hostel_name TEXT NOT NULL,
        fee_name TEXT NOT NULL,
        amount REAL NOT NULL DEFAULT 0,
        frequency TEXT NOT NULL DEFAULT 'Monthly',
        class_name TEXT,
        active INTEGER DEFAULT 1
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS hostel_fee_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admission_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        session_id INTEGER NOT NULL,
        receipt_no TEXT NOT NULL UNIQUE,
        payment_date TEXT NOT NULL,
        fee_name TEXT NOT NULL,
        amount REAL NOT NULL DEFAULT 0,
        payment_mode TEXT NOT NULL DEFAULT 'Cash',
        reference_no TEXT,
        remarks TEXT
    )""")
    c.commit(); c.close()

def login_required(f):
    @wraps(f)
    def w(*a,**kw):
        if "user_id" not in session:return redirect(url_for("login"))
        return f(*a,**kw)
    return w

def active_session():
    c=db(); r=c.execute("SELECT * FROM sessions WHERE status='Active' LIMIT 1").fetchone(); c.close(); return r


def _scalar(db, sql, params=()):
    row = db.execute(sql, params).fetchone()
    if not row:
        return 0
    value = row[0]
    return value if value is not None else 0

def _rows(db, sql, params=()):
    return db.execute(sql, params).fetchall()

def _month_bounds(month_value):
    try:
        y, m = [int(x) for x in month_value.split("-")]
        start = f"{y:04d}-{m:02d}-01"
        if m == 12:
            end = f"{y+1:04d}-01-01"
        else:
            end = f"{y:04d}-{m+1:02d}-01"
        return start, end
    except Exception:
        today = date.today()
        start = f"{today.year:04d}-{today.month:02d}-01"
        if today.month == 12:
            end = f"{today.year+1:04d}-01-01"
        else:
            end = f"{today.year:04d}-{today.month+1:02d}-01"
        return start, end

def _current_month():
    return date.today().strftime("%Y-%m")

@app.get("/health")
def health():
    try:
        c=db(); c.execute("SELECT 1").fetchone(); c.close()
        return {"status":"ok","service":"Brilliant English School ERP"}, 200
    except Exception:
        return {"status":"error"}, 500

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        c=db(); u=c.execute("SELECT * FROM users WHERE username=?",(request.form["username"],)).fetchone(); c.close()
        if u and check_password_hash(u["password"],request.form["password"]):
            session["user_id"]=u["id"];session["username"]=u["username"];return redirect(url_for("dashboard"))
        flash("Invalid username or password.")
    return render_template("login.html")

@app.route("/logout")
def logout():session.clear();return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    c=db()
    s=active_session()
    capacity=500
    if not s:
        c.close()
        return render_template("dashboard.html",active=None,stats={"students":0,"staff":0,"classes":0,"parents":0},
                               capacity=capacity,seats=capacity,session_reports=[],class_report=[],hostel_residents=0,
                               fee_total=0,notices=0)

    students=c.execute("SELECT COUNT(*) n FROM students WHERE session_id=? AND status='Active'",(s["id"],)).fetchone()["n"]
    staff=c.execute("SELECT COUNT(*) n FROM staff WHERE status='Active'").fetchone()["n"]
    classes=c.execute("SELECT COUNT(DISTINCT class_name) n FROM students WHERE session_id=? AND status='Active'",(s["id"],)).fetchone()["n"]
    parents=c.execute("SELECT COUNT(DISTINCT parent_name) n FROM students WHERE session_id=? AND parent_name<>''",(s["id"],)).fetchone()["n"]
    seats=max(capacity-students,0)

    session_reports=c.execute("""
        SELECT se.year,
               SUM(CASE WHEN st.gender='Male' THEN 1 ELSE 0 END) male,
               SUM(CASE WHEN st.gender='Female' THEN 1 ELSE 0 END) female,
               COUNT(st.id) total
        FROM sessions se LEFT JOIN students st ON st.session_id=se.id AND st.status='Active'
        GROUP BY se.id ORDER BY se.year DESC
    """).fetchall()

    class_report=c.execute("""
        SELECT class_name,
               SUM(CASE WHEN gender='Male' THEN 1 ELSE 0 END) male,
               SUM(CASE WHEN gender='Female' THEN 1 ELSE 0 END) female,
               COUNT(*) total
        FROM students
        WHERE session_id=? AND status='Active'
        GROUP BY class_name
        ORDER BY
          CASE
            WHEN lower(class_name)='nursery' THEN 0
            WHEN lower(class_name)='kg' THEN 1
            WHEN class_name GLOB '[0-9]*' THEN CAST(class_name AS INTEGER)
            WHEN class_name LIKE 'Class %' THEN CAST(substr(class_name,7) AS INTEGER)
            ELSE 99
          END, class_name
    """,(s["id"],)).fetchall()

    hostel_residents=c.execute("SELECT COUNT(*) n FROM hostel_admissions WHERE session_id=? AND status='Active'",(s["id"],)).fetchone()["n"]
    fee_total=c.execute("SELECT COALESCE(SUM(amount),0) n FROM fees WHERE session_id=?",(s["id"],)).fetchone()["n"]
    notices=c.execute("SELECT COUNT(*) n FROM notices WHERE status='Published'").fetchone()["n"] if c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notices'").fetchone() else 0
    c.close()
    return render_template("dashboard.html",active=s,
                           stats={"students":students,"staff":staff,"classes":classes,"parents":parents},
                           capacity=capacity,seats=seats,session_reports=session_reports,
                           class_report=class_report,hostel_residents=hostel_residents,
                           fee_total=fee_total,notices=notices)

@app.route("/sessions",methods=["GET","POST"])
@login_required
def sessions_page():
    c=db()
    if request.method=="POST":
        try:y=int(request.form["year"])
        except: y=0
        if y<2000 or y>2100:flash("Enter a valid session year.")
        elif c.execute("SELECT 1 FROM sessions WHERE year=?",(y,)).fetchone():flash("That session already exists.")
        else:c.execute("INSERT INTO sessions(year,status) VALUES(?,?)",(y,"Planned"));c.commit();flash(f"Session {y} created.")
    rows=c.execute("SELECT * FROM sessions ORDER BY year").fetchall();c.close()
    return render_template("sessions.html",sessions=rows,active=active_session())

@app.post("/sessions/<int:year>/activate")
@login_required
def activate(year):
    c=db();c.execute("UPDATE sessions SET status='Planned'");c.execute("UPDATE sessions SET status='Active' WHERE year=?",(year,));c.commit();c.close();flash(f"Academic session {year} is now active.");return redirect(url_for("sessions_page"))

@app.route("/students",methods=["GET","POST"])
@login_required
def students():
    s=active_session();c=db()
    if request.method=="POST":
        f=request.form
        n=f.get("name","").strip()
        if not n or not f.get("class_name"):flash("Student name and class are required.")
        else:
            count=c.execute("SELECT COUNT(*) n FROM students WHERE session_id=?",(s["id"],)).fetchone()["n"]+1
            adm=f.get("admission_no").strip() or f"BES-{s['year']}-{count:03d}"
            c.execute("""INSERT INTO students(session_id,admission_no,name,dob,gender,blood_group,class_name,section,roll_no,parent_name,mother_name,phone,email,address,admission_date,previous_school,aadhaar_last4,status)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (s["id"],adm,n,f.get("dob"),f.get("gender"),f.get("blood_group"),f.get("class_name"),f.get("section"),f.get("roll_no"),f.get("parent_name"),f.get("mother_name"),f.get("phone"),f.get("email"),f.get("address"),f.get("admission_date") or str(date.today()),f.get("previous_school"),f.get("aadhaar_last4"),"Active"))
            c.commit();flash(f"{n} admitted successfully with admission no. {adm}.");return redirect(url_for("students"))
    q=request.args.get("q","").strip()
    if q:
        rows=c.execute("""SELECT * FROM students WHERE session_id=? AND (name LIKE ? OR admission_no LIKE ? OR class_name LIKE ? OR parent_name LIKE ?) ORDER BY class_name,roll_no,name""",(s["id"],f"%{q}%",f"%{q}%",f"%{q}%",f"%{q}%")).fetchall()
    else:rows=c.execute("SELECT * FROM students WHERE session_id=? ORDER BY class_name,roll_no,name",(s["id"],)).fetchall()
    c.close();return render_template("students.html",students=rows,active=s,q=q)

@app.route("/students/<int:student_id>")
@login_required
def student_profile(student_id):
    c=db();x=c.execute("SELECT students.*,sessions.year FROM students JOIN sessions ON sessions.id=students.session_id WHERE students.id=?",(student_id,)).fetchone()
    docs=c.execute("SELECT * FROM student_documents WHERE student_id=? ORDER BY id DESC",(student_id,)).fetchall()
    c.close()
    if not x:return "Student not found",404
    return render_template("student_profile.html",student=x,docs=docs)

@app.post("/students/<int:student_id>/document")
@login_required
def add_document(student_id):
    f=request.form;c=db();c.execute("INSERT INTO student_documents(student_id,document_type,document_no,remarks) VALUES(?,?,?,?)",(student_id,f.get("document_type"),f.get("document_no"),f.get("remarks")));c.commit();c.close();flash("Document record added.");return redirect(url_for("student_profile",student_id=student_id))


@app.route("/classes",methods=["GET","POST"])
@login_required
def classes_page():
    s=active_session(); c=db()
    if request.method=="POST":
        f=request.form
        cn=f.get("class_name","").strip(); sec=f.get("section","").strip(); teacher=f.get("class_teacher","").strip()
        if cn:
            try:
                c.execute("INSERT INTO classes(session_id,class_name,section,class_teacher) VALUES(?,?,?,?)",(s["id"],cn,sec,teacher))
                c.commit(); flash(f"{cn} {sec or ''} added to session {s['year']}.")
            except sqlite3.IntegrityError: flash("That class and section already exists.")
    rows=c.execute("""SELECT classes.*,COUNT(students.id) student_count
                      FROM classes LEFT JOIN students ON students.session_id=classes.session_id
                      AND students.class_name=classes.class_name
                      AND COALESCE(students.section,'')=COALESCE(classes.section,'')
                      WHERE classes.session_id=? GROUP BY classes.id ORDER BY classes.class_name,classes.section""",(s["id"],)).fetchall()
    # If no class records yet, derive class/section rows from students.
    if not rows:
        derived=c.execute("""SELECT class_name,COALESCE(section,'') section,COUNT(*) student_count
                             FROM students WHERE session_id=? GROUP BY class_name,section ORDER BY class_name,section""",(s["id"],)).fetchall()
        rows=[dict(class_name=x["class_name"],section=x["section"],student_count=x["student_count"],class_teacher="") for x in derived]
    c.close(); return render_template("classes.html",classes=rows,active=s)

@app.route("/promote",methods=["GET","POST"])
@login_required
def promote():
    from_session=active_session(); c=db()
    future=c.execute("SELECT * FROM sessions WHERE year>? ORDER BY year",(from_session["year"],)).fetchall()
    target_id=int(request.form["to_session_id"]) if request.method=="POST" and request.form.get("to_session_id") else (future[0]["id"] if future else None)
    selected=[]
    if request.method=="POST" and target_id:
        target=c.execute("SELECT * FROM sessions WHERE id=?",(target_id,)).fetchone()
        student_ids=request.form.getlist("student_id")
        for sid in student_ids:
            st=c.execute("SELECT * FROM students WHERE id=? AND session_id=?",(int(sid),from_session["id"])).fetchone()
            if not st: continue
            to_class=request.form.get(f"to_class_{sid}",st["class_name"])
            to_section=request.form.get(f"to_section_{sid}",st["section"] or "")
            # Avoid duplicate promotion for same student/session.
            exists=c.execute("SELECT 1 FROM promotions WHERE student_id=? AND to_session_id=?",(st["id"],target["id"])).fetchone()
            if not exists:
                c.execute("""INSERT INTO promotions(from_session_id,to_session_id,student_id,from_class,to_class,from_section,to_section,promoted_date)
                             VALUES(?,?,?,?,?,?,?,?)""",(from_session["id"],target["id"],st["id"],st["class_name"],to_class,st["section"] or "",to_section,str(date.today())))
                # Create the student in the target session with a new admission record preserving identity.
                newadm=f"BES-{target['year']}-P{st['id']:04d}"
                duplicate=c.execute("SELECT 1 FROM students WHERE session_id=? AND admission_no=?",(target["id"],newadm)).fetchone()
                if not duplicate:
                    c.execute("""INSERT INTO students(session_id,admission_no,name,dob,gender,blood_group,class_name,section,roll_no,parent_name,mother_name,phone,email,address,admission_date,previous_school,aadhaar_last4,status)
                                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                              (target["id"],newadm,st["name"],st["dob"],st["gender"],st["blood_group"],to_class,to_section,"",st["parent_name"],st["mother_name"],st["phone"],st["email"],st["address"],str(date.today()),"Promoted from "+str(from_session["year"]),st["aadhaar_last4"],"Active"))
        c.commit(); flash(f"Selected students promoted to session {target['year']}.")
    students=c.execute("SELECT * FROM students WHERE session_id=? AND status='Active' ORDER BY class_name,roll_no,name",(from_session["id"],)).fetchall()
    promotions=c.execute("""SELECT promotions.*,students.name,fs.year from_year,ts.year to_year
                            FROM promotions JOIN students ON students.id=promotions.student_id
                            JOIN sessions fs ON fs.id=promotions.from_session_id JOIN sessions ts ON ts.id=promotions.to_session_id
                            WHERE promotions.from_session_id=? ORDER BY promotions.id DESC""",(from_session["id"],)).fetchall()
    c.close(); return render_template("promote.html",students=students,sessions=future,active=from_session,promotions=promotions)

@app.route("/staff")
@login_required
def staff():
    c=db();rows=c.execute("SELECT * FROM staff ORDER BY name").fetchall();c.close();return render_template("staff.html",staff=rows,active=active_session())

@app.route("/attendance")
@login_required
def attendance():
    s=active_session();c=db();rows=c.execute("SELECT * FROM students WHERE session_id=? AND status='Active' ORDER BY class_name,roll_no,name",(s["id"],)).fetchall();c.close();return render_template("attendance.html",students=rows,active=s)

@app.post("/attendance/save")
@login_required
def attendance_save():
    s=active_session();today=request.form.get("date") or str(date.today());c=db()
    for key,status in request.form.items():
        if key.startswith("student_"):
            sid=int(key.split("_")[1]);c.execute("INSERT INTO attendance(session_id,student_id,date,status) VALUES(?,?,?,?)",(s["id"],sid,today,status))
    c.commit();c.close();flash("Attendance saved.");return redirect(url_for("attendance"))

@app.route("/exams")
@login_required
def exams():
    s=active_session();c=db();rows=c.execute("SELECT * FROM exams WHERE session_id=? ORDER BY id DESC",(s["id"],)).fetchall();c.close();return render_template("exams.html",exams=rows,active=s)

@app.route("/fees")
@login_required
def fees():
    s=active_session();c=db();rows=c.execute("SELECT fees.*,students.name FROM fees JOIN students ON students.id=fees.student_id WHERE fees.session_id=? ORDER BY fees.id DESC",(s["id"],)).fetchall();c.close();return render_template("fees.html",fees=rows,active=s)

init_db()

@app.route("/analytics")
def analytics():
    if "user_id" not in session:
        return redirect(url_for("login"))
    db = db()
    active_session = active_session()
    session_id = active_session["id"] if active_session else None
    month = request.args.get("month") or _current_month()
    start, end = _month_bounds(month)

    # Core KPIs
    student_where = "WHERE active=1"
    student_params = []
    if session_id is not None:
        student_where += " AND session_id=?"
        student_params.append(session_id)

    total_students = _scalar(db, f"SELECT COUNT(*) FROM students {student_where}", student_params)
    total_staff = _scalar(db, "SELECT COUNT(*) FROM staff_profiles WHERE 1=1")
    total_classes = _scalar(db, "SELECT COUNT(*) FROM classes")
    total_sections = _scalar(db, "SELECT COUNT(*) FROM sections")

    att_params = [start, end]
    if session_id is not None:
        att_params.append(session_id)
        att_session = " AND session_id=?"
    else:
        att_session = ""
    attendance_counts = {
        "Present": _scalar(db, f"SELECT COUNT(*) FROM attendance WHERE attendance_date>=? AND attendance_date<?{att_session} AND status='Present'", att_params),
        "Absent": _scalar(db, f"SELECT COUNT(*) FROM attendance WHERE attendance_date>=? AND attendance_date<?{att_session} AND status='Absent'", att_params),
        "Late": _scalar(db, f"SELECT COUNT(*) FROM attendance WHERE attendance_date>=? AND attendance_date<?{att_session} AND status='Late'", att_params),
        "Leave": _scalar(db, f"SELECT COUNT(*) FROM attendance WHERE attendance_date>=? AND attendance_date<?{att_session} AND status='Leave'", att_params),
    }
    att_total = sum(attendance_counts.values())
    attendance_pct = round(attendance_counts["Present"] / att_total * 100, 2) if att_total else 0

    fee_params=[start,end]
    fee_session=""
    if session_id is not None:
        fee_params.append(session_id)
        fee_session=" AND session_id=?"
    fee_collected = _scalar(db, f"SELECT COALESCE(SUM(amount),0) FROM fee_payments WHERE payment_date>=? AND payment_date<?{fee_session}", fee_params)
    fee_due = _scalar(db, f"SELECT COALESCE(SUM(amount_due),0) FROM fee_payments WHERE 1=1{fee_session}", [session_id] if session_id is not None else [])
    expenses = _scalar(db, f"SELECT COALESCE(SUM(amount),0) FROM expenses WHERE expense_date>=? AND expense_date<?", [start,end])

    pending_admissions = _scalar(db, "SELECT COUNT(*) FROM admission_applications WHERE status IN ('Pending','Submitted','Under Review')")
    admitted_apps = _scalar(db, "SELECT COUNT(*) FROM admission_applications WHERE status IN ('Admitted','Approved')")
    notices = _scalar(db, "SELECT COUNT(*) FROM notices WHERE status='Published'")

    payroll_params=[start,end]
    payroll_session=""
    if session_id is not None:
        payroll_params.append(session_id)
        payroll_session=" AND session_id=?"
    payroll_paid = _scalar(db, f"SELECT COALESCE(SUM(net_salary),0) FROM payroll WHERE payment_date>=? AND payment_date<?{payroll_session}", payroll_params)

    # Class distribution
    class_rows=_rows(db, f"""
        SELECT COALESCE(c.name,'Unassigned') AS class_name,
               COUNT(s.id) AS student_count
        FROM classes c
        LEFT JOIN students s ON s.class_id=c.id AND s.active=1
        {"AND s.session_id=?" if session_id is not None else ""}
        GROUP BY c.id, c.name
        ORDER BY c.name
    """, [session_id] if session_id is not None else [])
    max_class=max([r["student_count"] for r in class_rows] or [1])

    # Gender distribution
    gender_rows=_rows(db, f"""
        SELECT COALESCE(gender,'Not Specified') AS label, COUNT(*) AS count
        FROM students {student_where}
        GROUP BY gender ORDER BY count DESC
    """, student_params)

    # Attendance status rows
    attendance_rows=[{"label":k,"count":v} for k,v in attendance_counts.items()]

    # Fee collection by month in active session/year
    year=date.today().year
    fee_month_rows=[]
    for m in range(1,13):
        ms=f"{year:04d}-{m:02d}-01"
        me=f"{year+1:04d}-01-01" if m==12 else f"{year:04d}-{m+1:02d}-01"
        p=[ms,me]
        ss=""
        if session_id is not None:
            p.append(session_id); ss=" AND session_id=?"
        amt=_scalar(db,f"SELECT COALESCE(SUM(amount),0) FROM fee_payments WHERE payment_date>=? AND payment_date<?{ss}",p)
        fee_month_rows.append({"month":date(year,m,1).strftime("%b"),"amount":float(amt or 0)})

    # Admissions by status
    admission_rows=_rows(db,"SELECT COALESCE(status,'Unknown') label, COUNT(*) count FROM admission_applications GROUP BY status ORDER BY count DESC")

    # Exam performance for latest/selected exam group
    exam_groups=_rows(db, "SELECT id, name FROM exam_groups ORDER BY id DESC")
    selected_group=request.args.get("exam_group_id", type=int)
    if not selected_group and exam_groups:
        selected_group=exam_groups[0]["id"]
    exam_summary=None
    if selected_group:
        exam_summary=_rows(db, """
            SELECT
              COUNT(DISTINCT rm.student_id) AS students,
              ROUND(AVG(CASE WHEN ep.max_marks>0 THEN rm.marks*100.0/ep.max_marks END),2) AS average_percentage,
              ROUND(100.0*SUM(CASE WHEN rm.marks*100.0/ep.max_marks >= ep.pass_marks*100.0/ep.max_marks THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0),2) AS pass_rate
            FROM result_marks rm
            JOIN exam_papers ep ON ep.id=rm.paper_id
            WHERE ep.exam_group_id=?
        """,[selected_group])
        exam_summary=exam_summary[0] if exam_summary else None

    return render_template("analytics.html",
        active_session=active_session, month=month,
        total_students=total_students, total_staff=total_staff,
        total_classes=total_classes, total_sections=total_sections,
        attendance_counts=attendance_counts, attendance_pct=attendance_pct,
        fee_collected=fee_collected, fee_due=fee_due, expenses=expenses,
        pending_admissions=pending_admissions, admitted_apps=admitted_apps,
        notices=notices, payroll_paid=payroll_paid,
        class_rows=class_rows, max_class=max_class,
        gender_rows=gender_rows, attendance_rows=attendance_rows,
        fee_month_rows=fee_month_rows, admission_rows=admission_rows,
        exam_groups=exam_groups, selected_group=selected_group,
        exam_summary=exam_summary)

@app.route("/analytics/print")
def analytics_print():
    if "user_id" not in session:
        return redirect(url_for("login"))
    # Reuse analytics page as a clean printable view.
    request.args = request.args
    return analytics()


@app.route("/timetable")
def timetable():
    if "user_id" not in session:
        return redirect(url_for("login"))
    db=db()
    active=active_session()
    if not active:
        return render_template("timetable.html", active_session=None, periods=[], classes=[], sections=[], subjects=[], staff=[], entries=[], days=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"], selected_class=None, selected_section=None)
    sid=active["id"]
    # Default periods if none exist for the session
    if _scalar(db,"SELECT COUNT(*) FROM periods WHERE session_id=?",[sid]) == 0:
        defaults=[
            ("1","Period 1","08:00","08:40"),("2","Period 2","08:40","09:20"),
            ("3","Period 3","09:20","10:00"),("4","Period 4","10:20","11:00"),
            ("5","Period 5","11:00","11:40"),("6","Period 6","11:40","12:20"),
        ]
        for no,label,st,et in defaults:
            db.execute("INSERT OR IGNORE INTO periods(session_id,period_no,label,start_time,end_time) VALUES(?,?,?,?,?)",(sid,int(no),label,st,et))
        db.commit()
    periods=_rows(db,"SELECT * FROM periods WHERE session_id=? ORDER BY period_no",[sid])
    classes=_rows(db,"SELECT * FROM classes ORDER BY class_name")
    sections=_rows(db,"SELECT * FROM sections ORDER BY name")
    subjects=_rows(db,"SELECT * FROM subjects ORDER BY name")
    staff=_rows(db,"SELECT sp.id, sp.employee_code, sp.full_name, sp.designation FROM staff_profiles sp ORDER BY sp.full_name")
    selected_class=request.args.get("class_id",type=int)
    selected_section=request.args.get("section_id",type=int)
    entries=[]
    if selected_class:
        entries=_rows(db,"""
          SELECT t.*, p.period_no, p.label period_label, p.start_time, p.end_time,
                 COALESCE(su.name,'') subject_name,
                 COALESCE(sp.full_name,'') teacher_name,
                 COALESCE(c.class_name,'') class_name, COALESCE(sec.name,'') section_name
          FROM timetable_entries t
          JOIN periods p ON p.id=t.period_id
          LEFT JOIN subjects su ON su.id=t.subject_id
          LEFT JOIN staff_profiles sp ON sp.id=t.teacher_id
          LEFT JOIN classes c ON c.id=t.class_id
          LEFT JOIN sections sec ON sec.id=t.section_id
          WHERE t.session_id=? AND t.class_id=? AND (t.section_id=? OR ? IS NULL)
          ORDER BY p.period_no, CASE t.day WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3 WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 WHEN 'Saturday' THEN 6 END
        """,[sid,selected_class,selected_section,selected_section])
    calendar=_rows(db,"SELECT * FROM academic_calendar WHERE session_id=? ORDER BY event_date",[sid])
    return render_template("timetable.html",active_session=active,periods=periods,classes=classes,sections=sections,subjects=subjects,staff=staff,entries=entries,calendar=calendar,
        days=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"],selected_class=selected_class,selected_section=selected_section)

@app.route("/timetable/save",methods=["POST"])
def timetable_save():
    if "user_id" not in session: return redirect(url_for("login"))
    db=db(); active=active_session()
    if not active: return redirect(url_for("timetable"))
    sid=active["id"]
    try:
        cid=int(request.form["class_id"]); sec=request.form.get("section_id") or None
        sec=int(sec) if sec else None
        day=request.form["day"]; pid=int(request.form["period_id"])
        subject=request.form.get("subject_id") or None; teacher=request.form.get("teacher_id") or None
        room=request.form.get("room","").strip(); notes=request.form.get("notes","").strip()
        subject=int(subject) if subject else None; teacher=int(teacher) if teacher else None
        existing=db.execute("SELECT id FROM timetable_entries WHERE session_id=? AND class_id=? AND section_id IS ? AND day=? AND period_id=?",(sid,cid,sec,day,pid)).fetchone()
        if existing:
            db.execute("""UPDATE timetable_entries SET subject_id=?,teacher_id=?,room=?,notes=? WHERE id=?""",(subject,teacher,room,notes,existing["id"]))
        else:
            db.execute("""INSERT INTO timetable_entries(session_id,class_id,section_id,day,period_id,subject_id,teacher_id,room,notes) VALUES(?,?,?,?,?,?,?,?,?)""",(sid,cid,sec,day,pid,subject,teacher,room,notes))
        db.commit()
    except Exception:
        pass
    return redirect(url_for("timetable",class_id=cid,section_id=sec or ""))

@app.route("/timetable/delete/<int:entry_id>",methods=["POST"])
def timetable_delete(entry_id):
    if "user_id" not in session: return redirect(url_for("login"))
    db=db(); row=db.execute("SELECT class_id,section_id FROM timetable_entries WHERE id=?",[entry_id]).fetchone()
    db.execute("DELETE FROM timetable_entries WHERE id=?",[entry_id]); db.commit()
    return redirect(url_for("timetable",class_id=row["class_id"] if row else ""))

@app.route("/timetable/periods",methods=["POST"])
def timetable_periods():
    if "user_id" not in session: return redirect(url_for("login"))
    db=db(); active=active_session()
    if active:
        sid=active["id"]
        no=int(request.form.get("period_no",1)); label=request.form.get("label","").strip() or f"Period {no}"
        st=request.form.get("start_time",""); et=request.form.get("end_time","")
        db.execute("INSERT INTO periods(session_id,period_no,label,start_time,end_time) VALUES(?,?,?,?,?) ON CONFLICT(session_id,period_no) DO UPDATE SET label=excluded.label,start_time=excluded.start_time,end_time=excluded.end_time",(sid,no,label,st,et))
        db.commit()
    return redirect(url_for("timetable"))

@app.route("/calendar")
def calendar():
    if "user_id" not in session: return redirect(url_for("login"))
    db=db(); active=active_session()
    events=_rows(db,"SELECT * FROM academic_calendar WHERE session_id=? ORDER BY event_date",[active["id"]]) if active else []
    return render_template("calendar.html",active_session=active,events=events)

@app.route("/calendar/save",methods=["POST"])
def calendar_save():
    if "user_id" not in session: return redirect(url_for("login"))
    db=db(); active=active_session()
    if active:
        db.execute("INSERT INTO academic_calendar(session_id,event_date,title,event_type,description,is_holiday) VALUES(?,?,?,?,?,?)",
            (active["id"],request.form.get("event_date"),request.form.get("title"),request.form.get("event_type","Academic"),request.form.get("description",""),1 if request.form.get("is_holiday") else 0))
        db.commit()
    return redirect(url_for("calendar"))

@app.route("/calendar/delete/<int:event_id>",methods=["POST"])
def calendar_delete(event_id):
    if "user_id" not in session: return redirect(url_for("login"))
    db=db(); db.execute("DELETE FROM academic_calendar WHERE id=?",[event_id]); db.commit()
    return redirect(url_for("calendar"))


@app.route("/portal/login", methods=["GET","POST"])
def portal_login():
    if request.method=="POST":
        username=request.form.get("username","").strip()
        password=request.form.get("password","")
        c=db()
        account=c.execute("SELECT * FROM portal_accounts WHERE username=? AND active=1",(username,)).fetchone()
        c.close()
        if account and check_password_hash(account["password_hash"],password):
            session["portal_user_id"]=account["id"]
            session["portal_student_id"]=account["student_id"]
            session["portal_role"]=account["role"]
            return redirect(url_for("portal_dashboard"))
        return render_template("portal_login.html",error="Invalid username or password.")
    return render_template("portal_login.html",error=None)

@app.route("/portal/logout")
def portal_logout():
    for k in ("portal_user_id","portal_student_id","portal_role"): session.pop(k,None)
    return redirect(url_for("portal_login"))

@app.route("/portal")
def portal_dashboard():
    if "portal_user_id" not in session:
        return redirect(url_for("portal_login"))
    c=db(); sid=session["portal_student_id"]
    st=c.execute("SELECT * FROM students WHERE id=?",(sid,)).fetchone()
    if not st:
        c.close(); return redirect(url_for("portal_logout"))
    sess=active_session()
    session_id=sess["id"] if sess else st["session_id"]

    att=c.execute("SELECT status,COUNT(*) count FROM attendance WHERE student_id=? AND session_id=? GROUP BY status",(sid,session_id)).fetchall()
    att_map={r["status"]:r["count"] for r in att}; total=sum(att_map.values())
    attendance_pct=round(att_map.get("Present",0)*100/total,2) if total else 0

    results=c.execute("""SELECT e.name exam_name,e.subject,e.max_marks,m.marks
        FROM marks m JOIN exams e ON e.id=m.exam_id
        WHERE m.student_id=? AND e.session_id=? ORDER BY e.id DESC""",(sid,session_id)).fetchall()

    payments=c.execute("""SELECT paid_date,receipt_no,amount,fee_type FROM fees
        WHERE student_id=? AND session_id=? ORDER BY id DESC LIMIT 10""",(sid,session_id)).fetchall()
    fee_paid=c.execute("SELECT COALESCE(SUM(amount),0) total FROM fees WHERE student_id=? AND session_id=?",(sid,session_id)).fetchone()["total"]

    timetable=c.execute("""SELECT t.day,p.period_no,p.label,p.start_time,p.end_time,
        COALESCE(su.name,'Free') subject_name,COALESCE(sp.full_name,'') teacher_name,t.room
        FROM timetable_entries t JOIN periods p ON p.id=t.period_id
        LEFT JOIN subjects su ON su.id=t.subject_id LEFT JOIN staff_profiles sp ON sp.id=t.teacher_id
        WHERE t.session_id=? AND t.class_id=? AND (t.section_id=? OR t.section_id IS NULL)
        ORDER BY CASE t.day WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3 WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 WHEN 'Saturday' THEN 6 END,p.period_no""",
        (session_id,st["id"] if False else 0,st["section"] or None))
    # V13 stores class name rather than class_id on students; map it to a class record.
    class_row=c.execute("SELECT id FROM classes WHERE session_id=? AND class_name=? AND COALESCE(section,'')=COALESCE(?, '') LIMIT 1",
                        (session_id,st["class_name"],st["section"] or "")).fetchone()
    if class_row:
        timetable=c.execute("""SELECT t.day,p.period_no,p.label,p.start_time,p.end_time,
            COALESCE(su.name,'Free') subject_name,COALESCE(sp.full_name,'') teacher_name,t.room
            FROM timetable_entries t JOIN periods p ON p.id=t.period_id
            LEFT JOIN subjects su ON su.id=t.subject_id LEFT JOIN staff_profiles sp ON sp.id=t.teacher_id
            WHERE t.session_id=? AND t.class_id=? AND (t.section_id IS NULL OR t.section_id=(SELECT id FROM sections WHERE name=? LIMIT 1))
            ORDER BY CASE t.day WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3 WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 WHEN 'Saturday' THEN 6 END,p.period_no""",
            (session_id,class_row["id"],st["section"] or "" )).fetchall()
    calendar=c.execute("SELECT event_date,title,event_type,description,is_holiday FROM academic_calendar WHERE session_id=? ORDER BY event_date LIMIT 12",(session_id,)).fetchall()
    c.close()
    return render_template("portal_dashboard.html",student=st,active_session=sess,attendance=att_map,attendance_pct=attendance_pct,
                           results=results,payments=payments,fee_paid=fee_paid,timetable=timetable,calendar=calendar)

@app.route("/portal/account/create",methods=["POST"])
def portal_account_create():
    if "user_id" not in session: return redirect(url_for("login"))
    c=db(); student_id=int(request.form["student_id"]); username=request.form["username"].strip()
    password=request.form["password"]; role=request.form.get("role","Parent")
    try:
        c.execute("INSERT INTO portal_accounts(student_id,username,password_hash,role,active) VALUES(?,?,?,?,1)",
                  (student_id,username,generate_password_hash(password),role)); c.commit()
    except Exception: pass
    c.close(); return redirect(url_for("portal_accounts"))

@app.route("/portal/accounts")
def portal_accounts():
    if "user_id" not in session: return redirect(url_for("login"))
    c=db()
    accounts=c.execute("""SELECT pa.*,s.admission_no,s.name student_name,s.class_name
        FROM portal_accounts pa JOIN students s ON s.id=pa.student_id ORDER BY s.name""").fetchall()
    students=c.execute("""SELECT s.id,s.admission_no,s.name student_name,s.class_name FROM students s
        WHERE s.status='Active' AND NOT EXISTS(SELECT 1 FROM portal_accounts pa WHERE pa.student_id=s.id)
        ORDER BY s.name""").fetchall()
    c.close(); return render_template("portal_accounts.html",accounts=accounts,students=students)

@app.route("/portal/account/toggle/<int:account_id>",methods=["POST"])
def portal_account_toggle(account_id):
    if "user_id" not in session: return redirect(url_for("login"))
    c=db(); c.execute("UPDATE portal_accounts SET active=CASE WHEN active=1 THEN 0 ELSE 1 END WHERE id=?",(account_id,)); c.commit(); c.close()
    return redirect(url_for("portal_accounts"))


@app.route("/hostel")
def hostel():
    if "user_id" not in session: return redirect(url_for("login"))
    c=db()
    sess=active_session()
    sid=sess["id"] if sess else None
    admissions=c.execute("""SELECT ha.*,s.name student_name,s.admission_no,s.class_name
        FROM hostel_admissions ha JOIN students s ON s.id=ha.student_id
        WHERE ha.session_id=? ORDER BY ha.id DESC""",(sid,)).fetchall() if sid else []
    structures=c.execute("""SELECT * FROM hostel_fee_structures WHERE session_id=? ORDER BY hostel_name,fee_name""",(sid,)).fetchall() if sid else []
    payments=c.execute("""SELECT hp.*,s.name student_name,s.admission_no
        FROM hostel_fee_payments hp JOIN students s ON s.id=hp.student_id
        WHERE hp.session_id=? ORDER BY hp.id DESC LIMIT 50""",(sid,)).fetchall() if sid else []
    students=c.execute("""SELECT id,name,admission_no,class_name FROM students
        WHERE status='Active' ORDER BY name""").fetchall()
    c.close()
    total_collected=sum(float(p["amount"] or 0) for p in payments)
    return render_template("hostel.html",active_session=sess,admissions=admissions,structures=structures,
                           payments=payments,students=students,total_collected=total_collected)

@app.route("/hostel/admission/save",methods=["POST"])
def hostel_admission_save():
    if "user_id" not in session: return redirect(url_for("login"))
    sess=active_session()
    if sess:
        c=db()
        c.execute("""INSERT INTO hostel_admissions
          (student_id,session_id,hostel_name,room_no,bed_no,admission_date,guardian_name,guardian_phone,status,remarks)
          VALUES(?,?,?,?,?,?,?,?,?,?)""",
          (int(request.form["student_id"]),sess["id"],request.form["hostel_name"].strip(),
           request.form.get("room_no","").strip(),request.form.get("bed_no","").strip(),
           request.form["admission_date"],request.form.get("guardian_name","").strip(),
           request.form.get("guardian_phone","").strip(),request.form.get("status","Active"),
           request.form.get("remarks","").strip()))
        c.commit(); c.close()
    return redirect(url_for("hostel"))

@app.route("/hostel/admission/status/<int:admission_id>",methods=["POST"])
def hostel_admission_status(admission_id):
    if "user_id" not in session: return redirect(url_for("login"))
    c=db()
    status=request.form.get("status","Active")
    c.execute("UPDATE hostel_admissions SET status=? WHERE id=?",(status,admission_id))
    c.commit(); c.close()
    return redirect(url_for("hostel"))

@app.route("/hostel/fee/save",methods=["POST"])
def hostel_fee_save():
    if "user_id" not in session: return redirect(url_for("login"))
    sess=active_session()
    if sess:
        c=db()
        c.execute("""INSERT INTO hostel_fee_structures
          (session_id,hostel_name,fee_name,amount,frequency,class_name,active)
          VALUES(?,?,?,?,?,?,1)""",
          (sess["id"],request.form["hostel_name"].strip(),request.form["fee_name"].strip(),
           float(request.form["amount"] or 0),request.form.get("frequency","Monthly"),
           request.form.get("class_name","").strip()))
        c.commit(); c.close()
    return redirect(url_for("hostel"))

@app.route("/hostel/fee/toggle/<int:fee_id>",methods=["POST"])
def hostel_fee_toggle(fee_id):
    if "user_id" not in session: return redirect(url_for("login"))
    c=db(); c.execute("UPDATE hostel_fee_structures SET active=CASE WHEN active=1 THEN 0 ELSE 1 END WHERE id=?",(fee_id,)); c.commit(); c.close()
    return redirect(url_for("hostel"))

@app.route("/hostel/payment/save",methods=["POST"])
def hostel_payment_save():
    if "user_id" not in session: return redirect(url_for("login"))
    sess=active_session()
    if sess:
        c=db()
        student_id=int(request.form["student_id"])
        admission=c.execute("""SELECT id FROM hostel_admissions
          WHERE student_id=? AND session_id=? AND status='Active' ORDER BY id DESC LIMIT 1""",
          (student_id,sess["id"])).fetchone()
        if admission:
            count=c.execute("SELECT COUNT(*) n FROM hostel_fee_payments WHERE session_id=?",(sess["id"],)).fetchone()["n"]+1
            receipt=f"BES/HOSTEL/{sess['year']}/{count:04d}"
            try:
                c.execute("""INSERT INTO hostel_fee_payments
                  (admission_id,student_id,session_id,receipt_no,payment_date,fee_name,amount,payment_mode,reference_no,remarks)
                  VALUES(?,?,?,?,?,?,?,?,?,?)""",
                  (admission["id"],student_id,sess["id"],receipt,request.form["payment_date"],
                   request.form["fee_name"].strip(),float(request.form["amount"] or 0),
                   request.form.get("payment_mode","Cash"),request.form.get("reference_no","").strip(),
                   request.form.get("remarks","").strip()))
                c.commit()
            except Exception:
                pass
        c.close()
    return redirect(url_for("hostel"))

@app.route("/hostel/payment/receipt/<int:payment_id>")
def hostel_payment_receipt(payment_id):
    if "user_id" not in session: return redirect(url_for("login"))
    c=db()
    p=c.execute("""SELECT hp.*,s.name student_name,s.admission_no,s.class_name,
      ha.hostel_name,ha.room_no,ha.bed_no FROM hostel_fee_payments hp
      JOIN students s ON s.id=hp.student_id JOIN hostel_admissions ha ON ha.id=hp.admission_id
      WHERE hp.id=?""",(payment_id,)).fetchone()
    c.close()
    return render_template("hostel_receipt.html",payment=p)

if __name__=="__main__":
    port=int(os.environ.get("PORT","5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
