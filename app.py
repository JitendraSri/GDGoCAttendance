import os
import re
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from flask_socketio import SocketIO, emit
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import io
import pandas as pd
import logging
from logging.handlers import RotatingFileHandler
import html

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
handler = RotatingFileHandler('app.log', maxBytes=1000000, backupCount=3)
formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
)
handler.setFormatter(formatter)
logger.addHandler(handler)

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default_secret')
MONGO_URI = os.getenv('MONGO_URI')
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'GDGADMIN')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'DEPLOYX@2025')

# Connect to MongoDB with connection pooling
client = MongoClient(MONGO_URI, maxPoolSize=100, retryWrites=True)
try:
    db = client.get_database()
except:
    db = client['attendance_db']
students_col = db['students']
attendance_col = db['attendance']
events_col = db['events']
admins_col = db['admins']

# Initialize SocketIO with better concurrency settings
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

from functools import wraps
def requires_super_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in') or session.get('username') != 'GDGADMIN':
            return jsonify({'error': 'Unauthorized: Only GDGADMIN can perform this action'}), 403
        return f(*args, **kwargs)
    return decorated

@app.errorhandler(Exception)
def handle_exception(e):
    # Log the error with traceback
    import traceback
    logger.error(f"Unhandled Exception: {str(e)}\n{traceback.format_exc()}")
    
    # Return JSON for API routes
    if request.path.startswith('/api/'):
        return jsonify({
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Please try again later."
        }), 500
    # Return a basic error message for others
    return render_template('error.html', error=str(e)), 500

@app.errorhandler(404)
def handle_404(e):
    logger.warning(f"404 Not Found: {request.path} [Referer: {request.headers.get('Referer')}]")
    return render_template('error.html', error="Page Not Found"), 404

@app.errorhandler(500)
def handle_500(e):
    import traceback
    logger.error(f"500 Internal Error on {request.path}: {str(e)}\n{traceback.format_exc()}")
    return render_template('error.html', error="Internal Server Error"), 500

# Branch Mapping
BRANCH_MAP = {
    '01': 'CIVIL',
    '02': 'EEE',
    '03': 'MECH',
    '04': 'ECE',
    '14': 'ECT',
    '43': 'CAI',
    '61': 'AIML',
    '44': 'CSD',
    '05': 'CSE',
    '06': 'CST'
}

def normalize_branch(branch):
    if not branch:
        return branch
    b = str(branch).strip().upper()
    if b in ('AIM', 'AIML'):
        return 'AIML'
    return b

def clean_roll_number(roll):
    if not roll:
        return ""
    s = str(roll).strip().upper()
    if s.endswith('.0'):
        s = s[:-2]
    return s

def detect_branch(roll_number):
    roll_number = clean_roll_number(roll_number)
    if not roll_number or len(roll_number) < 8:
        return 'UNKNOWN'
    code = roll_number[6:8]
    return BRANCH_MAP.get(code, 'UNKNOWN')

def get_today_str():
    return datetime.now().strftime('%Y-%m-%d')

@app.route('/')
def index():
    if 'logged_in' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            return render_template('login.html', error="Please enter both username and password")
            
        username = username.strip()
        password = password.strip()
        
        # Priority: Check database for admins
        try:
            admin = admins_col.find_one({'username': username, 'password': password})
            if admin:
                session['logged_in'] = True
                session['admin_id'] = str(admin['_id'])
                session['username'] = username
                return redirect(url_for('dashboard'))
        except Exception as e:
            print(f"Login Database Error: {e}")
            return render_template('login.html', error="Database connection error. Please try again later.")
                
        return render_template('login.html', error="Invalid Credentials")
    return render_template('login.html')

@app.route('/api/admins', methods=['GET', 'POST'])
@requires_super_admin
def admins_api():
    if request.method == 'GET':
        admins = list(admins_col.find({}, {'password': 0})) # Don't send passwords
        for a in admins:
            a['_id'] = str(a['_id'])
        return jsonify(admins)
        
    if request.method == 'POST':
        data = request.json
        username = data.get('username')
        password = data.get('password')
        if not username or not password:
            return jsonify({'error': 'Username and Password required'}), 400
            
        if admins_col.find_one({'username': username}):
            return jsonify({'error': 'Username already exists'}), 400
            
        admins_col.insert_one({'username': username, 'password': password})
        return jsonify({'status': 'SUCCESS'})

