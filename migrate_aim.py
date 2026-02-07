import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
uri = os.getenv('MONGO_URI')
client = MongoClient(uri)
db_name = uri.split('/')[-1].split('?')[0] if '/' in uri else 'attendance_db'
if not db_name: db_name = 'attendance_db'
db = client[db_name]

students_col = db['students']
attendance_col = db['attendance']

print("Updating students collection...")
res1 = students_col.update_many({'branch': 'AIM'}, {'$set': {'branch': 'AIML'}})
print(f"Modified {res1.modified_count} records in students.")

print("Updating attendance collection...")
res2 = attendance_col.update_many({'branch': 'AIM'}, {'$set': {'branch': 'AIML'}})
print(f"Modified {res2.modified_count} records in attendance.")

print("Merging complete.")
