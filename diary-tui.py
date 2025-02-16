#!/usr/bin/env python3
"""
CALENDAR/TIME-MANAGING/VIEWING SCRIPT (with TASK NOTES & RECURRING TASK MANAGEMENT)

Features:
  - Daily diary entries with YAML frontmatter metadata.
  - Tasks are individual markdown notes in NOTES_DIR (with YAML frontmatter).
  - Tasks (one-off and recurring) are indexed via NOTES_DIR/index.json.
  - Tasks can be filtered by status: open, in-progress, done, or all.
  - Toggle a task’s status by cycling through open → in-progress → done (for one‑offs)
    or, for recurring tasks, toggling today’s instance completion.
  - New keybind (O) to open the currently selected task in your editor.
  - New keybinds: (x) to delete a task and (z) to cycle its priority.
  - Timeblock editing/updating (including adding an empty timeblock template) remains.
  - Multiple calendar views: year, month, week.
  - Search and tag filtering.
  - Side-by-side and fullscreen modes for preview, tasks, and timeblock views.
  - Obsidian-style link parsing and integration with your editor.
  - Live screen refresh and mouse support.
  - A context-aware command palette (Ctrl+P) for quick commands.
  - Robust error handling with logging.
  - RECURRING TASK MANAGEMENT:
      • Tasks can now define recurrence rules in a new YAML “recurrence” section.
      • Recurrence frequencies include: daily, weekly, monthly, yearly.
      • Weekly tasks use the “days_of_week” field and monthly/yearly tasks use “day_of_month”.
      • Completed instances are tracked in a new “complete_instances” list (YYYY-MM-DD).
      • When toggled (Enter key), a recurring task’s “today” instance is marked
        complete (or undone) without affecting future recurrences.

Dependencies: curses, yaml, json
"""
import threading
import time
import curses
import calendar
import subprocess
import shutil
import re
import yaml
import json
import os
import sys
import logging
import random
import string
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
import hashlib

# ---------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------
CONFIG_DIR = Path.home() / ".config" / "diary-tui"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

DEFAULT_CONFIG = {
    "diary_dir": str(Path.home() / "diary"),
    "notes_dir": str(Path.home() / "notes"),
    "home_file": str(Path.home() / "notes" / "home.md"),
    "log_file": "/tmp/calendar_tui.log",
    "editor": "nvim"  # or specify "vi", "nano", etc.
}

