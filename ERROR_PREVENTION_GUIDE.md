# Zero-Error & High Scalability Maintenance Guide

This document outlines the safeguards implemented to prevent **Internal Server Errors (500)** and how to maintain the system for 2000+ scanning operations.

## 1. Implemented Safeguards

### Global Exception Handling
In `app.py`, a global error handler catches any crash that would normally show a "White Screen of Death":
- **Web Interface**: Shows a premium `error.html` page instead of a raw traceback.
- **REST API**: Returns a clean JSON response: `{"error": "Internal Server Error", "message": "..."}`.
- **Logging**: Every error is automatically logged to `app.log` with a full traceback for debugging.

### Database Stability
- **Connection Pooling**: The system is tuned to handle 100 simultaneous connections to MongoDB.
- **Automatic Retries**: If the database is momentarily busy, the system automatically retries the operation.
- **Indexes**: Critical fields are indexed. This prevents the database from slowing down as the number of scans grows to 2000+.

### Concurrency Support
- **Gunicorn + Eventlet**: The production server setup allows handling hundreds of active scanners simultaneously by using "green threads" (non-blocking I/O).

## 2. Best Practices to Prevent Errors

### ✅ DOs:
- **Use Production Command**: Always run the app using `gunicorn -c gunicorn_config.py app:app`. Do NOT use `python app.py` for large events.
- **Pre-Upload Students**: Ensure the Excel sheet is uploaded *before* scanning starts to avoid "Student Not Found" errors during peak time.
- **Monitor app.log**: If users report issues, check the `app.log` file in the project directory. It will tell you exactly which line of code failed.

### ❌ DON'Ts:
- **Don't use weak WiFi**: A stable internet connection is required for the scanners to communicate with the MongoDB Atlas cloud.
- **Don't Delete Events Mid-Scan**: Deleting an event while 40 people are scanning for it will cause those scans to fail (returning 404).

## 3. Scalability Checklist for Large Events
* [ ] Verify `MONGO_URI` is correctly set in `.env`.
* [ ] Ensure all 40 member accounts are present in the `admins` collection (happens automatically at startup).
* [ ] Test the scanning speed with 5-10 concurrent devices before the full crowd arrives.

---
**Maintaining this system involves keeping the `app.py` logic intact and ensuring the MongoDB Atlas tier has enough "connections" available for your event size.**
