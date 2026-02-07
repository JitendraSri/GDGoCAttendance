import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv('MONGO_URI')
client = MongoClient(MONGO_URI)
try:
    db = client.get_database()
except:
    db = client['attendance_db']
students_col = db['students']
attendance_col = db['attendance']

print("Unique branches in students collection:")
print(students_col.distinct('branch'))

print("\nUnique branches in attendance collection:")
print(attendance_col.distinct('branch'))

print("\nRecords with branch 'AIM' in students:")
print(students_col.count_documents({'branch': 'AIM'}))

print("Records with branch 'AIML' in students:")
print(students_col.count_documents({'branch': 'AIML'}))

print("\nRecords with branch 'AIM' in attendance:")
print(attendance_col.count_documents({'branch': 'AIM'}))

print("Records with branch 'AIML' in attendance:")
print(attendance_col.count_documents({'branch': 'AIML'}))
