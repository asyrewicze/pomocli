#!/usr/bin/env python3
"""
pomocli.py
A curses-based Pomodoro CLI with:
- Start Pomodoro (task prompt -> work timer -> break timer)
- Complete a Pomodoro early with Enter (logged as COMPLETE EARLY)
- View previous pomodoros (from a text log file)
- Settings (work/break durations, log directory, ASCII/Unicode graphics)

Files live under ~/.pomocli by default (override with POMOCLI_DIR).
Set POMOCLI_KEEP_TERM=1 to skip the macOS `rep` workaround (see neutralize_rep).
"""

import argparse
import curses
import json
import locale
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import List, Optional, Sequence

__version__ = "1.0.2"

# Files
# Base directory for PomoCLI's data. Override with the POMOCLI_DIR environment
# variable; otherwise defaults to a dedicated ~/.pomocli directory. The config
# file must live at a known location so it can be found before it is read.
BASE_DIR = os.environ.get("POMOCLI_DIR") or os.path.expanduser("~/.pomocli")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# Defaults (minutes)
DEFAULT_WORK_MIN = 25
DEFAULT_BREAK_MIN = 5

# The log directory is user-configurable (see Settings); it defaults to the
# base directory. LOG_FILE is resolved from config at load time.
DEFAULT_LOG_DIR = BASE_DIR
LOG_FILE = os.path.join(BASE_DIR, "pomocli_log.txt")


# -----------------------------
# Terminal workarounds (pre-curses)
# -----------------------------
# macOS links Python's curses against Apple's byte-oriented ncurses. When a
# terminal's terminfo advertises the `rep` capability, ncurses compresses a run
# of identical characters into one character plus ESC[Nb - but it does so a
# *byte* at a time, so a run of "\u2588" (e2 96 88) leaves the process as the
# trailing 0x88 plus a repeat count, and the terminal draws the debris as "?".
# Only runs corrupt, which is why the progress bar and the tomato art break
# while lone glyphs elsewhere survive. On macOS kitty's terminfo advertises
# `rep` and xterm-256color's does not, so pointing TERM at a rep-less entry is
# the entire fix - and it has to happen before initscr() reads TERM.
#
# This is Apple's ncurses alone; see neutralize_rep for why the swap is confined
# to macOS and what a replacement entry has to prove before it is adopted.

# Tried in order when the active terminal advertises `rep`. Each candidate is
# re-probed before it is accepted, so this is a preference order, not a promise:
# terminfo databases disagree about `rep` (ncurses 6.5 on Debian 13 gives it to
# `xterm-256color` and `xterm` alike, while older databases do not), and a
# candidate that fails the probe is skipped rather than adopted. `vt100` is
# deliberately absent: it is rep-less, but it also lacks `civis`, so adopting it
# would trade corrupt glyphs for a crash in curses.curs_set().
FALLBACK_TERMS = ("xterm-256color", "xterm")

# What a replacement entry must still be able to do. Hiding the cursor is the
# first thing PomoCLI asks of curses, and a terminal without `civis` answers by
# raising, so a swap that drops it breaks the app before it draws a frame.
REQUIRED_CAPS = ("civis",)

# Asks about one terminal, then exits. Capability names arrive as arguments and
# come back as a string of 1s and 0s in the same order. See probe_caps for why
# this cannot be answered in-process.
_CAP_PROBE = (
    "import curses, sys\n"
    "curses.setupterm()\n"
    "sys.stdout.write(''.join(\n"
    "    '1' if curses.tigetstr(cap) else '0' for cap in sys.argv[1:]))\n"
)

# A Python startup plus a terminfo lookup. Generous, but bounded: PomoCLI must
# not hang on a wedged subprocess before it draws anything.
PROBE_TIMEOUT_SECONDS = 5.0