@app.route('/api/admins/<admin_id>', methods=['DELETE'])
@requires_super_admin
def delete_admin_api(admin_id):
    # Prevet self-deletion
    if session.get('admin_id') == admin_id:
        return jsonify({'error': 'You cannot delete yourself'}), 400
        
    # Prevent deleting the core GDGADMIN via API if possible
    admin_to_del = admins_col.find_one({'_id': ObjectId(admin_id)})
    if admin_to_del and admin_to_del.get('username') == 'GDGADMIN':
        return jsonify({'error': 'GDGADMIN cannot be deleted'}), 400
        
    res = admins_col.delete_one({'_id': ObjectId(admin_id)})
    if res.deleted_count > 0:
        return jsonify({'status': 'SUCCESS'})
    return jsonify({'error': 'Admin not found'}), 404

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('dashboard.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/api/mark_attendance', methods=['POST'])
def mark_attendance_api():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    roll_number = clean_roll_number(data.get('roll_number'))
    event_id = data.get('event_id')
    
    if not roll_number or not event_id:
        return jsonify({'error': 'Roll number and Event ID required'}), 400
    
    # Validation logic
    if len(roll_number) < 8:
         return jsonify({'error': 'Roll Number too short'}), 400
         
    branch = normalize_branch(detect_branch(roll_number))
    branch = normalize_branch(branch)
    today = get_today_str()

    try:
        # Check for duplicate in this event
        existing = attendance_col.find_one({'rollNumber': roll_number, 'eventId': event_id})
        if existing:
            return jsonify({'error': 'Duplicate attendance', 'already_marked': True}), 409

        # Check existence in students collection for this event
        student = students_col.find_one({'rollNumber': roll_number, 'eventId': event_id})
        
        if not student:
            # Not found -> prompt to add
            return jsonify({'status': 'NOT_FOUND', 'roll_number': roll_number}), 404
        
        # Mark attendance
        attendance_record = {
            'rollNumber': roll_number,
            'name': student.get('name', 'Unknown'),
            'branch': normalize_branch(student.get('branch', branch)),
            'date': today,
            'eventId': event_id,
            'timestamp': datetime.now()
        }
        attendance_col.insert_one(attendance_record)
        
        # Emit update
        emit_counts(event_id)
        
        return jsonify({'status': 'SUCCESS', 'name': student.get('name'), 'branch': student.get('branch')})
    except Exception as e:
        logger.error(f"Error in mark_attendance_api for {roll_number}: {e}")
        return jsonify({'error': 'Internal Server Error', 'details': "Could not record attendance"}), 500

@app.route('/api/events', methods=['GET', 'POST'])
def events_api():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
        
    if request.method == 'GET':
        events = list(events_col.find().sort('created_at', -1))
        for e in events:
            e['_id'] = str(e['_id'])
        return jsonify(events)
        
    if request.method == 'POST':
        # Check for super admin
        if session.get('username') != 'GDGADMIN':
            return jsonify({'error': 'Only GDGADMIN can create events'}), 403
            
        data = request.json
        name = data.get('name')
        if not name:
            return jsonify({'error': 'Event name required'}), 400
            
        event = {
            'name': name,
            'created_at': datetime.now()
        }
        res = events_col.insert_one(event)
        return jsonify({'status': 'SUCCESS', 'event_id': str(res.inserted_id)})

