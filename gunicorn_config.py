import os

# Gunicorn configuration file
# See: https://docs.gunicorn.org/en/stable/configure.html

# Bind to the port provided by environment or default to 5000
bind = "0.0.0.0:" + os.getenv("PORT", "5000")

# Worker type - Eventlet is recommended for SocketIO/Flask-SocketIO
worker_class = "eventlet"

# Number of workers - For Eventlet, 1 is usually enough per container
# as it handles concurrency via green threads.
workers = 1

# Timeout for workers
timeout = 120

# Log settings
accesslog = "-"
errorlog = "-"
loglevel = "info"