def probe_caps(caps: Sequence[str], term: Optional[str] = None,
               env: Optional[dict] = None) -> Optional[dict]:
    """Which of `caps` a terminfo entry carries. None when it cannot be read.

    Runs in a subprocess because ncurses' setupterm is sticky: once cur_term is
    initialized, later setupterm calls naming a *different* terminal quietly
    return the first terminal's capabilities instead of loading the new entry.
    Probing candidates in-process would therefore report the starting terminal's
    answer for every one of them, and the probe itself would pin cur_term, so a
    TERM swapped afterwards would never take effect. A fresh interpreter gets a
    clean cur_term.
    """
    # The caller's env is an override layer, not a replacement: the child still
    # needs HOME to find ~/.terminfo, which is where kitty installs its entry.
    overrides = {} if env is None else dict(env)
    child_env = {**os.environ, **overrides}
    if term is not None:
        child_env["TERM"] = term
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _CAP_PROBE, *caps],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            env=child_env,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    # An unknown terminal makes the child exit non-zero having printed nothing,
    # which surfaces here as None rather than a verdict: "no such entry" must
    # never be mistaken for "this terminal is safe".
    answer = proc.stdout.strip()
    if len(answer) != len(caps) or set(answer) - {"0", "1"}:
        return None
    return {cap: flag == "1" for cap, flag in zip(caps, answer)}


def neutralize_rep(env: Optional[dict] = None) -> Optional[str]:
    """Point TERM at a rep-less entry when the current one would shatter runs.

    Returns the TERM adopted, or None when nothing needed changing. Set
    POMOCLI_KEEP_TERM=1 to opt out and keep the terminal's own entry.

    On macOS this is applied whenever `rep` is advertised rather than only on
    builds known to be byte-oriented: the usual wide-character probes lie there
    (hasattr(curses, "unget_wch") is True on the very build that corrupts the
    output), and a slightly reduced TERM costs far less than a garbled timer.
    """
    env = os.environ if env is None else env
    if env.get("POMOCLI_KEEP_TERM"):
        return None
    # Everywhere else Python's curses links wide ncurses, which emits runs of
    # multibyte characters intact; only Apple's byte-oriented build shatters
    # them. Off macOS the swap is all cost and no benefit, and the cost is real:
    # on a terminfo database that gives `rep` to every xterm entry, the search
    # walks past its usable candidates and downgrades a perfectly good terminal.
    if sys.platform != "darwin":
        return None
    caps = probe_caps(("rep",), env=env)
    if not caps or not caps["rep"]:
        return None

    current = env.get("TERM")
    wanted = ("rep", *REQUIRED_CAPS)
    for candidate in FALLBACK_TERMS:
        if candidate == current:
            continue
        caps = probe_caps(wanted, candidate, env=env)
        # Unreadable entry, still shatters runs, or missing something PomoCLI
        # needs: leave TERM alone. Unicode glyphs may corrupt, but the app runs,
        # and Settings offers ASCII mode as the way out.
        if caps and not caps["rep"] and all(caps[c] for c in REQUIRED_CAPS):
            env["TERM"] = candidate
            return candidate
    return None


