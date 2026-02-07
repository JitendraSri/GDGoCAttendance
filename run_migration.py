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

print("Starting migration...")
res1 = students_col.update_many({'branch': 'AIM'}, {'$set': {'branch': 'AIML'}})
res2 = attendance_col.update_many({'branch': 'AIM'}, {'$set': {'branch': 'AIML'}})
print(f"Modified {res1.modified_count} students and {res2.modified_count} attendance records.")

# Also ensure MECH is unified if there was any discrepancy (though it seems fine)
# But let's check for lowercase mech or something
res3 = students_col.update_many({'branch': {'$in': ['mech', 'Mechanical']}}, {'$set': {'branch': 'MECH'}})
res4 = attendance_col.update_many({'branch': {'$in': ['mech', 'Mechanical']}}, {'$set': {'branch': 'MECH'}})
print(f"Standardized {res3.modified_count + res4.modified_count} MECH records.")

print("Migration complete.")
