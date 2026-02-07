import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
uri = os.getenv('MONGO_URI')
client = MongoClient(uri)
# Try to get the database name from the URI, otherwise fallback
db_name = uri.split('/')[-1].split('?')[0] if '/' in uri else 'attendance_db'
if not db_name: db_name = 'attendance_db'
db = client[db_name]

students_col = db['students']
attendance_col = db['attendance']

print(f"Using database: {db_name}")
print("Students Branch Distinct:", students_col.distinct('branch'))
print("Attendance Branch Distinct:", attendance_col.distinct('branch'))
print("Students AIM count:", students_col.count_documents({'branch': 'AIM'}))
print("Students AIML count:", students_col.count_documents({'branch': 'AIML'}))
print("Attendance AIM count:", attendance_col.count_documents({'branch': 'AIM'}))
print("Attendance AIML count:", attendance_col.count_documents({'branch': 'AIML'}))
