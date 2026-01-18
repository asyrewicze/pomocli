#!/usr/bin/env python3
"""
pomocli_curses.py
A curses-based Pomodoro CLI with:
- Start Pomodoro (task prompt -> work timer -> break timer)
- View previous pomodoros (from a text log file)
- Settings (adjust work/break durations; persisted in JSON)

Changes in this version:
- End-of-timer alert: beep + flash, 5 iterations
- Timer UI displays the current task text
"""

import curses
import json
import os
import time
from datetime import datetime
from typing import List, Optional

# Files
LOG_FILE = os.path.expanduser("~/pomocli_log.txt")
CONFIG_FILE = os.path.expanduser("~/.pomocli_config.json")

# Defaults (minutes)
DEFAULT_WORK_MIN = 25
DEFAULT_BREAK_MIN = 5


# -----------------------------
# Persistence
# -----------------------------
def load_config() -> dict:
    cfg = {"work_minutes": DEFAULT_WORK_MIN, "break_minutes": DEFAULT_BREAK_MIN}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                cfg["work_minutes"] = int(data.get("work_minutes", cfg["work_minutes"]))
                cfg["break_minutes"] = int(data.get("break_minutes", cfg["break_minutes"]))
    except FileNotFoundError:
        pass
    except Exception:
        pass

    cfg["work_minutes"] = max(1, min(cfg["work_minutes"], 180))
    cfg["break_minutes"] = max(1, min(cfg["break_minutes"], 60))
    return cfg


def save_config(cfg: dict) -> None:
    safe = {
        "work_minutes": int(cfg.get("work_minutes", DEFAULT_WORK_MIN)),
        "break_minutes": int(cfg.get("break_minutes", DEFAULT_BREAK_MIN)),
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(safe, f, indent=2)


# -----------------------------
# Logging
# -----------------------------
def log_session(task_description: str, state: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d T=%H:%M")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} - {state}: {task_description}\n")


def read_log_lines() -> List[str]:
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return [line.rstrip("\n") for line in f.readlines()]
    except FileNotFoundError:
        return []
    except Exception:
        return ["[Error reading log file]"]


# -----------------------------
# UI Helpers
# -----------------------------
def init_curses(stdscr) -> None:
    curses.curs_set(0)
    stdscr.nodelay(False)
    stdscr.keypad(True)
    curses.noecho()
    curses.cbreak()
    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)     # Title
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Highlight
        curses.init_pair(3, curses.COLOR_YELLOW, -1)   # Status
        curses.init_pair(4, curses.COLOR_GREEN, -1)    # Success


