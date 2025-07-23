#!/usr/bin/env python3
# ↑ This lets you run the script directly from the shell like: ./pomocli.py

import os            # Used for handling file paths (like expanding ~ to /home/youruser)
import time          # Used for timers and countdown delays
from datetime import datetime  # For timestamping logs

# === Configurable Constants ===
WORK_DURATION = 25 * 60         # 25 minutes in seconds
BREAK_DURATION = 5 * 60         # 5 minutes in seconds
LOG_FILE = os.path.expanduser("~/pomocli_log.txt")  # File path for session logs

# === Function: Make Terminal Bell Sound ===
def ring_bell():
    # The "\a" character triggers the terminal bell (if enabled in your terminal settings)
    print("\a", end="", flush=True)

# === Function: Write a log entry to the log file ===
def log_session(task_description, state):
    # `state` should be either "START" or "END"
    with open(LOG_FILE, "a") as f:
        # Log format: 2025-07-22T20:45 - START: Write newsletter
        timestamp = datetime.now().strftime("%Y-%m-%d T=%H:%M")
        f.write(f"{timestamp} - {state}: {task_description}\n")

# === Function: Run a countdown timer and show time remaining with progress bar ===
def start_timer(duration, label):
    # Print initial message
    print(f"Starting {label} timer for {duration // 60} minutes...")

    # Timer Below
    try:
        for elapsed in range(duration):
            remaining = duration - elapsed
            mins, secs = divmod(remaining, 60)

            # Progress bar setup
            bar_width = 20
            percent_complete = elapsed / duration
            filled_length = int(bar_width * percent_complete)
            bar = '█' * filled_length + ' ' * (bar_width - filled_length)

            # Print status
            print(f"{label} Time: {mins:02}:{secs:02} [{bar}] {int(percent_complete * 100)}%", end='\r')
            time.sleep(1)
        # Alert on timer completion
        print()
        ring_bell()
        print(f"{label} session complete!")

    except KeyboardInterrupt:
        # If the user hits Ctrl+C during the countdown
        print("\nTimer interrupted. Session aborted.")

# === Main Program Logic ===
def main():
    try:
        # Prompt user for task they plan to work on
        task = input("🍅 What will you work on this session? ")

        # Log the start of the work session
        log_session(task, "START")

        # Start 25-minute work timer
        start_timer(WORK_DURATION, "Work")

        # Log the end of the work session
        log_session(task, "END")

        # Prompt user to begin break
        input("☕️ Press Enter to start your 5-minute break...")

        # Start 5-minute break timer
        start_timer(BREAK_DURATION, "Break")

    except KeyboardInterrupt:
        # Catch Ctrl+C from user to avoid a nasty traceback
        print("\nSession cancelled.")

# === Run the script ===
if __name__ == "__main__":
    main()
