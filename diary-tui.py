#!/usr/bin/env python3
"""
CALENDAR/TIME-MANAGING/VIEWING SCRIPT

Features:
  - Daily diary entries with YAML frontmatter metadata.
  - Tasks and timeblock editing/updating (including adding an empty timeblock template).
  - Multiple calendar views: year, month, week.
  - Search and tag filtering.
  - Side-by-side and fullscreen modes for preview, tasks, and timeblock views.
  - Obsidian-style link parsing and integration with your editor.
  - Live screen refresh and mouse support.
  - A context‑aware command palette (Ctrl+P) for quick commands.
  - Robust error handling with logging.

Dependencies: curses, yaml
"""

import threading
import time
import curses
import calendar
import subprocess
import shutil
import re
import yaml
import os
import sys
import logging
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
    "diary_dir": "/home/calluma/Dropbox/notes/diary",
    "notes_dir": "/home/calluma/Dropbox/notes",
    "tasks_file": "/home/calluma/Dropbox/notes/o7qtm.md",
    "home_file": "/home/calluma/Dropbox/notes/home.md",
    "log_file": "/tmp/calendar_tui.log",
    "editor": "nvim"  # Or leave empty for auto-detection, or specify "vi", "nano" etc.
}

def load_config():
    """Loads configuration from ~/.config/diary-tui/config.yaml,
       or uses default values if the file is not found or incomplete.
    """
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
TASKS_FILE = Path(CONFIG["tasks_file"])
HOME_FILE = Path(CONFIG["home_file"])
LOG_FILE = Path(CONFIG["log_file"])
EDITOR_CONFIG = CONFIG.get("editor", "").strip() # Get editor from config, might be empty string

logging.basicConfig(filename=LOG_FILE, level=logging.DEBUG,
                    format='%(asctime)s [%(levelname)s] %(message)s')

# ---------------------------------------------------------------------
# YAML FRONTMATTER UTILS
# ---------------------------------------------------------------------
class MetadataCache:
    def __init__(self):
        self.cache = {}
        self.file_hashes = {}

    def get_metadata(self, file_path: Path) -> dict:
        if not file_path.exists():
            return {}
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

    def get_timeblock(self, file_path: Path):
        if not file_path.exists():
            return []
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
            # return True, "Timeblock updated successfully."
        except Exception as e:
            logging.error(f"Error updating timeblock in {file_path}: {e}")
            return False, f"Error writing file: {e}"

timeblock_cache = TimeblockCache()

def add_default_timeblock(file_path: Path):
    """Adds an empty timeblock template if none exists."""
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
# HELPER FUNCTIONS
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

