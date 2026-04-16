#!/bin/bash
# FRIDAY Runner Script - called by launchd

export PATH="/usr/local/opt/python@3.14/libexec/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONPATH="/usr/local/lib/python3.14/site-packages"

cd /Users/fs/Documents/FRIDAY

echo "[$(date)] Starting FRIDAY..." >> /Users/fs/Documents/FRIDAY/logs/friday.log

/usr/local/bin/python3 /Users/fs/Documents/FRIDAY/friday.py >> /Users/fs/Documents/FRIDAY/logs/friday.log 2>&1