def load_config():
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with CONFIG_FILE.open("r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
                config.update(user_config)
        except Exception as e:
            logging.error(f"Error loading config file {CONFIG_FILE}: {e}")
    else:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with CONFIG_FILE.open("w", encoding="utf-8") as f:
                yaml.dump(DEFAULT_CONFIG, f, indent=2)
            logging.info(f"Default config file created at {CONFIG_FILE}")
        except Exception as e:
            logging.error(f"Error creating default config file: {e}")
    return config

CONFIG = load_config()

DIARY_DIR = Path(CONFIG["diary_dir"])
NOTES_DIR = Path(CONFIG["notes_dir"])
HOME_FILE = Path(CONFIG["home_file"])
LOG_FILE = Path(CONFIG["log_file"])
EDITOR_CONFIG = CONFIG.get("editor", "").strip()

logging.basicConfig(filename=LOG_FILE, level=logging.DEBUG,
                    format='%(asctime)s [%(levelname)s] %(message)s')

# ---------------------------------------------------------------------
# YAML FRONTMATTER UTILITIES
# ---------------------------------------------------------------------
class MetadataCache:
    def __init__(self):
        self.cache = {}
        self.file_hashes = {}
        self.file_mod_times = {}

    def get_metadata(self, file_path: Path) -> dict:
        if not file_path.exists():
            return {}
        try:
            current_mod_time = file_path.stat().st_mtime
        except Exception as e:
            logging.error(f"Error getting mod time for {file_path}: {e}")
            return {}

        if file_path in self.cache and self.file_mod_times.get(file_path) == current_mod_time:
            return self.cache[file_path]

        try:
            with file_path.open("r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            logging.error(f"Error reading {file_path}: {e}")
            return {}
        if len(lines) < 3 or lines[0].strip() != "---":
            return {}
        yaml_lines = []
        for line in lines[1:]:
            if line.strip() == "---":
                break
            yaml_lines.append(line)
        raw_yaml = "".join(yaml_lines)
        current_hash = hashlib.sha256(raw_yaml.encode("utf-8")).hexdigest()
        if file_path in self.cache and self.file_hashes.get(file_path) == current_hash:
            return self.cache[file_path]
        try:
            metadata = yaml.safe_load(raw_yaml) or {}
        except Exception as e:
            logging.error(f"Error parsing YAML in {file_path}: {e}")
            metadata = {}
        self.cache[file_path] = metadata
        self.file_hashes[file_path] = current_hash
        self.file_mod_times[file_path] = current_mod_time
        return metadata

    def rewrite_front_matter(self, file_path: Path, new_md: dict) -> bool:
        new_md["dateModified"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        try:
            if file_path.exists():
                with file_path.open("r", encoding="utf-8") as f:
                    lines = f.readlines()
            else:
                lines = []
        except Exception as e:
            logging.error(f"Error reading file for rewrite {file_path}: {e}")
            lines = []
        front = ["---\n"] + yaml.dump(new_md, sort_keys=False).splitlines(keepends=True) + ["---\n"]
        if lines and lines[0].strip() == "---":
            try:
                end_index = lines.index("---\n", 1)
                rest = lines[end_index+1:]
            except ValueError:
                rest = []
        else:
            rest = lines
        final_content = front + rest
        try:
            with file_path.open("w", encoding="utf-8") as f:
                f.writelines(final_content)
        except Exception as e:
            logging.error(f"Error rewriting frontmatter for {file_path}: {e}")
            return False
        self.cache[file_path] = new_md
        try:
            with file_path.open("r", encoding="utf-8") as f:
                lines = f.readlines()
            yaml_lines = []
            if lines and lines[0].strip() == "---":
                for line in lines[1:]:
                    if line.strip() == "---":
                        break
                    yaml_lines.append(line)
            raw_yaml = "".join(yaml_lines)
        except Exception as e:
            raw_yaml = ""
            logging.error(f"Error updating cache for {file_path}: {e}")
        self.file_hashes[file_path] = hashlib.sha256(raw_yaml.encode("utf-8")).hexdigest()
        return True

metadata_cache = MetadataCache()

# ---------------------------------------------------------------------
# TIMEBLOCK CACHE & TEMPLATE FUNCTIONS
# ---------------------------------------------------------------------
class TimeblockCache:
    def __init__(self):
        self.cache = {}
        self.file_hashes = {}
        self.file_mod_times = {}

    def get_timeblock(self, file_path: Path):
        if not file_path.exists():
            return []

        try:
            current_mod_time = file_path.stat().st_mtime
        except Exception as e:
            logging.error(f"Error getting mod time for {file_path}: {e}")
            return []

        if file_path in self.cache and self.file_mod_times.get(file_path) == current_mod_time:
            return self.cache[file_path]

        try:
            with file_path.open("r", encoding="utf-8") as f:
                contents = f.read()
        except Exception as e:
            logging.error(f"Error reading timeblock file {file_path}: {e}")
            return []
        current_hash = hashlib.sha256(contents.encode("utf-8")).hexdigest()
        if file_path in self.cache and self.file_hashes.get(file_path) == current_hash:
            return self.cache[file_path]
        tb = self.parse_timeblock(contents)
        self.cache[file_path] = tb
        self.file_hashes[file_path] = current_hash
        self.file_mod_times[file_path] = current_mod_time
        return tb

    def parse_timeblock(self, text: str):
        lines = text.splitlines()
        in_tb = False
        entries = []
        for line in lines:
            if line.strip().startswith("| Time") and "Activity" in line:
                in_tb = True
                continue
            if in_tb:
                if line.strip() == "" or line.strip().startswith("|-----"):
                    continue
                if line.startswith("|"):
                    parts = [p.strip() for p in line.strip("|").split("|")]
                    if len(parts) >= 2:
                        entries.append((parts[0], parts[1]))
                else:
                    break
        return entries

    def update_timeblock(self, file_path: Path, time_str: str, activity: str):
        try:
            with file_path.open("r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            return False, f"Error reading file: {e}"
        new_lines = []
        in_tb = False
        updated = False
        for line in lines:
            if line.strip().startswith("| Time") and "Activity" in line:
                in_tb = True
                new_lines.append(line)
                continue
            if in_tb:
                if line.strip().startswith("|-----"):
                    new_lines.append(line)
                    continue
                if line.startswith("|"):
                    parts = [p.strip() for p in line.strip("|").split("|")]
                    if parts and parts[0] == time_str:
                        new_lines.append(f"| {time_str} | {activity} |\n")
                        updated = True
                        continue
            new_lines.append(line)
        if not updated:
            for i, line in enumerate(new_lines):
                if line.strip().startswith("| Time") and "Activity" in line:
                    new_lines.insert(i+2, f"| {time_str} | {activity} |\n")
                    updated = True
                    break
        try:
            with file_path.open("w", encoding="utf-8") as f:
                f.writelines(new_lines)
            self.get_timeblock(file_path)
        except Exception as e:
            logging.error(f"Error updating timeblock in {file_path}: {e}")
            return False, f"Error writing file: {e}"

timeblock_cache = TimeblockCache()

def add_default_timeblock(file_path: Path):
    default_timeblock = [
        "| Time  | Activity |",
        "| ----- | --------- |",
        "| 05:00 |          |",
        "| 05:30 |          |",
        "| 06:00 |          |",
        "| 06:30 |          |",
        "| 07:00 |          |",
        "| 07:30 |          |",
        "| 08:00 |          |",
        "| 08:30 |          |",
        "| 09:00 |          |",
        "| 09:30 |          |",
        "| 10:00 |          |",
        "| 10:30 |          |",
        "| 11:00 |          |",
        "| 11:30 |          |",
        "| 12:00 |          |",
        "| 12:30 |          |",
        "| 13:00 |          |",
        "| 13:30 |          |",
        "| 14:00 |          |",
        "| 14:30 |          |",
        "| 15:00 |          |",
        "| 15:30 |          |",
        "| 16:00 |          |",
        "| 16:30 |          |",
        "| 17:00 |          |",
        "| 17:30 |          |",
        "| 18:00 |          |",
        "| 18:30 |          |",
        "| 19:00 |          |",
        "| 19:30 |          |",
        "| 20:00 |          |",
        "| 20:30 |          |",
        "| 21:00 |          |",
        "| 21:30 |          |",
        "| 22:00 |          |",
        "| 22:30 |          |",
        "| 23:00 |          |",
        "| 23:30 |          |"
    ]
    try:
        with file_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []
    for line in lines:
        if line.strip().startswith("| Time") and "Activity" in line:
            return  # Already exists.
    new_lines = lines + ["\n## Timeblock\n\n"] + [l + "\n" for l in default_timeblock]
    try:
        with file_path.open("w", encoding="utf-8") as f:
            f.writelines(new_lines)
        timeblock_cache.get_timeblock(file_path)
        return True
    except Exception as e:
        logging.error(f"Error adding default timeblock to {file_path}: {e}")
        return False

# ---------------------------------------------------------------------
# TASKS & INDEX FUNCTIONS (Revised to implement recurrence)
# ---------------------------------------------------------------------
def generate_task_filename():
    date_prefix = datetime.now().strftime("%y%m%d")
    suffix = ''.join(random.choices(string.ascii_lowercase, k=3))
    return f"{date_prefix}{suffix}.md"

class TaskManager:
    def __init__(self, notes_dir: Path):
        self.notes_dir = notes_dir
        self.index_cache = {"data": None, "mtime": 0}
        self.tasks = []
        # Initially load tasks for today
        self.load_tasks(datetime.now())

    def load_index(self):
        index_file = self.notes_dir / "index.json"
        try:
            current_mtime = index_file.stat().st_mtime
            if self.index_cache["data"] is None or current_mtime != self.index_cache["mtime"]:
                with index_file.open("r", encoding="utf-8") as f:
                    self.index_cache["data"] = json.load(f)
                self.index_cache["mtime"] = current_mtime
            return self.index_cache["data"]
        except Exception as e:
            logging.error(f"Error loading index file {index_file}: {e}")
            return []

    def _is_task_due_today(self, task: dict, current_date: datetime) -> bool:
        # For a task with recurrence rules, determine if it should appear on current_date.
        rec = task.get("recurrence")
        if not rec:
            return True  # one-off tasks are always loaded here
        frequency = rec.get("frequency", "").lower()
        # Daily: every day is due.
        if frequency == "daily":
            return True
        elif frequency == "weekly":
            # require a list of days (abbreviations, e.g., mon, tue, etc.)
            days = rec.get("days_of_week", [])
            # Map Monday=mon,... Sunday=sun. Note: Python weekday(): Monday==0.
            week_map = {0:"mon",1:"tue",2:"wed",3:"thu",4:"fri",5:"sat",6:"sun"}
            if week_map[current_date.weekday()] in days:
                return True
        elif frequency == "monthly":
            dom = rec.get("day_of_month")
            if dom and current_date.day == int(dom):
                return True
        elif frequency == "yearly":
            # For yearly, compare both month and day. Use initial task date as baseline.
            try:
                orig_date = datetime.strptime(task.get("date", ""), "%Y-%m-%dT%H:%M:%S")
            except Exception:
                orig_date = current_date  # fallback
            if current_date.month == orig_date.month and current_date.day == int(rec.get("day_of_month", orig_date.day)):
                return True
        return False

    def get_effective_status(self, task: dict, current_date: datetime) -> str:
        # For recurring tasks, effective status is determined by whether today's instance is complete.
        if task.get("recurrence"):
            comp = task.get("complete_instances", [])
            if current_date.strftime("%Y-%m-%d") in comp:
                return "done"
            else:
                return "open"
        else:
            return task.get("status", "open")

    def load_tasks(self, current_date: datetime):
        index_data = self.load_index()
        tasks = []
        for note in index_data:
            tags = note.get("tags")
            if isinstance(tags, list) and "task" in tags:
                # For recurring tasks, only include if due today.
                if note.get("recurrence"):
                    if self._is_task_due_today(note, current_date):
                        tasks.append(note)
                else:
                    tasks.append(note)
        # sort tasks: overdue first (only non-recurring tasks use due dates),
        # then by priority and due date.
        def is_overdue(task):
            due = task.get("due")
            status = self.get_effective_status(task, current_date)
            if due and status != "done":
                try:
                    due_date = datetime.strptime(due, "%Y-%m-%d")
                    return due_date.date() < current_date.date()
                except ValueError:
                    return False
            return False

        def sort_key(task):
            overdue = is_overdue(task)
            due = task.get("due")
            try:
                due_date = datetime.strptime(due, "%Y-%m-%d") if due else datetime.max
            except Exception:
                due_date = datetime.max
            priority = task.get("priority", "normal")
            priority_order = {"high": 0, "normal": 1, "low": 2}
            return (not overdue, priority_order.get(priority, 1), due_date)

        tasks.sort(key=sort_key)
        self.tasks = tasks

    def filter_tasks(self, status_filter: str, current_date: datetime):
        # status_filter can be "open", "in-progress", "done" or "all"
        filtered = []
        for t in self.tasks:
            effective_status = self.get_effective_status(t, current_date)
            if status_filter == "all" or effective_status == status_filter or t.get("status", "open") == status_filter:
                filtered.append(t)
        return filtered

    def create_task(self, title, due=None, priority="normal", extra_tags=None, recurrence_data: dict = None):
        filename = generate_task_filename()
        zettelid = filename[:-3]  # without .md
        file_path = NOTES_DIR / filename
        now_dt = datetime.now()
        now_str = now_dt.strftime("%Y-%m-%dT%H:%M:%S")
        today = now_dt.strftime("%Y-%m-%d")
        frontmatter = {
            "title": title,
            "zettelid": zettelid,
            "date": now_str,
            "dateModified": now_str,
            "status": "open",
            "due": due,
            "tags": ["task"] + (extra_tags if extra_tags else []),
            "priority": priority
        }
        if recurrence_data:
            frontmatter["recurrence"] = recurrence_data
            frontmatter["complete_instances"] = []
        content = (
            "---\n" +
            yaml.dump(frontmatter, sort_keys=False) +
            "---\n\n" +
            f"# {title}\n\n"
        )
        try:
            with file_path.open("w", encoding="utf-8") as f:
                f.write(content)
            logging.info(f"Created task note: {file_path}")
            return file_path
        except Exception as e:
            logging.error(f"Error creating task note: {e}")
            return None

    def toggle_task_status(self, task_path: Path):
        md = metadata_cache.get_metadata(task_path)
        today_str = datetime.now().strftime("%Y-%m-%d")
        # For recurring tasks, toggle today’s instance in complete_instances.
        if "recurrence" in md:
            complete = md.get("complete_instances", [])
            if today_str in complete:
                complete.remove(today_str)
            else:
                complete.append(today_str)
            md["complete_instances"] = complete
            # Do not change the overall "status" field.
        else:
            current_status = md.get("status", "open")
            new_status = {"open": "in-progress", "in-progress": "done", "done": "open"}.get(current_status, "open")
            md["status"] = new_status
        if metadata_cache.rewrite_front_matter(task_path, md):
            logging.info(f"Updated task {task_path}")
            return True
        else:
            logging.error(f"Failed to update task status for {task_path}")
            return False

    def cycle_task_priority(self, task_path: Path):
        md = metadata_cache.get_metadata(task_path)
        current_priority = md.get("priority", "normal")
        new_priority = {"low": "normal", "normal": "high", "high": "low"}.get(current_priority, "normal")
        md["priority"] = new_priority
        if metadata_cache.rewrite_front_matter(task_path, md):
            logging.info(f"Set task {task_path} priority to {new_priority}")
            return True
        else:
            logging.error(f"Failed to update task priority for {task_path}")
            return False

    def delete_task(self, task_path: Path):
        try:
            task_path.unlink()
            logging.info(f"Deleted task: {task_path}")
            return True
        except Exception as e:
            logging.error(f"Error deleting task {task_path}: {e}")
            return False

# ---------------------------------------------------------------------
# HELPER FUNCTIONS (DIARY, SEARCH, LINKS, ETC.)
# ---------------------------------------------------------------------
def calculate_week_stats_from_date(start_of_week: datetime) -> dict:
    total_pomodoros = 0
    total_workouts = 0
    days_meditated = 0
    for i in range(7):
        current = start_of_week + timedelta(days=i)
        file_path = DIARY_DIR / f"{current.strftime('%Y-%m-%d')}.md"
        md = metadata_cache.get_metadata(file_path)
        total_pomodoros += int(md.get("pomodoros", 0))
        if md.get("workout", False):
            total_workouts += 1
        if md.get("meditate", False):
            days_meditated += 1
    return {
        "total_pomodoros": total_pomodoros,
        "total_workouts": total_workouts,
        "days_meditated": days_meditated,
        "week_start": start_of_week.strftime("%Y-%m-%d"),
        "week_end": (start_of_week + timedelta(days=6)).strftime("%Y-%m-%d")
    }

def get_diary_preview(date_str: str) -> str:
    file_path = DIARY_DIR / f"{date_str}.md"
    if file_path.exists():
        try:
            return file_path.read_text(encoding="utf-8")
        except Exception as e:
            logging.error(f"Error reading diary preview {file_path}: {e}")
            return f"Error reading diary entry for {date_str}."
    return f"No diary entry for {date_str}."

def search_diary(query: str):
    query = query.lower()
    results = []
    for file in DIARY_DIR.glob("*.md"):
        try:
            content = file.read_text(encoding="utf-8").lower()
            md = metadata_cache.get_metadata(file)
            if query in content or query in str(md).lower():
                results.append(file.stem)
        except Exception as e:
            logging.error(f"Error searching file {file}: {e}")
    return sorted(results)

def filter_by_tag(tag: str):
    matches = set()
    for file in DIARY_DIR.glob("*.md"):
        md = metadata_cache.get_metadata(file)
        if isinstance(md.get("tags", []), list) and tag in md.get("tags", []):
            matches.add(file.stem)
    return matches

def parse_links_from_text(text: str):
    pattern = re.compile(r"\[\[([^]|]+)(?:\|([^\]]+))?\]\]")
    return [(m.group(2).strip() if m.group(2) else m.group(1).strip(),
             m.group(1).strip()) for m in pattern.finditer(text)]

def draw_rectangle(win, y1, x1, y2, x2):
    try:
        win.border()
    except curses.error:
        pass

def draw_links_menu(stdscr, links):
    if not links:
        return None
    height, width = stdscr.getmaxyx()
    menu_height = min(len(links) + 4, height - 4)
    menu_width = min(60, width - 4)
    start_y = max(0, (height - menu_height) // 2)
    start_x = max(0, (width - menu_width) // 2)
    win = curses.newwin(menu_height, menu_width, start_y, start_x)
    win.keypad(True)
    draw_rectangle(win, 0, 0, menu_height - 1, menu_width - 1)
    title = " Links "
    try:
        win.addstr(0, (menu_width - len(title)) // 2, title, curses.A_BOLD)
    except curses.error:
        pass
    selected = 0
    while True:
        for idx, (display, target) in enumerate(links[:menu_height - 4]):
            mode = curses.A_REVERSE if idx == selected else curses.A_NORMAL
            try:
                win.addstr(2 + idx, 2, f"{display} -> {target}", mode)
            except curses.error:
                pass
        win.refresh()
        key = win.getch()
        if key in (curses.KEY_UP, ord('k')):
            selected = (selected - 1) % len(links)
        elif key in (curses.KEY_DOWN, ord('j')):
            selected = (selected + 1) % len(links)
        elif key in (curses.KEY_ENTER, 10, 13):
            return links[selected]
        elif key in (27, ord('q')):
            return None

def draw_preview(stdscr, lines, start_y, start_x, height, width, scroll):
    max_width = width - start_x - 2
    available = height - start_y - 2
    for idx, line in enumerate(lines[scroll:scroll + available]):
        try:
            stdscr.addnstr(start_y + idx, start_x, line[:max_width], max_width)
        except curses.error:
            pass

# ---------------------------------------------------------------------
# DIARY TUI CLASS (with combined functionality including recurring tasks)
# ---------------------------------------------------------------------
class DiaryTUI:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()
        # Initialize color pairs
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, -1, curses.COLOR_CYAN)
        curses.init_pair(3, curses.COLOR_GREEN, -1)      # low priority
        curses.init_pair(4, curses.COLOR_MAGENTA, -1)
        curses.init_pair(5, curses.COLOR_RED, -1)        # high priority / important
        curses.init_pair(6, curses.COLOR_YELLOW, -1)
        curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(8, curses.COLOR_BLACK, -1)
        curses.init_pair(9, curses.COLOR_BLUE, -1)         # overdue
        curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
        curses.mouseinterval(0)
        self.cal = calendar.TextCalendar(calendar.SUNDAY)
        self.selected_date = datetime.now()
        self.current_view = "month"  # "year", "month", "week"
        self.is_side_by_side = False
        self.preview_scroll = 0
        self.search_results = set()
        self.tag_results = set()
        self.current_search_idx = -1
        self.search_list = []
        self.nvim_path = shutil.which("nvim")
        self.tmux_path = shutil.which("tmux")
        self.fallback_editor = shutil.which("vi") or shutil.which("nano")
        # Tasks related attributes
        self.task_filter = "open"  # can be open, in-progress, done, or "all"
        self.task_manager = TaskManager(NOTES_DIR)
        self.tasks_list = []  # list of task dicts from the index (will include effective status for recurring tasks)
        self.selected_task_index = 0
        self.selected_timeblock_index = 0
        self.show_tasks = True  # in side-by-side mode, show tasks pane by default
        self.non_side_by_side_mode = "timeblock"  # can be "preview", "tasks", or "timeblock"
        self.calendar_height_non_side = 0
        self.calendar_height_side = 0
        self.refresh_timer = None
        # Focus flags for panes
        self.task_pane_focused = False
        self.timeblock_pane_focused = False
        self.preview_pane_focused = False

    def get_week_start(self) -> datetime:
        delta = (self.selected_date.weekday() + 1) % 7
        return self.selected_date - timedelta(days=delta)

    def run(self):
        self.start_refresh_thread()
        while True:
            self.stdscr.clear()
            height, width = self.stdscr.getmaxyx()
            if height < 10 or width < 60:
                self.display_minimum_size_warning(height, width)
                if self.stdscr.getch() == ord('q'):
                    break
                continue
            if self.is_side_by_side:
                self.draw_side_by_side_layout(height, width)
            else:
                self.draw_layout(height, width)
            self.draw_divider(height, width)
            date_str = self.selected_date.strftime("%Y-%m-%d")
            file_path = DIARY_DIR / f"{date_str}.md"
            preview_text = get_diary_preview(date_str)
            lines = preview_text.splitlines()
            if self.is_side_by_side:
                self.draw_preview_pane(height, width, lines)
                if self.show_tasks:
                    self.draw_tasks_pane(height, width)
                else:
                    self.draw_timeblock_pane(height, width)
            else:
                if self.non_side_by_side_mode == "preview":
                    self.draw_preview_pane_full(height, width, lines)
                elif self.non_side_by_side_mode == "tasks":
                    self.draw_tasks_pane_full(height, width)
                elif self.non_side_by_side_mode == "timeblock":
                    self.draw_timeblock_pane_full(height, width)
            self.display_status_bar(height, width)
            self.display_footer(height, width)
            self.stdscr.refresh()
            key = self.stdscr.getch()
            if key == 16:  # Ctrl+P: command palette
                self.show_command_palette(height, width)
            elif not self.handle_input(key, height, width, file_path, date_str):
                break
        self.stop_refresh_thread()

    def display_minimum_size_warning(self, height, width):
        warning = "Terminal too small. Resize or press 'q' to quit."
        try:
            self.stdscr.addnstr(height // 2, max(0, (width - len(warning)) // 2),
                                 warning, len(warning), curses.A_BOLD)
        except curses.error:
            pass

    def display_status_bar(self, height, width):
        week_start = self.get_week_start()
        stats = calculate_week_stats_from_date(week_start)
        if self.is_side_by_side:
            if self.task_pane_focused:
                focus = "Tasks"
            elif self.timeblock_pane_focused:
                focus = "Timeblock"
            else:
                focus = "Calendar"
        else:
            if self.non_side_by_side_mode == "tasks":
                focus = "Tasks"
            elif self.non_side_by_side_mode == "timeblock":
                focus = "Timeblock"
            else:
                focus = "Preview"
        status_text = (f" Date: {self.selected_date.strftime('%Y-%m-%d')} | "
                       f"Pomodoros: {stats['total_pomodoros']} | "
                       f"Workouts: {stats['total_workouts']} | Meditated: {stats['days_meditated']} | "
                       f"Focus: {focus} | View: {self.current_view} ")
        if focus == "Tasks":
            status_text += f"| Task Filter: {self.task_filter} "
        try:
            self.stdscr.addnstr(0, 0, status_text.ljust(width), width, curses.A_REVERSE)
        except curses.error:
            pass

    def draw_divider(self, height, width):
        if self.is_side_by_side:
            preview_x = width // 2 + 4
            try:
                self.stdscr.vline(0, preview_x - 2, curses.ACS_VLINE, height)
            except curses.error:
                pass
        else:
            try:
                self.stdscr.hline(self.calendar_height_non_side + 2, 0, curses.ACS_HLINE, width)
            except curses.error:
                pass

    def draw_layout(self, height, width):
        start_x, start_y = 2, 2
        if self.current_view == "month":
            draw_single_month(self.stdscr, self.cal, self.selected_date.year, self.selected_date.month,
                              start_x, start_y,
                              highlight=(self.selected_date.year, self.selected_date.month, self.selected_date.day),
                              search_results=self.search_results, tag_results=self.tag_results)
            self.calendar_height_non_side = 8
        elif self.current_view == "week":
            draw_week_view(self.stdscr, self.cal, self.selected_date,
                           start_x, start_y, search_results=self.search_results, tag_results=self.tag_results)
            self.calendar_height_non_side = 6
        else:
            draw_year_view(self.stdscr, self.cal, self.selected_date.year,
                           start_x, start_y,
                           highlight=(self.selected_date.year, self.selected_date.month, self.selected_date.day),
                           search_results=self.search_results, tag_results=self.tag_results)
            self.calendar_height_non_side = 39

    def draw_side_by_side_layout(self, height, width):
        cal_width = width // 2 - 4
        if self.current_view == "month":
            draw_single_month(self.stdscr, self.cal, self.selected_date.year, self.selected_date.month,
                              2, 2,
                              highlight=(self.selected_date.year, self.selected_date.month, self.selected_date.day),
                              search_results=self.search_results, tag_results=self.tag_results)
            self.calendar_height_side = 8
        elif self.current_view == "week":
            draw_week_view(self.stdscr, self.cal, self.selected_date,
                           2, 2, search_results=self.search_results, tag_results=self.tag_results)
            self.calendar_height_side = 6
        else:
            draw_year_view(self.stdscr, self.cal, self.selected_date.year,
                           2, 2,
                           highlight=(self.selected_date.year, self.selected_date.month, self.selected_date.day),
                           search_results=self.search_results, tag_results=self.tag_results)
            self.calendar_height_side = 39

    def draw_preview_pane(self, height, width, lines):
        preview_y = 2
        preview_x = (width // 2) + 6
        draw_preview(self.stdscr, lines, preview_y, preview_x, height, width, self.preview_scroll)

    def draw_preview_pane_full(self, height, width, lines):
        preview_y = self.calendar_height_non_side + 3
        preview_x = 2
        draw_preview(self.stdscr, lines, preview_y, preview_x, height, width, self.preview_scroll)

    def read_tasks_cache(self):
        # Reload tasks using selected_date for recurrence checking.
        self.task_manager.load_tasks(self.selected_date)
        self.tasks_list = self.task_manager.filter_tasks(self.task_filter, self.selected_date)

    def display_error(self, msg):
        height, width = self.stdscr.getmaxyx()
        try:
            self.stdscr.addnstr(height - 2, 2, msg, width - 4, curses.A_BOLD)
        except curses.error:
            pass
        self.stdscr.refresh()
        time.sleep(1)

    def draw_tasks_pane(self, height, width):
        tasks_y = self.calendar_height_side + 3
        tasks_x = 2
        available_height = height - tasks_y - 1
        available_width = (width // 2) - 4
        self.read_tasks_cache()
        for idx, task in enumerate(self.tasks_list[self.preview_scroll:self.preview_scroll + available_height]):
            # Mark recurring tasks with * at the start.
            prefix = "[*]" if task.get("recurrence") else ""
            effective_status = self.task_manager.get_effective_status(task, self.selected_date)
            mark = "[x]" if effective_status == "done" else ("[~]" if effective_status == "in-progress" else "[ ]")
            title = task.get("title", "Untitled")
            due = task.get("due", "")
            priority = task.get("priority", "normal")
            attr = curses.A_NORMAL
            if priority == "high":
                attr |= curses.color_pair(5)
            elif priority == "low":
                attr |= curses.color_pair(3)
            else:
                attr |= curses.color_pair(6)
            if due:
                try:
                    due_date = datetime.strptime(due, "%Y-%m-%d")
                    if due_date < datetime.today() and effective_status != "done":
                        attr = curses.color_pair(9) | curses.A_BOLD
                except Exception:
                    pass
            line = f"- {mark}{prefix} {title}"
            if self.task_pane_focused and (idx + self.preview_scroll) == self.selected_task_index:
                attr |= curses.A_REVERSE
            if due:
                line += f" (Due: {due})"
            try:
                self.stdscr.addnstr(tasks_y + idx, tasks_x, line, available_width, attr)
            except curses.error:
                pass

    def draw_tasks_pane_full(self, height, width):
        tasks_y = self.calendar_height_non_side + 3
        tasks_x = 2
        available_height = height - tasks_y - 3
        available_width = width - 4
        self.read_tasks_cache()
        for idx, task in enumerate(self.tasks_list[self.preview_scroll:self.preview_scroll + available_height]):
            prefix = "[*]" if task.get("recurrence") else ""
            effective_status = self.task_manager.get_effective_status(task, self.selected_date)
            mark = "[x]" if effective_status == "done" else ("[~]" if effective_status == "in-progress" else "[ ]")
            title = task.get("title", "Untitled")
            due = task.get("due", "")
            priority = task.get("priority", "normal")
            attr = curses.A_NORMAL
            if priority == "high":
                attr |= curses.color_pair(5)
            elif priority == "low":
                attr |= curses.color_pair(3)
            else:
                attr |= curses.color_pair(6)
            if due:
                try:
                    due_date = datetime.strptime(due, "%Y-%m-%d")
                    if due_date < datetime.today() and effective_status != "done":
                        attr = curses.color_pair(9) | curses.A_BOLD
                except Exception:
                    pass
            line = f"- {mark}{prefix} {title}"
            if self.task_pane_focused and (idx + self.preview_scroll) == self.selected_task_index:
                attr |= curses.A_REVERSE
            if due:
                line += f" (Due: {due})"
            try:
                self.stdscr.addnstr(tasks_y + idx, tasks_x, line, available_width, attr)
            except curses.error:
                pass

    def draw_timeblock_pane(self, height, width):
        tb_y = self.calendar_height_side + 3
        tb_x = 2
        available_height = height - tb_y - 1
        available_width = (width // 2) - 4
        date_str = self.selected_date.strftime("%Y-%m-%d")
        file_path = DIARY_DIR / f"{date_str}.md"
        tb_entries = timeblock_cache.get_timeblock(file_path)
        table = ["", "  Time  | Activity  "]
        for t, act in tb_entries:
            table.append(f"  {t} | {act} ")
        now = datetime.now()
        for idx, line in enumerate(table[self.preview_scroll:self.preview_scroll + available_height]):
            attr = curses.A_NORMAL
            if idx > 1:
                try:
                    t_str = table[idx + self.preview_scroll].split('|')[0].strip()
                    block_hour, block_min = map(int, t_str.split(":"))
                    end_hour, end_min = block_hour, block_min + 30
                    if end_min >= 60:
                        end_min -= 60
                        end_hour += 1
                    if ((now.hour > block_hour) or (now.hour == block_hour and now.minute >= block_min)) and \
                       ((now.hour < end_hour) or (now.hour == end_hour and now.minute < end_min)):
                        attr = curses.color_pair(2) | curses.A_BOLD
                    elif (self.timeblock_pane_focused and (idx + self.preview_scroll - 2) == self.selected_timeblock_index):
                        attr = curses.color_pair(3) | curses.A_BOLD
                except Exception:
                    pass
            try:
                self.stdscr.addnstr(tb_y + idx, tb_x, line, available_width, attr)
            except curses.error:
                pass

    def draw_timeblock_pane_full(self, height, width):
        tb_y = self.calendar_height_non_side + 3
        tb_x = 2
        available_height = height - tb_y - 3
        available_width = width - 4
        date_str = self.selected_date.strftime("%Y-%m-%d")
        file_path = DIARY_DIR / f"{date_str}.md"
        tb_entries = timeblock_cache.get_timeblock(file_path)
        table = ["", "  Time  | Activity  "]
        for t, act in tb_entries:
            table.append(f"  {t} | {act} ")
        now = datetime.now()
        for idx, line in enumerate(table[self.preview_scroll:self.preview_scroll + available_height]):
            attr = curses.A_NORMAL
            if idx > 1:
                try:
                    t_str = table[idx + self.preview_scroll].split('|')[0].strip()
                    block_hour, block_min = map(int, t_str.split(":"))
                    end_hour, end_min = block_hour, block_min + 30
                    if end_min >= 60:
                        end_min -= 60
                        end_hour += 1
                    if ((now.hour > block_hour) or (now.hour == block_hour and now.minute >= block_min)) and \
                       ((now.hour < end_hour) or (now.hour == end_hour and now.minute < end_min)):
                        attr = curses.color_pair(2) | curses.A_BOLD
                    elif (self.timeblock_pane_focused and (idx + self.preview_scroll - 2) == self.selected_timeblock_index):
                        attr = curses.color_pair(3) | curses.A_BOLD
                except Exception:
                    pass
            try:
                self.stdscr.addnstr(tb_y + idx, tb_x, line, available_width, attr)
            except curses.error:
                pass

    def display_footer(self, height, width):
        footer = "Press '?' for help."
        if self.search_results:
            footer = f"Search: {len(self.search_results)} matches. Use n/p to navigate, / for new search, f to filter, m/w/y to switch view."
        try:
            self.stdscr.addnstr(height - 1, max(0, width - len(footer) - 2), footer, len(footer))
        except curses.error:
            pass

    def open_file_in_editor(self, file_path: Path):
        editor = self.nvim_path or self.fallback_editor
        if not editor:
            self.display_error("No editor found. Install nvim, vi, or nano.")
            return
        try:
            obs_sock = "/tmp/obsidian.sock"
            command = [editor, "--server", obs_sock, "--remote", str(file_path)]
            tmux_cmd = [self.tmux_path, "select-window", "-t", "1"]
            subprocess.run(command, check=True)
            subprocess.run(tmux_cmd, check=True)
        except Exception as e:
            self.display_error(f"Editor error: {e}")

    def handle_input(self, key, height, width, file_path: Path, date_str: str) -> bool:
        if key == ord('q'):
            return False
        elif key == curses.KEY_RESIZE:
            return True
        elif key == curses.KEY_MOUSE:
            self.handle_mouse()
        elif key == ord('s'):
            self.show_week_stats(height, width)
        elif key in (ord('m'), ord('w'), ord('y')):
            self.current_view = {"m": "month", "w": "week", "y": "year"}[chr(key)]
            self.preview_scroll = 0
        elif key == ord('o'):
            self.is_side_by_side = not self.is_side_by_side
            self.preview_scroll = 0
            self.task_pane_focused = False
            self.timeblock_pane_focused = False
            self.preview_pane_focused = False
            self.selected_task_index = 0
            self.selected_timeblock_index = 0
            self.non_side_by_side_mode = "timeblock"
        elif key in (ord('h'), curses.KEY_LEFT):
            self.move_day(-1)
        elif key in (ord('l'), curses.KEY_RIGHT):
            self.move_day(1)
        elif key in (ord('j'), curses.KEY_DOWN):
            if self.task_pane_focused:
                self.move_task_selection(1)
            elif self.timeblock_pane_focused:
                self.move_timeblock_selection(1)
            else:
                self.move_week(1)
        elif key in (ord('k'), curses.KEY_UP):
            if self.task_pane_focused:
                self.move_task_selection(-1)
            elif self.timeblock_pane_focused:
                self.move_timeblock_selection(-1)
            else:
                self.move_week(-1)
        elif key == ord('/'):
            self.perform_search(height, width)
        elif key == ord('n'):
            self.navigate_search(1)
        elif key == ord('p'):
            self.navigate_search(-1)
        elif key == ord('f'):
            self.perform_tag_filter(height, width)
        elif key == ord('e'):
            self.edit_entry(file_path)
        elif key == ord('a'):
            self.add_note(file_path, date_str)
        elif key == ord('C'):
            self.create_new_task()
        elif key == ord('T'):
            add_default_timeblock(file_path)
        elif key == ord('t'):
            self.jump_to_today()
        elif key in (ord('M'), ord('W'), ord('P'), ord('I')):
            self.toggle_metadata(key, file_path)
        elif key == ord('L'):
            self.list_links(height, width, file_path)
        elif key == ord('?'):
            self.show_help(height, width)
        elif key in (ord('u'), ord('d'), ord('U'), ord('D')):
            self.scroll_preview(key)
        elif key == ord('0'):
            self.toggle_focus()
        elif key == ord('1'):
            self.non_side_by_side_mode = "timeblock"
            if self.is_side_by_side:
                self.show_tasks = False
                self.task_pane_focused = False
                self.timeblock_pane_focused = True
        elif key == ord('2'):
            self.non_side_by_side_mode = "tasks"
            if self.is_side_by_side:
                self.show_tasks = True
                self.task_pane_focused = True
                self.timeblock_pane_focused = False
        elif key == ord('3'):
            if not self.is_side_by_side:
                self.non_side_by_side_mode = "preview"
        elif key in (10, 13) and self.task_pane_focused:
            self.toggle_task()
        elif key in (10, 13) and self.timeblock_pane_focused:
            tb = timeblock_cache.get_timeblock(file_path)
            if 0 <= self.selected_timeblock_index < len(tb):
                t_sel, _ = tb[self.selected_timeblock_index]
                self.add_timeblock_entry(file_path, date_str, t_sel)
        elif key == ord('O') and self.task_pane_focused:
            self.open_selected_task()
        elif key == ord('R') and self.non_side_by_side_mode == "tasks":
            self.cycle_task_filter()
        elif key == ord('x') and self.task_pane_focused:
            self.delete_selected_task()
        elif key == ord('z') and self.task_pane_focused:
            self.cycle_selected_task_priority()
        return True

    def handle_mouse(self):
        try:
            _, mx, my, _, bstate = curses.getmouse()
            if bstate & curses.BUTTON4_PRESSED:
                self.move_day(-1)
            elif bstate & curses.BUTTON5_PRESSED:
                self.move_day(1)
        except Exception as e:
            logging.error(f"Mouse event error: {e}")

    def move_day(self, delta: int):
        self.selected_date += timedelta(days=delta)
        self.preview_scroll = 0

    def move_week(self, delta: int):
        self.selected_date += timedelta(weeks=delta)
        self.preview_scroll = 0

    def move_task_selection(self, delta: int):
        self.read_tasks_cache()
        max_idx = len(self.tasks_list) - 1
        self.selected_task_index = max(0, min(self.selected_task_index + delta, max_idx))

    def move_timeblock_selection(self, delta: int):
        date_str = self.selected_date.strftime("%Y-%m-%d")
        tb = timeblock_cache.get_timeblock(DIARY_DIR / f"{date_str}.md")
        if not tb:
            return
        max_idx = len(tb) - 1
        self.selected_timeblock_index = max(0, min(self.selected_timeblock_index + delta, max_idx))

    def perform_search(self, height, width):
        curses.echo()
        try:
            self.stdscr.addstr(height - 1, 2, "Search: ")
            self.stdscr.clrtoeol()
            query = self.stdscr.getstr(height - 1, 10, 100).decode("utf-8").strip()
        except Exception as e:
            logging.error(f"Search input error: {e}")
            query = ""
        curses.noecho()
        if query:
            self.search_list = search_diary(query)
            self.search_results = set(self.search_list)
            if self.search_list:
                self.current_search_idx = 0
                self.select_search_result()
        else:
            self.search_results = set()
            self.current_search_idx = -1

    def navigate_search(self, direction: int):
        if not self.search_list:
            return
        self.current_search_idx = (self.current_search_idx + direction) % len(self.search_list)
        self.select_search_result()

    def select_search_result(self):
        if 0 <= self.current_search_idx < len(self.search_list):
            try:
                self.selected_date = datetime.strptime(self.search_list[self.current_search_idx], "%Y-%m-%d")
                self.preview_scroll = 0
            except Exception as e:
                logging.error(f"Search result date parse error: {e}")

    def perform_tag_filter(self, height, width):
        curses.echo()
        try:
            self.stdscr.addstr(height - 1, 2, "Filter by tag: ")
            self.stdscr.clrtoeol()
            tag = self.stdscr.getstr(height - 1, 18, 50).decode("utf-8").strip()
        except Exception as e:
            logging.error(f"Tag filter input error: {e}")
            tag = ""
        curses.noecho()
        self.tag_results = filter_by_tag(tag) if tag else set()
        self.preview_scroll = 0

    def edit_entry(self, file_path: Path):
        if not file_path.exists():
            file_path.touch()
        curses.endwin()
        try:
            if self.nvim_path:
                obs_sock = os.path.expanduser("/tmp/obsidian.sock")
                command = [self.nvim_path, "--server", obs_sock, "--remote", str(file_path)]
                tmux_cmd = [self.tmux_path, "select-window", "-t", "1"]
                subprocess.run(command, check=True)
                subprocess.run(tmux_cmd, check=True)
            elif self.fallback_editor:
                subprocess.run([self.fallback_editor, str(file_path)], check=True)
            else:
                print("No editor found. Install nvim, vi, or nano.")
                input("Press Enter to continue...")
        except Exception as e:
            logging.error(f"Edit entry error: {e}")
        finally:
            self.stdscr = curses.initscr()
            curses.noecho()
            curses.cbreak()
            self.stdscr.keypad(True)
            curses.curs_set(0)

    def add_note(self, file_path: Path, date_str: str):
        try:
            curses.echo()
            self.stdscr.addstr(0, 2, "Enter note: ")
            self.stdscr.clrtoeol()
            note = self.stdscr.getstr(0, 14, 100).decode("utf-8").strip()
            curses.noecho()
            if note:
                now = datetime.now().strftime("%Y-%m-%dT%H:%M")
                with file_path.open("a", encoding="utf-8") as f:
                    f.write(f"- [{now}] {note}\n")
                metadata_cache.rewrite_front_matter(file_path, metadata_cache.get_metadata(file_path))
            self.stdscr.getch()
        except Exception as e:
            logging.error(f"Add note error: {e}")
        finally:
            curses.noecho()

    def create_new_task(self):
        curses.echo()
        try:
            self.stdscr.addstr(0, 1, "Task Title: ")
            self.stdscr.clrtoeol()
            title = self.stdscr.getstr(0, 14, 100).decode("utf-8").strip()
            if not title:
                return
            self.stdscr.addstr(0, 1, "Due Date (YYYY-MM-DD) [optional]: ")
            self.stdscr.clrtoeol()
            due = self.stdscr.getstr(0, 38, 20).decode("utf-8").strip()
            self.stdscr.addstr(0, 1, "Priority (low, normal, high) [normal]: ")
            self.stdscr.clrtoeol()
            priority = self.stdscr.getstr(0, 44, 10).decode("utf-8").strip() or "normal"
            self.stdscr.addstr(0, 1, "Extra Tags (comma separated) [optional]: ")
            self.stdscr.clrtoeol()
            tags_input = self.stdscr.getstr(0, 40, 50).decode("utf-8").strip()
            extra_tags = [tag.strip() for tag in tags_input.split(',') if tag.strip()] if tags_input else []
            # NEW: Prompt for recurrence rules.
            self.stdscr.addstr(0, 1, "Recurrence frequency (none/daily/weekly/monthly/yearly): ")
            self.stdscr.clrtoeol()
            freq = self.stdscr.getstr(0, 50, 10).decode("utf-8").strip().lower()  # use column index "fifty"
            recurrence = None
            if freq and freq != "none":
                recurrence = {"frequency": freq}
                if freq == "weekly":
                    self.stdscr.addstr(0, 1, "Days of week (e.g., mon,wed,fri): ")
                    self.stdscr.clrtoeol()
                    days_in = self.stdscr.getstr(0, 36, 20).decode("utf-8").strip()
                    recurrence["days_of_week"] = [d.strip().lower() for d in days_in.split(",") if d.strip()]
                elif freq in ("monthly", "yearly"):
                    self.stdscr.addstr(0, 1, "Day of month (e.g., 15): ")
                    self.stdscr.clrtoeol()
                    dom_in = self.stdscr.getstr(0, 28, 5).decode("utf-8").strip()
                    recurrence["day_of_month"] = int(dom_in) if dom_in.isdigit() else 1
            curses.noecho()
            created = self.task_manager.create_task(title, due if due else None, priority, extra_tags, recurrence)
            if created:
                self.display_error("Task created successfully.")
            else:
                self.display_error("Failed to create task.")
        except Exception as e:
            logging.error(f"Create task error: {e}")
        finally:
            curses.noecho()

    def toggle_task(self):
        self.read_tasks_cache()
        if not self.tasks_list:
            return
        if 0 <= self.selected_task_index < len(self.tasks_list):
            task = self.tasks_list[self.selected_task_index]
            filename_prefix = task.get("zettelid")
            for file in NOTES_DIR.glob(f"{filename_prefix}*.md"):
                if file.is_file():
                    self.task_manager.toggle_task_status(file)
                    break
            self.read_tasks_cache()

    def open_selected_task(self):
        self.read_tasks_cache()
        if not self.tasks_list:
            return
        if 0 <= self.selected_task_index < len(self.tasks_list):
            task = self.tasks_list[self.selected_task_index]
            filename_prefix = task.get("zettelid")
            for file in NOTES_DIR.glob(f"{filename_prefix}*.md"):
                if file.is_file():
                    self.open_file_in_editor(file)
                    break

    def cycle_task_filter(self):
        order = ["open", "in-progress", "done", "all"]
        try:
            idx = order.index(self.task_filter)
            self.task_filter = order[(idx + 1) % len(order)]
        except ValueError:
            self.task_filter = "open"
        self.selected_task_index = 0
        self.preview_scroll = 0

    def delete_selected_task(self):
        self.read_tasks_cache()
        if not self.tasks_list:
            return
        task = self.tasks_list[self.selected_task_index]
        filename_prefix = task.get("zettelid")
        task_title = task.get("title")
        for file in NOTES_DIR.glob(f"{filename_prefix}*.md"):
            if file.is_file():
                delete_confirm = f"Delete task '{task_title}' ({filename_prefix})? (y/n): "
                self.stdscr.addstr(0, 2, delete_confirm)
                self.stdscr.clrtoeol()
                self.stdscr.refresh()
                confirm = self.stdscr.getch()
                if confirm in (ord('y'), ord('Y')):
                    if self.task_manager.delete_task(file):
                        self.display_error("Task deleted successfully.")
                        self.selected_task_index = max(0, self.selected_task_index - 1)
                        self.read_tasks_cache()
                break

    def cycle_selected_task_priority(self):
        self.read_tasks_cache()
        if not self.tasks_list:
            return
        task = self.tasks_list[self.selected_task_index]
        filename_prefix = task.get("zettelid")
        for file in NOTES_DIR.glob(f"{filename_prefix}*.md"):
            if file.is_file():
                if self.task_manager.cycle_task_priority(file):
                    self.display_error("Task priority cycled.")
                break

    def add_timeblock_entry(self, file_path: Path, date_str: str, selected_time: str):
        try:
            curses.echo()
            prompt = f"Enter activity for {selected_time}: "
            self.stdscr.addstr(0, 2, prompt)
            self.stdscr.clrtoeol()
            activity = self.stdscr.getstr(0, len(prompt) + 2, 100).decode("utf-8").strip()
            curses.noecho()
            if activity:
                success, msg = timeblock_cache.update_timeblock(file_path, selected_time, activity)
                self.display_error(msg)
        except Exception as e:
            logging.error(f"Add timeblock entry error: {e}")
        finally:
            curses.noecho()

    def jump_to_today(self):
        self.selected_date = datetime.today()
        self.preview_scroll = 0

    def toggle_metadata(self, key, file_path: Path):
        md = metadata_cache.get_metadata(file_path)
        if key == ord('M'):
            md["meditate"] = not md.get("meditate", False)
        elif key == ord('W'):
            md["workout"] = not md.get("workout", False)
        elif key == ord('P'):
            md["pomodoros"] = int(md.get("pomodoros", 0)) + 1
        elif key == ord('I'):
            tags = md.get("tags", [])
            if "important" in tags:
                tags.remove("important")
            else:
                tags.append("important")
            md["tags"] = tags
        if not metadata_cache.rewrite_front_matter(file_path, md):
            logging.error(f"Failed rewriting metadata for {file_path}")

    def list_links(self, height, width, file_path: Path):
        text = get_diary_preview(file_path.stem)
        links = parse_links_from_text(text)
        chosen = draw_links_menu(self.stdscr, links)
        if chosen:
            display, target = chosen
            if re.match(r"^\d{4}-\d{2}-\d{2}$", target):
                try:
                    self.selected_date = datetime.strptime(target, "%Y-%m-%d")
                except Exception as e:
                    logging.error(f"Link date parse error: {e}")
            else:
                link_file = NOTES_DIR / f"{target}.md"
                self.open_file_in_editor(link_file)

    def show_help(self, height, width):
        help_text = [
            "Key Bindings:",
            "  h/LEFT   : Move left (day -1)",
            "  l/RIGHT  : Move right (day +1)",
            "  j/Down   : Move down one week / tasks/timeblock navigation",
            "  k/Up     : Move up one week / tasks/timeblock navigation",
            "  m/w/y    : Switch to Month/Week/Year view",
            "  o        : Toggle side-by-side layout",
            "  a        : Add note",
            "  C        : Create New Task (with recurrence support)",
            "  T        : Add empty timeblock template",
            "  e        : Edit diary entry",
            "  t        : Jump to today",
            "  /        : Search diary",
            "  n/p      : Navigate search results",
            "  f        : Filter by tag",
            "  M/W/P/I  : Toggle metadata (meditate/workout/pomodoros/important)",
            "  L        : List links",
            "  0        : Toggle focus between Tasks/Timeblock panes",
            "  1        : Show Timeblock view",
            "  2        : Show Tasks view",
            "  3        : Show Preview view (fullscreen only)",
            "  R        : Cycle task filter (open -> in-progress -> done -> all)",
            "  O        : Open selected task in editor",
            "  x        : Delete selected task (in Tasks view)",
            "  z        : Cycle task priority (in Tasks view)",
            "  Enter    : In Tasks view, toggle selected task status",
            "  Ctrl+P   : Command Palette",
            "  q        : Quit",
            "",
            "Press any key to close this help."
        ]
        popup_h = min(len(help_text) + 4, height - 2)
        popup_w = min(100, width - 4)
        start_y = (height - popup_h) // 2
        start_x = (width - popup_w) // 2
        win = curses.newwin(popup_h, popup_w, start_y, start_x)
        draw_rectangle(win, 0, 0, popup_h - 1, popup_w - 1)
        try:
            win.addstr(0, (popup_w - len(" Help ")) // 2, " Help ", curses.A_BOLD)
        except curses.error:
            pass
        for idx, line in enumerate(help_text, start=2):
            try:
                win.addstr(idx, 2, line)
            except curses.error:
                pass
        win.refresh()
        win.getch()
        del win

    def scroll_preview(self, key):
        if key == ord('u'):
            self.preview_scroll = max(0, self.preview_scroll - 1)
        elif key == ord('U'):
            self.preview_scroll = max(0, self.preview_scroll - 5)
        elif key == ord('d'):
            self.preview_scroll += 1
        elif key == ord('D'):
            self.preview_scroll += 5

    def toggle_focus(self):
        if self.is_side_by_side:
            if self.show_tasks:
                self.task_pane_focused = not self.task_pane_focused
                self.timeblock_pane_focused = False
            else:
                self.timeblock_pane_focused = not self.timeblock_pane_focused
                self.task_pane_focused = False
        else:
            if self.non_side_by_side_mode == "tasks":
                self.task_pane_focused = not self.task_pane_focused
                self.timeblock_pane_focused = False
            elif self.non_side_by_side_mode == "timeblock":
                self.timeblock_pane_focused = not self.timeblock_pane_focused
                self.task_pane_focused = False

    def start_refresh_thread(self):
        self.stop_refresh_thread()
        self.refresh_timer = threading.Timer(60.0, self.refresh_screen)
        self.refresh_timer.daemon = True
        self.refresh_timer.start()

    def stop_refresh_thread(self):
        if self.refresh_timer and self.refresh_timer.is_alive():
            self.refresh_timer.cancel()

    def refresh_screen(self):
        height, width = self.stdscr.getmaxyx()
        if height >= 10 and width >= 60:
            self.stdscr.clear()
            if self.is_side_by_side:
                self.draw_side_by_side_layout(height, width)
            else:
                self.draw_layout(height, width)
            self.draw_divider(height, width)
            date_str = self.selected_date.strftime("%Y-%m-%d")
            file_path = DIARY_DIR / f"{date_str}.md"
            preview_text = get_diary_preview(date_str)
            lines = preview_text.splitlines()
            if self.is_side_by_side:
                self.draw_preview_pane(height, width, lines)
                if self.show_tasks:
                    self.draw_tasks_pane(height, width)
                else:
                    self.draw_timeblock_pane(height, width)
            else:
                if self.non_side_by_side_mode == "preview":
                    self.draw_preview_pane_full(height, width, lines)
                elif self.non_side_by_side_mode == "tasks":
                    self.draw_tasks_pane_full(height, width)
                elif self.non_side_by_side_mode == "timeblock":
                    self.draw_timeblock_pane_full(height, width)
            self.display_status_bar(height, width)
            self.display_footer(height, width)
            self.stdscr.refresh()
        self.start_refresh_thread()

    # -----------------------------------------------------------------
    # COMMAND PALETTE
    # -----------------------------------------------------------------
    def show_command_palette(self, height, width):
        current_file = DIARY_DIR / f"{self.selected_date.strftime('%Y-%m-%d')}.md"
        commands = [
            ("Jump to Today", self.jump_to_today),
            ("Add Note", lambda: self.add_note(current_file, self.selected_date.strftime("%Y-%m-%d"))),
            ("Create New Task", self.create_new_task),
            ("Edit Diary Entry", lambda: self.edit_entry(current_file)),
            ("Toggle Meditate", lambda: self.toggle_metadata(ord('M'), current_file)),
            ("Toggle Workout", lambda: self.toggle_metadata(ord('W'), current_file)),
            ("Increment Pomodoros", lambda: self.toggle_metadata(ord('P'), current_file)),
            ("Toggle Important", lambda: self.toggle_metadata(ord('I'), current_file)),
            ("Switch to Month View", lambda: setattr(self, 'current_view', 'month')),
            ("Switch to Week View", lambda: setattr(self, 'current_view', 'week')),
            ("Switch to Year View", lambda: setattr(self, 'current_view', 'year')),
            ("Toggle Side-by-Side Layout", lambda: setattr(self, 'is_side_by_side', not self.is_side_by_side)),
            ("Open Home File", lambda: self.open_file_in_editor(HOME_FILE)),
            ("Search Diary", lambda: self.perform_search(height, width)),
            ("Filter by Tag", lambda: self.perform_tag_filter(height, width)),
            ("List Links", lambda: self.list_links(height, width, current_file))
        ]
        palette_h = min(len(commands) + 4, height - 4)
        palette_w = min(60, width - 4)
        start_y = max(0, (height - palette_h) // 2)
        start_x = max(0, (width - palette_w) // 2)
        win = curses.newwin(palette_h, palette_w, start_y, start_x)
        win.keypad(True)
        draw_rectangle(win, 0, 0, palette_h - 1, palette_w - 1)
        title = " Command Palette (Ctrl+P) "
        try:
            win.addstr(0, (palette_w - len(title)) // 2, title, curses.A_BOLD)
        except curses.error:
            pass
        selected = 0
        while True:
            for idx, (cmd_text, _) in enumerate(commands):
                mode = curses.A_REVERSE if idx == selected else curses.A_NORMAL
                try:
                    win.addstr(2 + idx, 2, cmd_text.ljust(palette_w - 4), mode)
                except curses.error:
                    pass
            win.refresh()
            key = win.getch()
            if key in (curses.KEY_UP, ord('k')):
                selected = (selected - 1) % len(commands)
            elif key in (curses.KEY_DOWN, ord('j')):
                selected = (selected + 1) % len(commands)
            elif key in (curses.KEY_ENTER, 10, 13):
                win.clear()
                win.refresh()
                try:
                    commands[selected][1]()
                except Exception as e:
                    logging.error(f"Error executing command '{commands[selected][0]}': {e}")
                break
            elif key in (27, ord('q')):
                break
        win.clear()
        self.stdscr.touchwin()
        self.stdscr.refresh()

# ---------------------------------------------------------------------
# CALENDAR DRAWING HELPERS
# ---------------------------------------------------------------------
def draw_single_month(stdscr, cal, year, month, start_x, start_y, highlight=None,
                      search_results=None, tag_results=None):
    month_name = calendar.month_name[month]
    title = f"{month_name} {year}"
    try:
        stdscr.addnstr(start_y, start_x, title.center(20), 20, curses.A_BOLD)
    except curses.error:
        pass
    dow = "Su Mo Tu We Th Fr Sa"
    try:
        stdscr.addnstr(start_y + 1, start_x, dow, 20, curses.A_BOLD)
    except curses.error:
        pass
    month_cal = cal.monthdayscalendar(year, month)
    offset = 2
    for week in month_cal:
        y = start_y + offset
        for idx, day in enumerate(week):
            if day == 0:
                continue
            col = start_x + idx * 3
            date_str = f"{year}-{month:02}-{day:02}"
            attr = get_date_attr(date_str, search_results, tag_results)
            if highlight and (year, month, day) == highlight:
                attr = curses.color_pair(2) | curses.A_BOLD
            try:
                stdscr.addnstr(y, col, f"{day:2}", 2, attr)
            except curses.error:
                pass
        offset += 1

def draw_week_view(stdscr, cal, selected_date, start_x, start_y, search_results=None, tag_results=None):
    dow = (selected_date.weekday() + 1) % 7
    start_week = selected_date - timedelta(days=dow)
    title = f"Week of {start_week.strftime('%Y-%m-%d')} (Sun -> Sat)"
    try:
        stdscr.addnstr(start_y, start_x, title, 50, curses.A_BOLD)
    except curses.error:
        pass
    for i in range(7):
        day = start_week + timedelta(days=i)
        label = f"{day.strftime('%a')} {day.day}"
        attr = get_date_attr(day.strftime("%Y-%m-%d"), search_results, tag_results)
        if day.date() == selected_date.date():
            attr = curses.color_pair(2) | curses.A_BOLD
        try:
            stdscr.addnstr(start_y + 2, start_x + i * 12, label, 12, attr)
        except curses.error:
            pass

def draw_year_view(stdscr, cal, year, start_x, start_y, highlight=None, search_results=None, tag_results=None):
    mini_w = 20
    mini_h = 8
    for m in range(1, 13):
        row = (m - 1) // 3
        col = (m - 1) % 3
        x = start_x + col * (mini_w + 3)
        y = start_y + row * (mini_h + 2)
        title = f"{calendar.month_abbr[m]} {year}"
        try:
            stdscr.addnstr(y, x, title.center(18), 18, curses.A_BOLD)
            stdscr.addnstr(y + 1, x, "Su Mo Tu We Th Fr Sa", 20, curses.A_BOLD)
        except curses.error:
            pass
        month_cal = cal.monthdayscalendar(year, m)
        offset = y + 2
        for week in month_cal:
            for idx, day in enumerate(week):
                if day == 0:
                    continue
                date_str = f"{year}-{m:02}-{day:02}"
                attr = get_date_attr(date_str, search_results, tag_results)
                if highlight and (year, m, day) == highlight:
                    attr = curses.color_pair(2) | curses.A_BOLD
                try:
                    stdscr.addnstr(offset, x + idx * 3, f"{day:2}", 2, attr)
                except curses.error:
                    pass
            offset += 1

def get_date_attr(date_str, search_results, tag_results):
    file_path = DIARY_DIR / f"{date_str}.md"
    if file_path.exists():
        md = metadata_cache.get_metadata(file_path)
        tags = md.get("tags", [])
        if "important" in tags:
            return curses.color_pair(5) | curses.A_BOLD
        if tag_results and date_str in tag_results:
            return curses.color_pair(4) | curses.A_BOLD
        if search_results and date_str in search_results:
            return curses.color_pair(3) | curses.A_BOLD
        return curses.color_pair(1) | curses.A_BOLD
    return curses.A_NORMAL

# ---------------------------------------------------------------------
# MAIN FUNCTION
# ---------------------------------------------------------------------
def main(stdscr):
    tui = DiaryTUI(stdscr)
    tui.run()

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except Exception as e:
        logging.critical(f"Unhandled exception: {e}")
        sys.exit(1)