def parse_tasks(file_path: Path):
    if not file_path.exists():
        return (0, 0)
    try:
        with file_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        logging.error(f"Error parsing tasks {file_path}: {e}")
        return (0, 0)
    total = 0
    completed = 0
    for line in lines:
        if line.strip().startswith("- [ ]"):
            total += 1
        elif line.strip().lower().startswith("- [x]"):
            completed += 1
    return completed, total

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
# DIARY TUI CLASS (with Command Palette)
# ---------------------------------------------------------------------
class DiaryTUI:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()
        # Color pairs
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, -1, curses.COLOR_CYAN)
        curses.init_pair(3, curses.COLOR_GREEN, -1)
        curses.init_pair(4, curses.COLOR_MAGENTA, -1)
        curses.init_pair(5, curses.COLOR_RED, -1)
        curses.init_pair(6, curses.COLOR_YELLOW, -1)
        curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(8, curses.COLOR_BLACK, -1)
        curses.init_pair(9, curses.COLOR_YELLOW, curses.COLOR_BLACK)
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
        self.tasks_cache = {}
        self.task_pane_focused = False
        self.timeblock_pane_focused = False
        self.preview_pane_focused = False # Not focusable by '0' anymore
        self.selected_task_index = 0
        self.selected_timeblock_index = 0
        self.show_tasks = True # In side-by-side, show tasks by default, else timeblock
        self.non_side_by_side_mode = "timeblock"  # "preview", "tasks", "timeblock"
        self.calendar_height_non_side = 0
        self.calendar_height_side = 0
        self.refresh_timer = None

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
            # Draw status bar (second to last line)
            self.display_status_bar(height, width)
            # Draw footer (last line)
            self.display_footer(height, width)
            self.stdscr.refresh()
            key = self.stdscr.getch()
            # Ctrl+P (ASCII 16) launches the command palette
            if key == 16:
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
        """Displays a dynamic status bar on the second-to-last line."""
        # Compute weekly stats
        week_start = self.get_week_start()
        stats = calculate_week_stats_from_date(week_start)
        # Get tasks info
        comp, tot = parse_tasks(TASKS_FILE)
        # Determine focus
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
        status_text = (f" Date: {self.selected_date.strftime('%Y-%m-%d')} |  "
                       f"Tasks: {comp}/{tot} | Pomodoros: {stats['total_pomodoros']} | "
                       f"Workouts: {stats['total_workouts']} | Meditated: {stats['days_meditated']} | "
                       f"Focus: {focus} | View: {self.current_view} ")
        try:
            self.stdscr.addnstr(0, 0, status_text.ljust(width), width, curses.A_REVERSE)
        except curses.error:
            pass
    def display_minimum_size_warning(self, height, width):
        warning = "Terminal too small. Resize or press 'q' to quit."
        try:
            self.stdscr.addnstr(height // 2, max(0, (width - len(warning)) // 2), warning, len(warning), curses.A_BOLD)
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

    def draw_tasks_pane(self, height, width):
        tasks_y = self.calendar_height_side + 3
        tasks_x = 2
        available_height = height - tasks_y - 1
        available_width = (width // 2) - 4
        self.read_tasks_cache()
        if self.tasks_cache.get("lines"):
            for idx, line in enumerate(self.tasks_cache["lines"][self.preview_scroll:self.preview_scroll + available_height]):
                attr = curses.color_pair(6) | curses.A_BOLD if (self.task_pane_focused and (idx + self.preview_scroll) == self.selected_task_index) else curses.A_NORMAL
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
        if self.tasks_cache.get("lines"):
            for idx, line in enumerate(self.tasks_cache["lines"][self.preview_scroll:self.preview_scroll + available_height]):
                attr = curses.color_pair(6) | curses.A_BOLD if (self.task_pane_focused and (idx + self.preview_scroll) == self.selected_task_index) else curses.A_NORMAL
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

    def read_tasks_cache(self):
        mod_time = TASKS_FILE.stat().st_mtime if TASKS_FILE.exists() else 0
        if self.tasks_cache.get("file_mod") != mod_time:
            tasks = []
            try:
                with TASKS_FILE.open("r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip().startswith("- [ ]") or line.strip().startswith("- [x]"):
                            tasks.append(line.rstrip())
            except Exception as e:
                logging.error(f"Error reading tasks file: {e}")
                tasks = []
            self.tasks_cache = {"lines": tasks, "file_mod": mod_time}

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
            self.tasks_cache = {}
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
        elif key == ord('A'):
            self.add_task()
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
        elif key == ord('1'): # Timeblock view
            self.non_side_by_side_mode = "timeblock"
            if self.is_side_by_side:
                self.show_tasks = False
                self.task_pane_focused = False
                self.timeblock_pane_focused = True
        elif key == ord('2'): # Tasks view
            self.non_side_by_side_mode = "tasks"
            if self.is_side_by_side:
                self.show_tasks = True
                self.task_pane_focused = True
                self.timeblock_pane_focused = False
        elif key == ord('3'): # Preview view (only fullscreen)
            if not self.is_side_by_side:
                self.non_side_by_side_mode = "preview"
        elif key in (10, 13) and self.task_pane_focused:
            self.toggle_task()
        elif key in (10, 13) and self.timeblock_pane_focused:
            tb = timeblock_cache.get_timeblock(file_path)
            if 0 <= self.selected_timeblock_index < len(tb):
                t_sel, _ = tb[self.selected_timeblock_index]
                self.add_timeblock_entry(file_path, date_str, t_sel)
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
        if not self.tasks_cache.get("lines"):
            return
        max_idx = len(self.tasks_cache["lines"]) - 1
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

    def add_task(self):
        try:
            curses.echo()
            self.stdscr.addstr(0, 2, "Enter task: ")
            self.stdscr.clrtoeol()
            task = self.stdscr.getstr(0, 14, 100).decode("utf-8").strip()
            curses.noecho()
            if task:
                with TASKS_FILE.open("a", encoding="utf-8") as f:
                    f.write(f"- [ ] {task}\n")
            self.read_tasks_cache()
            return True, "Task added successfully."
        except Exception as e:
            logging.error(f"Add task error: {e}")
        finally:
            curses.noecho()

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
            "  A        : Add task",
            "  T        : Add empty timeblock template",
            "  e        : Edit entry",
            "  t        : Jump to today",
            "  /        : Search",
            "  n/p      : Navigate search results",
            "  f        : Filter by tag",
            "  M/W/P/I  : Toggle metadata (meditate/workout/pomodoros/important)",
            "  L        : List links",
            "  0        : Toggle focus between Tasks/Timeblock panes",
            "  1        : Show Timeblock view",
            "  2        : Show Tasks view",
            "  3        : Show Preview view (fullscreen only)",
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
            # Preview pane is never focused by '0' in fullscreen mode

    def toggle_task(self):
        if not self.task_pane_focused or not self.tasks_cache.get("lines"):
            return
        idx = self.selected_task_index
        task_line = self.tasks_cache["lines"][idx]
        if task_line.startswith("- [ ]"):
            new_line = "- [x]" + task_line[5:]
        elif task_line.startswith("- [x]"):
            new_line = "- [ ]" + task_line[5:]
        else:
            return
        self.tasks_cache["lines"][idx] = new_line
        try:
            with TASKS_FILE.open("r", encoding="utf-8") as f:
                all_lines = f.readlines()
            task_idx = 0
            new_all = []
            for line in all_lines:
                if line.strip().startswith("- [ ]") or line.strip().startswith("- [x]"):
                    if task_idx == idx:
                        new_all.append(new_line + "\n")
                    else:
                        new_all.append(line)
                    task_idx += 1
                else:
                    new_all.append(line)
            with TASKS_FILE.open("w", encoding="utf-8") as f:
                f.writelines(new_all)
        except Exception as e:
            logging.error(f"Toggle task error: {e}")

    def show_week_stats(self, height, width):
        week_start = self.get_week_start()
        stats = calculate_week_stats_from_date(week_start)
        popup_w, popup_h = 50, 10
        start_y, start_x = (height - popup_h) // 2, (width - popup_w) // 2
        win = curses.newwin(popup_h, popup_w, start_y, start_x)
        win.border()
        try:
            win.addstr(0, (popup_w - len(" Weekly Statistics ")) // 2, " Weekly Statistics ", curses.A_BOLD)
        except curses.error:
            pass
        lines = [
            f"Week: {stats['week_start']} to {stats['week_end']}",
            "",
            f"Total Pomodoros: {stats['total_pomodoros']}",
            f"Total Workouts : {stats['total_workouts']}",
            f"Days Meditated : {stats['days_meditated']}",
            "",
            "Press any key..."
        ]
        for idx, line in enumerate(lines, start=1):
            try:
                win.addstr(idx, 2, line)
            except curses.error:
                pass
        win.refresh()
        win.getch()
        del win

    def get_week_start(self) -> datetime:
        delta = (self.selected_date.weekday() + 1) % 7
        return self.selected_date - timedelta(days=delta)

    def display_error(self, message: str):
        height, width = self.stdscr.getmaxyx()
        popup_h, popup_w = 5, min(width - 4, len(message) + 4)
        start_y, start_x = (height - popup_h) // 2, (width - popup_w) // 2
        win = curses.newwin(popup_h, popup_w, start_y, start_x)
        win.border()
        try:
            win.addstr(1, 2, message, curses.A_BOLD)
        except curses.error:
            pass
        win.refresh()
        win.getch()
        del win

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
        """
        Displays a command palette overlay (triggered by Ctrl+P) that
        allows the user to choose from a list of context-aware commands.
        """
        # Define commands as a list of tuples: (display text, function to call)
        # Many commands are implemented as lambdas using the current date entry.
        current_file = DIARY_DIR / f"{self.selected_date.strftime('%Y-%m-%d')}.md"
        commands = [
            ("Jump to Today", self.jump_to_today),
            ("Add Note", lambda: self.add_note(current_file, self.selected_date.strftime("%Y-%m-%d"))),
            ("Add Task", self.add_task),
            ("Edit Entry", lambda: self.edit_entry(current_file)),
            ("Toggle Meditate", lambda: self.toggle_metadata(ord('M'), current_file)),
            ("Toggle Workout", lambda: self.toggle_metadata(ord('W'), current_file)),
            ("Increment Pomodoros", lambda: self.toggle_metadata(ord('P'), current_file)),
            ("Toggle Important", lambda: self.toggle_metadata(ord('I'), current_file)),
            ("Switch to Month View", lambda: setattr(self, 'current_view', 'month')),
            ("Switch to Week View", lambda: setattr(self, 'current_view', 'week')),
            ("Switch to Year View", lambda: setattr(self, 'current_view', 'year')),
            ("Toggle Side-by-Side Layout", lambda: setattr(self, 'is_side_by_side', not self.is_side_by_side)),
            ("Open Home File", lambda: self.open_file_in_editor(HOME_FILE)),
            ("Open Tasks File", lambda: self.open_file_in_editor(TASKS_FILE)),
            ("Search Diary", lambda: self.perform_search(height, width)),
            ("Filter by Tag", lambda: self.perform_tag_filter(height, width)),
            ("List Links", lambda: self.list_links(height, width, current_file))
        ]
        # Create a palette window
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
                # Execute the selected command
                win.clear()
                win.refresh()
                # Execute the function
                try:
                    commands[selected][1]()
                except Exception as e:
                    logging.error(f"Error executing command '{commands[selected][0]}': {e}")
                break
            elif key in (27, ord('q')):
                break
        # Clear the palette window
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

