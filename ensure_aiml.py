import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
uri = os.getenv('MONGO_URI')
client = MongoClient(uri)
db_name = uri.split('/')[-1].split('?')[0] if '/' in uri else 'attendance_db'
if not db_name: db_name = 'attendance_db'
db = client[db_name]

print(f"Checking AIM records in {db_name}...")
s_count = db['students'].count_documents({'branch': 'AIM'})
a_count = db['attendance'].count_documents({'branch': 'AIM'})
print(f"Students with branch 'AIM': {s_count}")
print(f"Attendance with branch 'AIM': {a_count}")

if s_count > 0:
    print("Fixing students...")
    db['students'].update_many({'branch': 'AIM'}, {'$set': {'branch': 'AIML'}})
if a_count > 0:
    print("Fixing attendance...")
    db['attendance'].update_many({'branch': 'AIM'}, {'$set': {'branch': 'AIML'}})

print("Checking records with branch 'AIML'...")
s_aiml_count = db['students'].count_documents({'branch': 'AIML'})
a_aiml_count = db['attendance'].count_documents({'branch': 'AIML'})
print(f"Students with branch 'AIML': {s_aiml_count}")
print(f"Attendance with branch 'AIML': {a_aiml_count}")
