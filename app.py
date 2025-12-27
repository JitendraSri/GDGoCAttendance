import os
import re
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from flask_socketio import SocketIO, emit
from pymongo import MongoClient
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import io
import pandas as pd

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default_secret')
MONGO_URI = os.getenv('MONGO_URI')
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'GDGADMIN')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'DEPLOYX@2025')

# Connect to MongoDB
# Connect to MongoDB
client = MongoClient(MONGO_URI)
try:
    db = client.get_database()
except:
    db = client['attendance_db'] # Fallback if URI doesn't validly specify one
students_col = db['students']
attendance_col = db['attendance']

# Initialize SocketIO
socketio = SocketIO(app, async_mode='threading')

# Branch Mapping
BRANCH_MAP = {
    '04': 'ECE',
    '14': 'ECT',
    '43': 'CAI',
    '61': 'AIM',
    '44': 'CSD',
    '05': 'CSE',
    '06': 'CST'
}

def detect_branch(roll_number):
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
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Invalid Credentials")
    return render_template('login.html')

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
    roll_number = data.get('roll_number')
    if not roll_number:
        return jsonify({'error': 'Roll number required'}), 400

    roll_number = roll_number.upper().strip()
    
    print(f"DEBUG: Mark Attendance Request for {roll_number}")
    
    # Validation logic
    if len(roll_number) < 8:
         print("DEBUG: Invalid Length")
         return jsonify({'error': 'Invalid Roll Number format'}), 400
         
    branch = detect_branch(roll_number)
    today = get_today_str()

    # Check for duplicate
    existing = attendance_col.find_one({'rollNumber': roll_number, 'date': today})
    if existing:
        print("DEBUG: Duplicate Found")
        return jsonify({'error': 'Duplicate attendance', 'already_marked': True}), 409

    # Check existence in students collection
    student = students_col.find_one({'rollNumber': roll_number})
    
    if not student:
        print("DEBUG: Student NOT FOUND in students collection")
        # Not found -> prompt to add
        return jsonify({'status': 'NOT_FOUND', 'roll_number': roll_number}), 404
    
    # Mark attendance
    print(f"DEBUG: Found Student {student.get('name')}. Marking Present.")
    attendance_record = {
        'rollNumber': roll_number,
        'name': student.get('name', 'Unknown'),
        'branch': student.get('branch', branch),
        'date': today,
        'timestamp': datetime.now()
    }
    result = attendance_col.insert_one(attendance_record)
    print(f"DEBUG: Inserted Result ID: {result.inserted_id}")
    
    # Emit update
    emit_counts()
    
    return jsonify({'status': 'SUCCESS', 'name': student.get('name'), 'branch': student.get('branch')})

@app.route('/api/add_student', methods=['POST'])
def add_student_api():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    print(f"DEBUG: Add Student Request: {data}")
    roll_number = data.get('roll_number')
    name = data.get('name')
    
    if not roll_number or not name:
        return jsonify({'error': 'Roll number and Name required'}), 400
        
    roll_number = roll_number.upper().strip()
    branch = detect_branch(roll_number)
    
    # Insert to students
    res_s = students_col.update_one(
        {'rollNumber': roll_number},
        {'$set': {'name': name, 'branch': branch}},
        upsert=True
    )
    print(f"DEBUG: Update/Upsert Student. Matched: {res_s.matched_count}, Modified: {res_s.modified_count}, Upserted: {res_s.upserted_id}")
    
    # Automatically mark attendance
    today = get_today_str()
    existing = attendance_col.find_one({'rollNumber': roll_number, 'date': today})
    if not existing:
        attendance_record = {
            'rollNumber': roll_number,
            'name': name,
            'branch': branch,
            'date': today,
            'timestamp': datetime.now()
        }
        res_a = attendance_col.insert_one(attendance_record)
        print(f"DEBUG: Auto-Marked Attendance. ID: {res_a.inserted_id}")
        emit_counts()
        return jsonify({'status': 'SUCCESS', 'message': 'Student added and attendance marked'})
    else:
        print("DEBUG: Attendance already existed during Add Student.")
        return jsonify({'status': 'SUCCESS', 'message': 'Student added, attendance was already marked'})