@app.route('/api/events/<event_id>', methods=['DELETE'])
@requires_super_admin
def delete_event_api(event_id):
    # Validate event id early to avoid ObjectId errors
    if not ObjectId.is_valid(event_id):
        return jsonify({'error': 'Invalid Event ID'}), 400
    try:
        # Cascade delete
        # 1. Delete Students
        students_col.delete_many({'eventId': event_id})
        # 2. Delete Attendance
        attendance_col.delete_many({'eventId': event_id})
        # 3. Delete Event
        res = events_col.delete_one({'_id': ObjectId(event_id)})
        
        if res.deleted_count > 0:
            return jsonify({'status': 'SUCCESS', 'message': f'Event {event_id} and all associated data deleted.'})
        else:
            return jsonify({'error': 'Event not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload_students', methods=['POST'])
@requires_super_admin
def upload_students():
    # File handling logic...
        
    event_id = request.form.get('event_id')
    if not event_id:
        return jsonify({'error': 'No event selected'}), 400
        
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        try:
            df = pd.read_excel(file)
            # Normalize column names
            df.columns = [str(c).strip().title() for c in df.columns]
            
            required = ['Roll Number', 'Name']
            if not all(c in df.columns for c in required):
                return jsonify({'error': f'Excel must contain: {", ".join(required)}'}), 400
                
            student_records = []
            seen_rolls = set()
            duplicates_count = 0
            
            for _, row in df.iterrows():
                roll_raw = row.get('Roll Number')
                name_raw = row.get('Name')
                
                if pd.isna(roll_raw) or pd.isna(name_raw):
                    continue
                    
                roll = clean_roll_number(roll_raw)
                
                if not roll:
                    continue
                    
                if roll in seen_rolls:
                    duplicates_count += 1
                    continue
                    
                seen_rolls.add(roll)
                name = str(name_raw).strip()
                raw_branch = row.get('Branch')
                if pd.isna(raw_branch) or raw_branch is None:
                    branch = normalize_branch(detect_branch(roll))
                else:
                    branch = normalize_branch(str(raw_branch).strip().upper())
                
                student_records.append({
                    'rollNumber': roll,
                    'name': name,
                    'branch': branch,
                    'eventId': event_id
                })
            
            if student_records:
                for s in student_records:
                    students_col.update_one(
                        {'rollNumber': s['rollNumber'], 'eventId': event_id},
                        {'$set': s},
                        upsert=True
                    )
                    
            msg = f"Successfully registered {len(student_records)} students."
            if duplicates_count > 0:
                msg += f" (Note: {duplicates_count} duplicate roll numbers were ignored in Excel)"
                
            return jsonify({'status': 'SUCCESS', 'count': len(student_records), 'message': msg})
        except Exception as e:
            return jsonify({'error': f'Parsing error: {str(e)}'}), 500
            
    return jsonify({'error': 'Invalid file format'}), 400

@app.route('/api/add_student', methods=['POST'])
def add_student_api():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    roll_number = clean_roll_number(data.get('roll_number'))
    name = data.get('name')
    event_id = data.get('event_id')
    
    if not roll_number or not name or not event_id:
        return jsonify({'error': 'Roll number, Name and Event ID required'}), 400
    try:
        # Insert to students with normalization
        branch = normalize_branch(detect_branch(roll_number))
        students_col.update_one(
            {'rollNumber': roll_number, 'eventId': event_id},
            {'$set': {'name': name, 'branch': branch}},
            upsert=True
        )
        
        # Automatically mark attendance
        today = get_today_str()
        attendance_record = {
            'rollNumber': roll_number,
            'name': name,
            'branch': normalize_branch(branch),
            'date': today,
            'eventId': event_id,
            'timestamp': datetime.now()
        }
        attendance_col.insert_one(attendance_record)
        emit_counts(event_id)
        return jsonify({'status': 'SUCCESS', 'message': 'Student added and attendance marked'})
    except Exception as e:
        logger.error(f"Error in add_student_api for {roll_number}: {e}")
        return jsonify({'error': 'Internal Server Error', 'details': "Could not add student"}), 500

@app.route('/api/delete_student', methods=['POST'])
def delete_student_api():
    try:
        if not session.get('logged_in'):
            return jsonify({'error': 'Unauthorized'}), 401
    
        data = request.json
        roll_number = clean_roll_number(data.get('roll_number'))
        event_id = data.get('event_id')
        
        if not roll_number or not event_id:
            return jsonify({'error': 'Roll number and Event ID required'}), 400
        
        # Delete from students
        res_s = students_col.delete_one({'rollNumber': roll_number, 'eventId': event_id})
        # Delete from attendance
        res_a = attendance_col.delete_many({'rollNumber': roll_number, 'eventId': event_id})
        
        if res_s.deleted_count > 0 or res_a.deleted_count > 0:
            emit_counts(event_id)
            return jsonify({'status': 'SUCCESS', 'message': f'Deleted {roll_number}'})
        else:
            return jsonify({'status': 'NOT_FOUND', 'message': f'Roll number {roll_number} not found in this event'}), 404
            
    except Exception as e:
        return jsonify({'error': f'Internal Server Error: {str(e)}'}), 500

@app.route('/api/attendees')
def get_attendees():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    event_id = request.args.get('event_id')
    branch = request.args.get('branch')
    
    if not event_id:
        return jsonify({'error': 'Event ID required'}), 400
        
    query = {'eventId': event_id}
    if branch and branch != 'ALL':
        query['branch'] = normalize_branch(branch)
        
    records = list(attendance_col.find(query))
    result = []
    for idx, r in enumerate(records, 1):
        result.append({
            's_no': idx,
            'rollResult': r.get('rollNumber'),
            'name': r.get('name'),
            'branch': r.get('branch')
        })
    return jsonify(result)

@app.route('/api/stats')
def get_stats():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    event_id = request.args.get('event_id')
    if not event_id:
        return jsonify({'total': 0, 'branch_counts': {}, 'total_students': 0})
        
    total = attendance_col.count_documents({'eventId': event_id})
    pipeline = [
        {'$match': {'eventId': event_id}},
        {'$group': {'_id': '$branch', 'count': {'$sum': 1}}}
    ]
    branch_counts = {item['_id']: item['count'] for item in attendance_col.aggregate(pipeline)}
    for dept in BRANCH_MAP.values():
        if dept not in branch_counts:
            branch_counts[dept] = 0
            
    total_students = students_col.count_documents({'eventId': event_id})
    return jsonify({'total': total, 'branch_counts': branch_counts, 'total_students': total_students})

@socketio.on('join_event')
def on_join(data):
    event_id = data.get('event_id')
    if event_id:
        from flask_socketio import join_room
        join_room(event_id)
        # print(f"Client joined room: {event_id}")

def emit_counts(event_id):
    try:
        # Use aggregation for efficiency
        pipeline = [
            {'$match': {'eventId': event_id}},
            {'$facet': {
                'total': [{'$count': 'count'}],
                'by_branch': [
                    {'$group': {'_id': '$branch', 'count': {'$sum': 1}}}
                ]
            }}
        ]
        results = list(attendance_col.aggregate(pipeline))[0]
        
        total = results['total'][0]['count'] if results['total'] else 0
        branch_counts = {item['_id']: item['count'] for item in results['by_branch']}
        
        # Ensure all branches are present
        for dept in BRANCH_MAP.values():
            if dept not in branch_counts:
                branch_counts[dept] = 0
                
        total_students = students_col.count_documents({'eventId': event_id})
        
        socketio.emit('update_counts', {
            'total': total, 
            'branch_counts': branch_counts,
            'total_students': total_students,
            'event_id': event_id
        }, to=event_id)
    except Exception as e:
        logger.error(f"ERROR: emit_counts failed for event {event_id}: {e}")


@app.route('/download_pdf/<event_id>/<department>')
@requires_super_admin
def download_pdf(event_id, department):
    if not session.get('logged_in'):
         return redirect(url_for('login'))
         
    department = normalize_branch(department.upper())
    if not ObjectId.is_valid(event_id):
        return "Invalid Event", 400
    event = events_col.find_one({'_id': ObjectId(event_id)})
    if not event:
        return "Invalid Event", 400
        
    query = {'eventId': event_id}
    if department != 'ALL':
        query['branch'] = department
        
    records = list(attendance_col.find(query).sort('timestamp', 1))
    
    try:
        # Generate PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()
        
        # Title
        title_style = styles['Title']
        title_style.leading = 24
        
        # Escape event name for Paragraph
        safe_event_name = html.escape(event['name'])
        # Use proper self-closing tags and ensure no accidental content
        header_text = f"<para align='center'>ATTENDANCE FOR THE<br/>{safe_event_name}<br/>INITIATED BY<br/>SRI VASAVI ENGINEERING COLLEGE<br/>(AUTONOMOUS)</para>"
        
        logger.info(f"Generating PDF for event: {event['name']} ({event_id}), dept: {department}")
        elements.append(Paragraph(header_text, title_style))
        elements.append(Spacer(1, 12))
        
        safe_dept = html.escape('All Branches' if department == 'ALL' else department)
        elements.append(Paragraph(f"Category: {safe_dept}", styles['Heading2']))
        elements.append(Paragraph(f"Date: {get_today_str()}", styles['Normal']))
        elements.append(Paragraph(f"Total Students: {len(records)}", styles['Normal']))
        elements.append(Spacer(1, 12))
       
        # Table Data
        data = [['S.No', 'Roll Number', 'Name', 'Branch' if department == 'ALL' else '']]
        if department != 'ALL':
            data = [['S.No', 'Roll Number', 'Name']]
            
        for idx, record in enumerate(records, 1):
            if department == 'ALL':
                data.append([str(idx), record.get('rollNumber', ''), record.get('name', ''), record.get('branch', '')])
            else:
                data.append([str(idx), record.get('rollNumber', ''), record.get('name', '')])
            
        # Set column widths
        col_widths = [50, 150, 300]
        if department == 'ALL':
            col_widths = [40, 120, 240, 100]
            
        table = Table(data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(table)
        
        doc.build(elements)
        buffer.seek(0)
        
        today_str = get_today_str()
        filename = f"Attendance_{department}_{today_str}.pdf"
        return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')
    except Exception as e:
        import traceback
        logger.error(f"PDF Generation Error for event {event_id}: {str(e)}\n{traceback.format_exc()}")
        return render_template('error.html', error=f"PDF Error: {str(e)}"), 500

@app.route('/download_full_excel/<event_id>')
@requires_super_admin
def download_full_excel(event_id):
    if not session.get('logged_in'):
         return redirect(url_for('login'))
    
    if not ObjectId.is_valid(event_id):
        return "Invalid Event", 400
    event = events_col.find_one({'_id': ObjectId(event_id)})
    if not event:
        return "Invalid Event", 400
        
    attendance_records = list(attendance_col.find({'eventId': event_id}, {'_id': 0}))
    
    data = []
    for r in attendance_records:
        data.append({
            'Roll Number': r.get('rollNumber', 'UNKNOWN'),
            'Name': r.get('name', ''),
            'Branch': r.get('branch', ''),
            'Time': r.get('timestamp', '').strftime('%H:%M:%S') if isinstance(r.get('timestamp'), datetime) else str(r.get('time', ''))
        })
        
    df = pd.DataFrame(data)
    
    # Output to BytesIO
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Present Students')
        
    output.seek(0)
    
    today_str = get_today_str()
    return send_file(output, as_attachment=True, download_name=f"Full_Student_Data_{today_str}.xlsx", mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

if __name__ == '__main__':
    # Ensure indexes
    try:
        # Try to ensure indexes without dropping if they exist
        # This is safer for production and avoids downtime
        attendance_col.create_index([('rollNumber', 1), ('eventId', 1)], unique=True)
        attendance_col.create_index('eventId')
        attendance_col.create_index('branch')
        students_col.create_index([('rollNumber', 1), ('eventId', 1)], unique=True)
        print("Indexes ensured.")
        
        # Bootstrap required accounts
        # GDGADMIN (Full access)
        admins_col.update_one(
            {'username': 'GDGADMIN'},
            {'$set': {'username': 'GDGADMIN', 'password': 'COREADMIN#3'}},
            upsert=True
        )
        # Batch add GDGMEMBER1 to GDGMEMBER40
        print("Ensuring batch member accounts (1-40)...")
        from pymongo import UpdateOne
        bulk_ops = []
        for i in range(1, 41):
            u = f"GDGMEMBER{i}"
            p = f"COREMEMBER#{i}"
            bulk_ops.append(UpdateOne(
                {'username': u},
                {'$set': {'username': u, 'password': p}},
                upsert=True
            ))
        
        if bulk_ops:
            res = admins_col.bulk_write(bulk_ops)
            print(f"Batch admins ensured: {res.upserted_count + res.matched_count} total.")
        # Merging AIM and AIML into AIML (Normalization)
        print("Ensuring branch normalization (AIM -> AIML)...")
        res1 = students_col.update_many({'branch': 'AIM'}, {'$set': {'branch': 'AIML'}})
        res2 = attendance_col.update_many({'branch': 'AIM'}, {'$set': {'branch': 'AIML'}})
        if res1.modified_count > 0 or res2.modified_count > 0:
            print(f"Normalized {res1.modified_count} students and {res2.modified_count} attendance records.")
        
        print("Default Admins ensured.")
        
        # DEBUG: Print counts
        s_count = students_col.count_documents({})
        a_count = attendance_col.count_documents({})
        today_str = datetime.now().strftime('%Y-%m-%d')
        a_today = attendance_col.count_documents({'date': today_str})
        print(f"DEBUG: Total Students in DB: {s_count}")
        print(f"DEBUG: Total Attendance (All Time): {a_count}")
        print(f"DEBUG: Attendance Today ({today_str}): {a_today}")
        
    except Exception as e:
        print(f"Index creation failed: {e}")
        
    port = int(os.environ.get("PORT", 5000))
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        allow_unsafe_werkzeug=True
    )