def ensure_parent_dir(path: str) -> None:
    """Create the parent directory of `path` if it does not already exist."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def resolve_log_file(cfg: dict) -> str:
    log_dir = cfg.get("log_dir") or DEFAULT_LOG_DIR
    return os.path.join(os.path.expanduser(log_dir), "pomocli_log.txt")


# -----------------------------
# Persistence
# -----------------------------
def load_config() -> dict:
    global LOG_FILE
    cfg = {"work_minutes": DEFAULT_WORK_MIN,
           "break_minutes": DEFAULT_BREAK_MIN,
           "log_dir": DEFAULT_LOG_DIR,
           "use_unicode": False}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                cfg["work_minutes"] = int(
                    data.get("work_minutes", cfg["work_minutes"]))
                cfg["break_minutes"] = int(
                    data.get("break_minutes", cfg["break_minutes"]))
                log_dir = str(data.get("log_dir", cfg["log_dir"])).strip()
                if log_dir:
                    cfg["log_dir"] = log_dir
                cfg["use_unicode"] = bool(
                    data.get("use_unicode", cfg["use_unicode"]))
    except FileNotFoundError:
        pass
    except Exception:
        pass

    cfg["work_minutes"] = max(1, min(cfg["work_minutes"], 180))
    cfg["break_minutes"] = max(1, min(cfg["break_minutes"], 60))
    LOG_FILE = resolve_log_file(cfg)
    return cfg


def save_config(cfg: dict) -> None:
    global LOG_FILE
    safe = {
        "work_minutes": int(cfg.get("work_minutes", DEFAULT_WORK_MIN)),
        "break_minutes": int(cfg.get("break_minutes", DEFAULT_BREAK_MIN)),
        "log_dir": str(cfg.get("log_dir", DEFAULT_LOG_DIR)).strip() or DEFAULT_LOG_DIR,
        "use_unicode": bool(cfg.get("use_unicode", False)),
    }
    ensure_parent_dir(CONFIG_FILE)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(safe, f, indent=2)
    LOG_FILE = resolve_log_file(safe)


# -----------------------------
# Logging
# -----------------------------
def log_session(task_description: str, state: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d T=%H:%M")
    ensure_parent_dir(LOG_FILE)
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
def set_cursor(visible: int) -> None:
    """Show or hide the cursor, tolerating terminals that cannot do either.

    curs_set() returns ERR - which Python raises as curses.error - when terminfo
    carries no `civis` (hide) or `cnorm` (show); `vt100` and `dumb` have neither.
    Cursor visibility is cosmetic in PomoCLI, so a terminal that refuses is not a
    reason to abort: hiding fails at startup, showing fails at the task prompt,
    and both screens are perfectly usable with the cursor left where it is.
    """
    try:
        curses.curs_set(visible)
    except curses.error:
        pass


def init_curses(stdscr) -> None:
    set_cursor(0)
    stdscr.nodelay(False)
    stdscr.keypad(True)
    curses.noecho()
    curses.cbreak()
    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)     # Title
        curses.init_pair(2, curses.COLOR_BLACK,
                         curses.COLOR_WHITE)  # Highlight
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
        attr = curses.color_pair(
            1) | curses.A_BOLD if curses.has_colors() else curses.A_BOLD
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

    set_cursor(1)
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
            set_cursor(0)
            return None
        if ch in (curses.KEY_ENTER, 10, 13):
            val = "".join(buf).strip()
            curses.noecho()
            set_cursor(0)
            return val if val else ""
        if ch in (curses.KEY_BACKSPACE, 127, 8):
            if buf:
                buf.pop()
        elif 0 <= ch <= 255:
            c = chr(ch)
            if c.isprintable():
                buf.append(c)


def menu(stdscr, title: str, options: List[str], footer: str = "[q]: back/quit",
         corner: str = "") -> int:
    idx = 0
    while True:
        draw_frame(stdscr, title)
        h, w = stdscr.getmaxyx()

        attr_footer = curses.color_pair(3) if curses.has_colors() else 0
        try:
            stdscr.addstr(h - 2, 2, footer[: w - 4], attr_footer)
        except curses.error:
            pass

        # Optional version/label tucked into the bottom-right border
        if corner:
            label = f" {corner} "
            try:
                stdscr.addstr(h - 1, max(1, w - len(label) - 1), label,
                              attr_footer)
            except curses.error:
                pass

        start_y = 3
        for i, opt in enumerate(options):
            y = start_y + i
            if y >= h - 3:
                break
            if i == idx:
                attr = curses.color_pair(
                    2) | curses.A_BOLD if curses.has_colors() else curses.A_REVERSE
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
# Two art sets so the timer works on any terminal. Unicode uses block glyphs
# (nicer, but needs a font that has them); ASCII works everywhere. Every line
# in a set is padded to the same width so center_text aligns them consistently.
UNICODE_ART = [
    "                ░░        ",
    "              ░░          ",
    "      ░░      ░░    ░░    ",
    "        ░░██░░██░░░░      ",
    "    ████▒▒░░░░░░▒▒████    ",
    "  ██▒▒▒▒░░░░▒▒▒▒  ▒▒▒▒██  ",
    "  ██▒▒░░▒▒▒▒▒▒▒▒▒▒    ██  ",
    "██▓▓▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒  ▒▒██",
    "██▓▓▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒  ██",
    "██▓▓▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒██",
    "██▓▓▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒██",
    "  ██▓▓▓▓▒▒▒▒▒▒▒▒▒▒▒▒▒▒██  ",
    "  ██▓▓▓▓▓▓▒▒▒▒▒▒▒▒▒▒▒▒██  ",
    "    ████▓▓▓▓▓▓▓▓▓▓████    ",
    "        ██████████        ",
]

ASCII_ART = [
    " /\\_/\\ ",
    "( o.o )",
    " > ^ < ",
]


def run_timer(stdscr, seconds: int, label: str, task: str,
              use_unicode: bool = False) -> bool:
    """
    Returns True if completed, False if aborted.
    Press 'q' to abort.
    Press 'enter' to complete early.
    Displays task text on-screen.
    `use_unicode` selects block glyphs vs. an ASCII-safe fallback.
    """
    fill_ch, empty_ch = ("█", "░") if use_unicode else ("#", "-")
    art_lines = UNICODE_ART if use_unicode else ASCII_ART
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
            bar = fill_ch * filled + empty_ch * (bar_width - filled)

            draw_frame(stdscr, "Pomodoro Timer")
            h, w = stdscr.getmaxyx()

            title_attr = curses.color_pair(
                1) | curses.A_BOLD if curses.has_colors() else curses.A_BOLD
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
            if use_unicode:
                center_text(stdscr, 8, f"{bar} {int(percent * 100):3d}%")
            else:
                center_text(stdscr, 8, f"[{bar}] {int(percent * 100):3d}%")

            # Render each line of the (Unicode or ASCII) art, centered
            for i, line in enumerate(art_lines):
                center_text(stdscr, 10 + i, line)

            attr_footer = curses.color_pair(3) if curses.has_colors() else 0
            try:
                stdscr.addstr(
                    h - 2, 2, "[q]: abort timer"[: w - 4], attr_footer)
                stdscr.addstr(
                    h - 3, 2, "[CR]: complete early"[: w - 4], attr_footer)
            except curses.error:
                pass

            stdscr.refresh()

            ch = stdscr.getch()
            if ch in (ord("q"), ord("Q")):
                return False
            if ch in (curses.KEY_ENTER, 10, 13):  # Enter key
                log_session(task, "COMPLETE EARLY")
                draw_frame(stdscr, "Pomodoro Timer")
                center_text(stdscr, 4, "Pomodoro marked as complete early!", curses.color_pair(
                    4) | curses.A_BOLD if curses.has_colors() else curses.A_BOLD)
                center_text(stdscr, 8, "Press any key to exit.")
                stdscr.refresh()
                stdscr.getch()
                return True

            time.sleep(0.1)

        # Completed
        draw_frame(stdscr, "Pomodoro Timer")
        ok_attr = curses.color_pair(
            4) | curses.A_BOLD if curses.has_colors() else curses.A_BOLD
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
            message_box(stdscr, "Previous Pomodoros", [
                        "No log entries found yet."], footer="Press any key...")
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

        footer = "[Up/Down]: scroll  PgUp/PgDn: page  Home/End  [q]: back"
        try:
            stdscr.addstr(
                h - 2, 2, footer[: w - 4], curses.color_pair(3) if curses.has_colors() else 0)
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
def clear_log_sequence(stdscr, cfg: dict) -> None:
    log_dir = cfg.get("log_dir") or DEFAULT_LOG_DIR
    current_log = os.path.join(os.path.expanduser(log_dir), "pomocli_log.txt")
    message_box(stdscr, "Are you Sure?", ["Are you sure you want to clear the pomodoro log?"])
    message_box(stdscr, "Are you REALLY Sure?", ["This will permanently delete all entries."])
    message_box(stdscr, "Clear Log", ["Clearing log file..."])
    try:
        ensure_parent_dir(current_log)
        with open(current_log, "w", encoding="utf-8") as f:
            pass
    except Exception:
        pass
    message_box(stdscr, "Confirmed Deletion", ["Log has been cleared successfully."])


def adjust_settings(stdscr, cfg: dict) -> dict:
    while True:
        options = [
            f"Work duration (minutes):  {cfg['work_minutes']}",
            f"Break duration (minutes): {cfg['break_minutes']}",
            f"Log directory: {cfg.get('log_dir', DEFAULT_LOG_DIR)}",
            f"Graphics: {'Unicode' if cfg.get('use_unicode', False) else 'ASCII'}",
            "Clear Pomodoro Log",
            "Save and return",
        ]
        choice = menu(stdscr, "Settings", options,
                      footer="[CR]: select  [q]: back (without saving)")
        if choice == -1:
            return cfg

        if choice == 0:
            val = prompt_input(
                stdscr, "Settings", "Set work minutes (1-180):", str(cfg["work_minutes"]))
            if val is None:
                continue
            try:
                cfg["work_minutes"] = max(1, min(int(val), 180))
            except ValueError:
                message_box(stdscr, "Settings", [
                            "Invalid number."], footer="Press any key...")
        elif choice == 1:
            val = prompt_input(
                stdscr, "Settings", "Set break minutes (1-60):", str(cfg["break_minutes"]))
            if val is None:
                continue
            try:
                cfg["break_minutes"] = max(1, min(int(val), 60))
            except ValueError:
                message_box(stdscr, "Settings", [
                            "Invalid number."], footer="Press any key...")
        elif choice == 2:
            val = prompt_input(
                stdscr, "Settings", "Log directory:",
                str(cfg.get("log_dir", DEFAULT_LOG_DIR)))
            if val is None:
                continue
            val = val.strip()
            if val == "":
                continue
            try:
                os.makedirs(os.path.expanduser(val), exist_ok=True)
                cfg["log_dir"] = val
            except Exception as e:
                message_box(stdscr, "Settings", [
                            "Could not use that directory:", str(e)],
                            footer="Press any key...")
        elif choice == 3:
            cfg["use_unicode"] = not cfg.get("use_unicode", False)
        elif choice == 4:
            clear_log_sequence(stdscr, cfg)
        elif choice == 5:
            save_config(cfg)
            message_box(stdscr, "Settings", [
                        "Saved."], footer="Press any key...")
            return cfg


# -----------------------------
# Main flow
# -----------------------------
def start_pomodoro_flow(stdscr, cfg: dict) -> None:
    task = prompt_input(stdscr, "Start Pomodoro",
                        "What task are you working on?")
    if task is None:
        return
    if task.strip() == "":
        task = "Untitled task"

    work_seconds = int(cfg["work_minutes"]) * 60
    break_seconds = int(cfg["break_minutes"]) * 60

    log_session(task, "START")

    use_unicode = cfg.get("use_unicode", False)
    completed = run_timer(stdscr, work_seconds, "WORK", task, use_unicode)
    if not completed:
        log_session(task, "ABORT")
        message_box(stdscr, "Pomodoro", [
                    "Work timer aborted.", "Logged as ABORT."], footer="Press any key...")
        return

    log_session(task, "END")

    choice = menu(
        stdscr,
        "Break",
        ["Start break now", "Skip break and return to menu"],
        footer="[CR]: select  [q]: back (acts like skip)",
    )
    if choice == 0:
        run_timer(stdscr, break_seconds, "BREAK", task, use_unicode)


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
            footer="[Up/Down]: move  [CR]: select  [q]: quit",
            corner=f"v{__version__}",
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
    parser = argparse.ArgumentParser(
        prog="pomocli",
        description="A curses-based Pomodoro timer for the terminal.",
        epilog=(
            "environment variables:\n"
            "  POMOCLI_DIR         base directory for config.json and the "
            "default log location\n"
            "                      (default: ~/.pomocli)\n"
            "  POMOCLI_KEEP_TERM   macOS only: keep the terminal's own TERM "
            "entry. PomoCLI\n"
            "                      otherwise swaps TERM for a `rep`-less one "
            "there, because\n"
            "                      terminfo entries advertising `rep` corrupt "
            "runs of Unicode\n"
            "                      block glyphs under Apple's ncurses. Set this "
            "if the swap\n"
            "                      causes trouble; expect the Unicode graphics "
            "mode to render\n"
            "                      as \"?\" when you do.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s {__version__}")
    parser.parse_args()

    # Use the terminal's preferred encoding so curses can draw the Unicode
    # progress bar and art instead of falling back to ASCII "?" glyphs.
    locale.setlocale(locale.LC_ALL, "")
    # Necessary but not sufficient: on macOS a terminfo entry advertising `rep`
    # still shatters runs of block glyphs. Must run before curses.wrapper,
    # because initscr() reads TERM at that moment. A no-op off macOS.
    neutralize_rep()
    curses.wrapper(main_curses)


if __name__ == "__main__":
    main()