@app.route('/api/delete_student', methods=['POST'])
def delete_student_api():
    try:
        if not session.get('logged_in'):
            return jsonify({'error': 'Unauthorized'}), 401
    
        data = request.json
        roll_number = data.get('roll_number')
        
        if not roll_number:
            return jsonify({'error': 'Roll number required'}), 400
            
        # Force string conversion to handle potential numbers
        roll_number = str(roll_number).upper().strip()
        
        print(f"DEBUG: Delete Request for '{roll_number}' (Len: {len(roll_number)})")
    
        # Check existence before delete for debugging
        ex_s = students_col.find_one({'rollNumber': roll_number})
        ex_a = attendance_col.find_one({'rollNumber': roll_number})
        print(f"DEBUG: Pre-check - Student: {ex_s['_id'] if ex_s else 'NONE'}, Attendance: {ex_a['_id'] if ex_a else 'NONE'}")
    
        # Delete from students
        res_s = students_col.delete_one({'rollNumber': roll_number})
        # Delete from attendance
        res_a = attendance_col.delete_many({'rollNumber': roll_number})
        
        print(f"DEBUG: Deleted Student: {res_s.deleted_count}, Attendance: {res_a.deleted_count}")
        
        if res_s.deleted_count > 0 or res_a.deleted_count > 0:
            emit_counts()
            return jsonify({'status': 'SUCCESS', 'message': f'Deleted {roll_number}. Student: {res_s.deleted_count}, Attendance: {res_a.deleted_count}'})
        else:
            return jsonify({'status': 'NOT_FOUND', 'message': f'Roll number {roll_number} not found'}), 404
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Internal Server Error: {str(e)}'}), 500

@app.route('/api/attendees')
def get_attendees():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    branch = request.args.get('branch')
    today = get_today_str()
    query = {'date': today}
    
    if branch and branch != 'ALL':
        query['branch'] = branch.upper()
        
    records = list(attendance_col.find(query))
    # Transform for frontend
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
    today = get_today_str()
    total = attendance_col.count_documents({'date': today})
    pipeline = [
        {'$match': {'date': today}},
        {'$group': {'_id': '$branch', 'count': {'$sum': 1}}}
    ]
    branch_counts = {item['_id']: item['count'] for item in attendance_col.aggregate(pipeline)}
    # Ensure all departments are in the map
    for dept in BRANCH_MAP.values():
        if dept not in branch_counts:
            branch_counts[dept] = 0
            
    total_students = students_col.count_documents({})
    return jsonify({'total': total, 'branch_counts': branch_counts, 'total_students': total_students})

def emit_counts():
    today = get_today_str()
    total = attendance_col.count_documents({'date': today})
    pipeline = [
        {'$match': {'date': today}},
        {'$group': {'_id': '$branch', 'count': {'$sum': 1}}}
    ]
    branch_counts = {item['_id']: item['count'] for item in attendance_col.aggregate(pipeline)}
     # Ensure all departments are in the map
    for dept in BRANCH_MAP.values():
        if dept not in branch_counts:
            branch_counts[dept] = 0
            
    total_students = students_col.count_documents({})
    try:
        socketio.emit('update_counts', {
            'total': total, 
            'branch_counts': branch_counts,
            'total_students': total_students
        })
    except Exception as e:
        print(f"ERROR: emit_counts failed: {e}")


@app.route('/download_pdf/<department>')
def download_pdf(department):
    if not session.get('logged_in'):
         return redirect(url_for('login'))
         
    department = department.upper()
    if department not in BRANCH_MAP.values():
        return "Invalid Department", 400
        
    today = get_today_str()
    records = list(attendance_col.find({'date': today, 'branch': department}))
    
    # Generate PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = styles['Title']
    title_style.leading = 24
    elements.append(Paragraph("ATTENDANCE FOR THE<br/>DEPLOYX Event BY GDGoC SVEC", title_style))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Department: {department}", styles['Heading2']))
    elements.append(Paragraph(f"Date: {today}", styles['Normal']))
    elements.append(Spacer(1, 12))
    
    # Table Data
    data = [['S.No', 'Roll Number', 'Name']]
    for idx, record in enumerate(records, 1):
        data.append([str(idx), record.get('rollNumber', ''), record.get('name', '')])
        
    # Set column widths to make table BIG (Total ~500pts)
    table = Table(data, colWidths=[50, 150, 300])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(table)
    
    doc.build(elements)
    buffer.seek(0)
    
    return send_file(buffer, as_attachment=True, download_name=f"Attendance_{department}_{today}.pdf", mimetype='application/pdf')

@app.route('/download_full_excel')
def download_full_excel():
    if not session.get('logged_in'):
         return redirect(url_for('login'))
    
    # Fetch only today's attendance records (Present students)
    today = get_today_str()
    attendance_records = list(attendance_col.find({'date': today}, {'_id': 0}))
    
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
    
    return send_file(output, as_attachment=True, download_name=f"Full_Student_Data_{today}.xlsx", mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

if __name__ == '__main__':
    # Ensure indexes
    try:
        attendance_col.create_index([('rollNumber', 1), ('date', 1)], unique=True)
        attendance_col.create_index('date')
        attendance_col.create_index('branch')
        print("Indexes ensured.")
        
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
        
    # Run server on 0.0.0.0 to allow mobile connections
    try:
        socketio.run(app, host='0.0.0.0', debug=True, use_reloader=False, port=5000)
    except Exception as e:
        print(f"Server Error: {e}")