def center_text(stdscr, y: int, text: str, attr: int = 0) -> None:
    h, w = stdscr.getmaxyx()
    x = max(0, (w - len(text)) // 2)
    try:
        stdscr.addstr(y, x, text[: max(0, w - 1)], attr)
    except curses.error:
        pass


def draw_frame(stdscr, title: str = "") -> None:
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    try:
        stdscr.border()
    except curses.error:
        pass

    if title:
        attr = curses.color_pair(1) | curses.A_BOLD if curses.has_colors() else curses.A_BOLD
        header = f" {title} "
        x = max(1, (w - len(header)) // 2)
        try:
            stdscr.addstr(0, x, header[: max(0, w - 2)], attr)
        except curses.error:
            pass


def prompt_input(stdscr, title: str, prompt: str, initial: str = "") -> Optional[str]:
    draw_frame(stdscr, title)
    h, w = stdscr.getmaxyx()

    info = "ESC to cancel"
    attr_info = curses.color_pair(3) if curses.has_colors() else 0
    try:
        stdscr.addstr(2, 2, info[: w - 4], attr_info)
        stdscr.addstr(4, 2, prompt[: w - 4])
    except curses.error:
        pass

    curses.curs_set(1)
    curses.echo()

    y = 6
    x = 2
    buf = list(initial)
    while True:
        stdscr.move(y, x)
        try:
            stdscr.clrtoeol()
            stdscr.addstr(y, x, "".join(buf)[: max(0, w - 4)])
        except curses.error:
            pass
        stdscr.refresh()

        ch = stdscr.getch()
        if ch == 27:  # ESC
            curses.noecho()
            curses.curs_set(0)
            return None
        if ch in (curses.KEY_ENTER, 10, 13):
            val = "".join(buf).strip()
            curses.noecho()
            curses.curs_set(0)
            return val if val else ""
        if ch in (curses.KEY_BACKSPACE, 127, 8):
            if buf:
                buf.pop()
        elif 0 <= ch <= 255:
            c = chr(ch)
            if c.isprintable():
                buf.append(c)


def menu(stdscr, title: str, options: List[str], footer: str = "q: back/quit") -> int:
    idx = 0
    while True:
        draw_frame(stdscr, title)
        h, w = stdscr.getmaxyx()

        attr_footer = curses.color_pair(3) if curses.has_colors() else 0
        try:
            stdscr.addstr(h - 2, 2, footer[: w - 4], attr_footer)
        except curses.error:
            pass

        start_y = 3
        for i, opt in enumerate(options):
            y = start_y + i
            if y >= h - 3:
                break
            if i == idx:
                attr = curses.color_pair(2) | curses.A_BOLD if curses.has_colors() else curses.A_REVERSE
            else:
                attr = 0
            line = f"  {opt}"
            try:
                stdscr.addstr(y, 2, line[: w - 4], attr)
            except curses.error:
                pass

        stdscr.refresh()
        ch = stdscr.getch()

        if ch in (ord("q"), ord("Q")):
            return -1
        if ch in (curses.KEY_UP, ord("k")):
            idx = (idx - 1) % len(options)
        elif ch in (curses.KEY_DOWN, ord("j")):
            idx = (idx + 1) % len(options)
        elif ch in (curses.KEY_ENTER, 10, 13):
            return idx


def message_box(stdscr, title: str, lines: List[str], footer: str = "Press any key...") -> None:
    draw_frame(stdscr, title)
    h, w = stdscr.getmaxyx()

    y = 3
    for line in lines:
        if y >= h - 3:
            break
        try:
            stdscr.addstr(y, 2, line[: w - 4])
        except curses.error:
            pass
        y += 1

    attr_footer = curses.color_pair(3) if curses.has_colors() else 0
    try:
        stdscr.addstr(h - 2, 2, footer[: w - 4], attr_footer)
    except curses.error:
        pass
    stdscr.refresh()
    stdscr.getch()


# -----------------------------
# Alerts: beep + flash (5 iterations)
# -----------------------------
def beep_and_flash(stdscr, iterations: int = 5, delay: float = 0.12) -> None:
    """
    Beep + reverse-video flash. Iterations default to 5 per your request.
    """
    # Make sure screen is in a known state
    stdscr.nodelay(True)
    try:
        for _ in range(iterations):
            # beep
            try:
                curses.beep()
            except Exception:
                try:
                    stdscr.addstr("\a")
                except curses.error:
                    pass

            # flash (reverse)
            try:
                stdscr.attron(curses.A_REVERSE)
                stdscr.refresh()
                time.sleep(delay)
                stdscr.attroff(curses.A_REVERSE)
                stdscr.refresh()
            except curses.error:
                pass

            time.sleep(delay)

            # Drain any keypresses during alert so they don't "skip" the next screen
            try:
                while stdscr.getch() != -1:
                    pass
            except Exception:
                pass
    finally:
        stdscr.nodelay(False)


# -----------------------------
# Timer UI
# -----------------------------
def run_timer(stdscr, seconds: int, label: str, task: str) -> bool:
    """
    Returns True if completed, False if aborted.
    Press 'q' to abort.
    Displays task text on-screen.
    """
    start = time.time()
    end = start + seconds
    bar_width = 30

    stdscr.nodelay(True)
    try:
        while True:
            now = time.time()
            remaining = int(end - now)
            elapsed = seconds - max(0, remaining)

            if remaining <= 0:
                break

            mins, secs = divmod(remaining, 60)
            percent = min(1.0, elapsed / seconds) if seconds > 0 else 1.0
            filled = int(bar_width * percent)
            bar = "#" * filled + "-" * (bar_width - filled)

            draw_frame(stdscr, "Pomodoro Timer")
            h, w = stdscr.getmaxyx()

            title_attr = curses.color_pair(1) | curses.A_BOLD if curses.has_colors() else curses.A_BOLD
            center_text(stdscr, 2, label, title_attr)

            # Task line (new)
            task_line = f"Task: {task}"
            # Keep it from overflowing and avoid wrapping weirdness
            if len(task_line) > (w - 4):
                task_line = task_line[: max(0, w - 7)] + "..."
            try:
                stdscr.addstr(4, 2, task_line[: max(0, w - 4)])
            except curses.error:
                pass

            center_text(stdscr, 6, f"{mins:02}:{secs:02} remaining")
            center_text(stdscr, 8, f"[{bar}] {int(percent * 100):3d}%")

            attr_footer = curses.color_pair(3) if curses.has_colors() else 0
            try:
                stdscr.addstr(h - 2, 2, "q: abort timer"[: w - 4], attr_footer)
            except curses.error:
                pass

            stdscr.refresh()

            ch = stdscr.getch()
            if ch in (ord("q"), ord("Q")):
                return False

            time.sleep(0.1)

        # Completed
        draw_frame(stdscr, "Pomodoro Timer")
        ok_attr = curses.color_pair(4) | curses.A_BOLD if curses.has_colors() else curses.A_BOLD
        center_text(stdscr, 4, f"{label} complete!", ok_attr)

        # Show task again on completion screen
        h, w = stdscr.getmaxyx()
        task_line = f"Task: {task}"
        if len(task_line) > (w - 4):
            task_line = task_line[: max(0, w - 7)] + "..."
        try:
            stdscr.addstr(6, 2, task_line[: max(0, w - 4)])
        except curses.error:
            pass

        center_text(stdscr, 8, "Press any key...")
        stdscr.refresh()

        # New alert behavior (beep + flash x5)
        beep_and_flash(stdscr, iterations=5)

        stdscr.nodelay(False)
        stdscr.getch()
        return True
    finally:
        stdscr.nodelay(False)


# -----------------------------
# Log Viewer
# -----------------------------
def view_log(stdscr) -> None:
    lines = list(reversed(read_log_lines()))
    pos = 0

    while True:
        draw_frame(stdscr, "Previous Pomodoros")
        h, w = stdscr.getmaxyx()

        if not lines:
            message_box(stdscr, "Previous Pomodoros", ["No log entries found yet."], footer="Press any key...")
            return

        view_h = max(1, h - 6)
        end = min(len(lines), pos + view_h)
        window = lines[pos:end]

        try:
            stdscr.addstr(2, 2, f"Log file: {LOG_FILE}"[: w - 4],
                          curses.color_pair(3) if curses.has_colors() else 0)
        except curses.error:
            pass

        y = 4
        for line in window:
            if y >= h - 2:
                break
            try:
                stdscr.addstr(y, 2, line[: w - 4])
            except curses.error:
                pass
            y += 1

        footer = "Up/Down: scroll  PgUp/PgDn: page  Home/End  q: back"
        try:
            stdscr.addstr(h - 2, 2, footer[: w - 4], curses.color_pair(3) if curses.has_colors() else 0)
        except curses.error:
            pass

        stdscr.refresh()
        ch = stdscr.getch()

        if ch in (ord("q"), ord("Q")):
            return
        elif ch == curses.KEY_UP:
            pos = max(0, pos - 1)
        elif ch == curses.KEY_DOWN:
            pos = min(max(0, len(lines) - 1), pos + 1)
        elif ch == curses.KEY_PPAGE:
            pos = max(0, pos - view_h)
        elif ch == curses.KEY_NPAGE:
            pos = min(max(0, len(lines) - view_h), pos + view_h)
        elif ch == curses.KEY_HOME:
            pos = 0
        elif ch == curses.KEY_END:
            pos = max(0, len(lines) - view_h)


# -----------------------------
# Settings
# -----------------------------
def adjust_settings(stdscr, cfg: dict) -> dict:
    while True:
        options = [
            f"Work duration (minutes):  {cfg['work_minutes']}",
            f"Break duration (minutes): {cfg['break_minutes']}",
            "Save and return",
        ]
        choice = menu(stdscr, "Settings", options, footer="Enter: select  q: back (without saving)")
        if choice == -1:
            return cfg

        if choice == 0:
            val = prompt_input(stdscr, "Settings", "Set work minutes (1-180):", str(cfg["work_minutes"]))
            if val is None:
                continue
            try:
                cfg["work_minutes"] = max(1, min(int(val), 180))
            except ValueError:
                message_box(stdscr, "Settings", ["Invalid number."], footer="Press any key...")
        elif choice == 1:
            val = prompt_input(stdscr, "Settings", "Set break minutes (1-60):", str(cfg["break_minutes"]))
            if val is None:
                continue
            try:
                cfg["break_minutes"] = max(1, min(int(val), 60))
            except ValueError:
                message_box(stdscr, "Settings", ["Invalid number."], footer="Press any key...")
        elif choice == 2:
            save_config(cfg)
            message_box(stdscr, "Settings", ["Saved."], footer="Press any key...")
            return cfg


# -----------------------------
# Main flow
# -----------------------------
def start_pomodoro_flow(stdscr, cfg: dict) -> None:
    task = prompt_input(stdscr, "Start Pomodoro", "What task are you working on?")
    if task is None:
        return
    if task.strip() == "":
        task = "Untitled task"

    work_seconds = int(cfg["work_minutes"]) * 60
    break_seconds = int(cfg["break_minutes"]) * 60

    log_session(task, "START")

    completed = run_timer(stdscr, work_seconds, "WORK", task)
    if not completed:
        log_session(task, "ABORT")
        message_box(stdscr, "Pomodoro", ["Work timer aborted.", "Logged as ABORT."], footer="Press any key...")
        return

    log_session(task, "END")

    choice = menu(
        stdscr,
        "Break",
        ["Start break now", "Skip break and return to menu"],
        footer="Enter: select  q: back (acts like skip)",
    )
    if choice == 0:
        run_timer(stdscr, break_seconds, "BREAK", task)


def main_curses(stdscr) -> None:
    init_curses(stdscr)
    cfg = load_config()

    while True:
        options = [
            "Start Pomodoro",
            "View previous pomodoros",
            "Settings",
            "Quit",
        ]
        choice = menu(
            stdscr,
            "PomoCLI (curses)",
            options,
            footer="Up/Down: move  Enter: select  q: quit",
        )

        if choice in (-1, 3):
            break
        elif choice == 0:
            start_pomodoro_flow(stdscr, cfg)
            cfg = load_config()
        elif choice == 1:
            view_log(stdscr)
        elif choice == 2:
            cfg = adjust_settings(stdscr, cfg)
            cfg = load_config()


def main() -> None:
    curses.wrapper(main_curses)


if __name__ == "__main__":
    main()
