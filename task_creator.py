#!/usr/bin/env python3
"""
Even BETTER Curses Task Creation Script (based on diary-tui.py), using same config with input validation, confirmation, line highlight, mouse & MORE! - Further Improved
"""
import curses
import yaml
import json
import os
import sys
import logging
import random
import string
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------
# CONFIGURATION (From diary-tui.py - same as before)
# ---------------------------------------------------------------------
CONFIG_DIR = Path.home() / ".config" / "diary-tui"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

DEFAULT_CONFIG = {
    "diary_dir": str(Path.home() / "diary"),
    "notes_dir": str(Path.home() / "notes"),
    "home_file": str(Path.home() / "notes" / "home.md"),
    "log_file": "/tmp/calendar_tui.log",
    "editor": "nvim"
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
NOTES_DIR = Path(CONFIG["notes_dir"])

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')

# ---------------------------------------------------------------------
# Simplified TaskManager (only create_task - same as before)
# ---------------------------------------------------------------------
class TaskManager:
    def __init__(self, notes_dir: Path):
        self.notes_dir = notes_dir

    def create_task(self, title, due=None, priority="normal", extra_tags=None, recurrence_data: dict = None, contexts=None):
        """Creates a new task markdown file with YAML frontmatter."""
        date_prefix = datetime.now().strftime("%y%m%d")
        suffix = ''.join(random.choices(string.ascii_lowercase, k=3))
        filename = f"{date_prefix}{suffix}.md"
        zettelid = filename[:-3]
        file_path = self.notes_dir / filename
        now_dt = datetime.now()
        now_str = now_dt.strftime("%Y-%m-%dT%H:%M:%S")
        frontmatter = {
            "title": title,
            "zettelid": zettelid,
            "date": now_str,
            "dateModified": now_str,
            "status": "open",
            "due": due,
            "tags": ["task"] + (extra_tags if extra_tags else []),
            "priority": priority,
            "contexts": contexts if contexts else []
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
            self.notes_dir.mkdir(parents=True, exist_ok=True)
            with file_path.open("w", encoding="utf-8") as f:
                f.write(content)
            logging.info(f"Created task note: {file_path}")
            return file_path
        except Exception as e:
            logging.error(f"Error creating task note: {e}")
            return None

# ---------------------------------------------------------------------
# CURSES UI FOR TASK CREATION FORM (Even BETTER!) - REFACTORED & IMPROVED
# ---------------------------------------------------------------------
def draw_rectangle(win, y1, x1, y2, x2):
    # Removed border drawing
    pass

def _draw_form_frame(form_win, title_text):
    """Draws the form frame and title."""
    form_win.clear()
    # draw_rectangle(form_win, 0, 0, form_win.getmaxyx()[0] - 1, form_win.getmaxyx()[1] - 1) # Removed border call
    try:
        form_win.addstr(0, (form_win.getmaxyx()[1] - len(title_text)) // 2, title_text, curses.A_BOLD | curses.color_pair(3))
    except curses.error:
        pass

def _draw_text_field(form_win, y, label, value, placeholder, is_current_field, form_width, instruction=None, error=False):
    """Draws a text input field with optional instruction and error highlighting."""
    try:
        form_win.addstr(y, 2, f"{label}: ", curses.color_pair(2))
    except curses.error:
        pass
    line_attr = curses.A_NORMAL
    if is_current_field:
        line_attr = curses.color_pair(1)
        form_win.chgat(y, 0, form_width - 2, line_attr)
    if error and is_current_field: # Highlight error in current field
        line_attr = curses.color_pair(5) # Error color
        form_win.chgat(y, 0, form_width - 2, line_attr)

    display_value = value if value else placeholder
    attr = curses.A_REVERSE if is_current_field else curses.A_NORMAL
    if not value and placeholder:
        attr |= curses.A_DIM
    if error and is_current_field:
        attr = curses.A_REVERSE | curses.color_pair(5) # Error color for input

    try:
        form_win.addnstr(y, 2 + len(label) + 1, display_value, form_width - (4 + len(label) + 1), attr | line_attr | curses.color_pair(4))
    except curses.error:
        pass

    if instruction and is_current_field:
        try:
            form_win.addstr(y + 1, 4, instruction, curses.A_DIM | curses.color_pair(4)) # Instruction below, dim
        except curses.error:
            pass


def _draw_dropdown_field(form_win, y, label, value, options, is_current_field, form_width):
    """Draws a dropdown field."""
    try:
        form_win.addstr(y, 2, f"{label}: ", curses.color_pair(2))
    except curses.error:
        pass
    line_attr = curses.A_NORMAL
    if is_current_field:
        line_attr = curses.color_pair(1)
        form_win.chgat(y, 0, form_width - 2, line_attr)
    current_value_display = value
    try:
        form_win.addnstr(y, 2 + len(label) + 1, current_value_display, form_width - (4 + len(label) + 1), curses.A_REVERSE if is_current_field else curses.A_NORMAL | line_attr | curses.color_pair(4))
    except curses.error:
        pass

def _draw_checkboxes_field(form_win, y_start, label, value, options, is_current_field, current_checkbox_index):
    """Draws a checkboxes field."""
    try:
        form_win.addstr(y_start, 2, f"{label}: ", curses.color_pair(2))
    except curses.error:
        pass
    line_attr = curses.A_NORMAL
    if is_current_field:
        line_attr = curses.color_pair(1)
        form_win.chgat(y_start, 0, form_win.getmaxyx()[1] - 2, line_attr) # Highlight whole line
    for j, option in enumerate(options):
        mark_char = "x" if option in value else " "
        checkbox_display = f"[{mark_char}]{option}"
        attr = curses.A_NORMAL
        if is_current_field and j == current_checkbox_index:
            checkbox_display = f">> {checkbox_display} <<" # More visual selection
            attr = curses.A_BOLD | curses.color_pair(1) # Highlight selected checkbox option
        try:
            form_win.addstr(y_start + 1, 4 + j * 8, checkbox_display, attr | line_attr | curses.color_pair(4))
        except curses.error:
            pass

def show_confirmation_dialog(stdscr, task_info):
    """Shows a confirmation dialog before creating the task (improved)."""
    dialog_height = 14 # Increased height
    dialog_width = 60
    start_y = max(0, (stdscr.getmaxyx()[0] - dialog_height) // 2)
    start_x = max(0, (stdscr.getmaxyx()[1] - dialog_width) // 2)
    dialog_win = curses.newwin(dialog_height, dialog_width, start_y, start_x)
    dialog_win.keypad(True)
    # draw_rectangle(dialog_win, 0, 0, dialog_height - 1, dialog_width - 1) # Removed border call

    lines = [
        "Confirm Task Creation?",
        "",
        "Task Details:", # Clearer section title
        f"  Title: {task_info['title']}",
        f"  Due Date: {task_info['due'] or 'None'}",
        f"  Priority: {task_info['priority']}",
        f"  Contexts: {', '.join(task_info['contexts']) or 'None'}", # Show contexts
        f"  Extra Tags: {', '.join(task_info['extra_tags']) or 'None'}", # Show extra tags
        "",
        " [Confirm]   [Cancel] "
    ]

    selected_button = 0 # 0 for Confirm, 1 for Cancel

    while True:
        dialog_win.clear()
        # draw_rectangle(dialog_win, 0, 0, dialog_height - 1, dialog_width - 1) # Removed border call
        for i, line in enumerate(lines):
            try:
                dialog_win.addstr(i + 1, (dialog_width - len(line)) // 2, line, curses.color_pair(4) if i > 1 else curses.A_BOLD | curses.color_pair(3)) # Title bold cyan, details white
            except curses.error:
                pass

        # Highlight selected button (more distinct highlight)
        confirm_attr = curses.A_REVERSE | curses.color_pair(1) if selected_button == 0 else curses.A_NORMAL
        cancel_attr = curses.A_REVERSE | curses.color_pair(1) if selected_button == 1 else curses.A_NORMAL
        try:
            dialog_win.addstr(dialog_height - 2, (dialog_width // 2) - 10, "[Confirm]", confirm_attr)
            dialog_win.addstr(dialog_height - 2, (dialog_width // 2) + 2, "[Cancel]", cancel_attr)
        except curses.error:
            pass

        dialog_win.refresh()
        key = dialog_win.getch()
        if key == 9: # Tab
            selected_button = 1 - selected_button
        elif key == curses.KEY_LEFT or key == curses.KEY_RIGHT:
            selected_button = 1 - selected_button
        elif key in (curses.KEY_ENTER, 10, 13):
            return selected_button == 0
        elif key == 27: # Esc
            return False

def show_task_creation_form(stdscr, task_manager):
    height, width = stdscr.getmaxyx()
    form_height = 23
    form_width = 70
    start_y = max(0, (height - form_height) // 2)
    start_x = max(0, (width - form_width) // 2)
    form_win = curses.newwin(form_height, form_width, start_y, start_x)
    form_win.keypad(True)
    curses.curs_set(0)
    curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)

    fields = [
        {"label": "Title", "type": "text", "value": "", "placeholder": "Enter task title", "help": "Task title (required)"},
        {"label": "Due Date (YYYY-MM-DD)", "type": "text", "value": "", "placeholder": "YYYY-MM-DD (optional)", "instruction": "Format: YYYY-MM-DD", "help": "Due date in YYYY-MM-DD format", "error": False}, # Added error flag
        {"label": "Priority", "type": "dropdown", "options": ["low", "normal", "high"], "value": "normal", "help": "Task priority level"},
        {"label": "Context Tags (comma-separated)", "type": "text", "value": "", "placeholder": "tag1, tag2, ... (optional)", "help": "Comma-separated context tags"},
        {"label": "Extra Tags (comma-separated)", "type": "text", "value": "", "placeholder": "tag1, tag2, ... (optional)", "help": "Comma-separated extra tags"},
        {"label": "Recurrence Frequency", "type": "dropdown", "options": ["none", "daily", "weekly", "monthly", "yearly"], "value": "none", "help": "Task recurrence frequency"},
        {"label": "Day of Month (for monthly/yearly, 1-31)", "type": "text", "value": "", "placeholder": "1-31 (optional)", "instruction": "For monthly/yearly recurrence", "help": "Day of month for recurrence", "error": False}, # Added error flag
        {"label": "Days of Week (for weekly, mon,tue,...)", "type": "checkboxes", "options": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "value": [], "instruction": "For weekly recurrence", "help": "Days of week for weekly recurrence"},
    ]
    current_field_index = 0
    current_checkbox_index = 0
    message = ""
    help_line = ""
    error_in_form = False # Flag to track if there's any error in the form

    while True:
        _draw_form_frame(form_win, " Create New Task ") # Draw frame and title
        y_offset = 2
        error_in_form = False # Reset error flag for each redraw
        for i, field in enumerate(fields):
            if field["type"] == "text":
                _draw_text_field(form_win, y_offset + i, field["label"], field["value"], field["placeholder"], i == current_field_index, form_width, instruction=field.get("instruction"), error=field.get("error", False)) # Pass instruction and error flag
                if field.get("error", False):
                    error_in_form = True # Set form error flag if any field has error
                    field["error"] = False # Reset error flag after drawing
            elif field["type"] == "dropdown":
                _draw_dropdown_field(form_win, y_offset + i, field["label"], field["value"], field["options"], i == current_field_index, form_width)
            elif field["type"] == "checkboxes":
                _draw_checkboxes_field(form_win, y_offset + i, field["label"], field["value"], field["options"], i == current_field_index, current_checkbox_index)
                y_offset += 1 # Checkboxes are 2 lines tall
            if i == current_field_index:
                help_line = field.get("help", "") # Dynamic help line

        # Visual cue if there are errors in the form
        create_task_text_attr = curses.A_REVERSE if current_field_index == len(fields) else curses.A_NORMAL
        if error_in_form:
            create_task_text_attr = curses.A_REVERSE | curses.color_pair(5) if current_field_index == len(fields) else curses.A_NORMAL | curses.color_pair(5) # Red if error

        try:
            form_win.addstr(form_win.getmaxyx()[0] - 4, 4, "[Create Task]", create_task_text_attr)
            form_win.addstr(form_win.getmaxyx()[0] - 4, 20, "[Cancel]", curses.A_REVERSE if current_field_index == len(fields)+1 else curses.A_NORMAL)
            if message:
                form_win.addstr(form_win.getmaxyx()[0] - 6, 2, message, curses.A_BOLD | curses.color_pair(5))
            form_win.addstr(form_win.getmaxyx()[0] - 1, 2, help_line, curses.A_DIM) # Help line at bottom
        except curses.error:
            pass

        form_win.refresh()
        key = form_win.getch()
        message = ""
        help_line = ""

        if key == 9 or key == 14:
            current_field_index = (current_field_index + 1) % (len(fields) + 2)
            if 0 <= current_field_index - 1 < len(fields) and fields[current_field_index-1]["type"] == "checkboxes":
                current_checkbox_index = 0
        elif key == curses.KEY_BTAB or key == 353 or key == 16:
            current_field_index = (current_field_index - 1) % (len(fields) + 2)
            if 0 <= current_field_index < len(fields) and fields[current_field_index]["type"] == "checkboxes":
                current_checkbox_index = 0
        elif key in (curses.KEY_ENTER, 10, 13):
            if current_field_index == len(fields):
                task_data = {f['label']: f['value'] for f in fields}

                # --- Input Validation --- (same as before but improved messages & UI feedback)
                due_date_str = task_data['Due Date (YYYY-MM-DD)']
                if due_date_str:
                    try:
                        datetime.strptime(due_date_str, '%Y-%m-%d')
                    except ValueError:
                        message = "Invalid Date Format." # More concise error message
                        for field in fields: # Set error flag for the field
                            if field["label"] == "Due Date (YYYY-MM-DD)":
                                field["error"] = True
                        continue

                recurrence_freq = task_data['Recurrence Frequency']
                if recurrence_freq in ('monthly', 'yearly'):
                    day_of_month_str = task_data['Day of Month (for monthly/yearly, 1-31)']
                    if not day_of_month_str.isdigit() or not 1 <= int(day_of_month_str) <= 31:
                        message = "Day of Month must be 1-31." # More concise error
                        for field in fields:
                            if field["label"] == "Day of Month (for monthly/yearly, 1-31)":
                                field["error"] = True
                        continue
                    else: # Clear error if previously set and now valid
                        for field in fields:
                            if field["label"] == "Day of Month (for monthly/yearly, 1-31)":
                                field["error"] = False # Clear error

                if not task_data['Title'].strip():
                    message = "Task Title cannot be empty."
                    continue
                else: # Clear error implicitly by moving away from title field if it was empty
                    pass # No specific field to mark error on, as title is always visible. Error message sufficient

                task_data['Context Tags (comma-separated)'] = [ctx.strip() for ctx in task_data['Context Tags (comma-separated)'].split(',') if ctx.strip()]
                task_data['Extra Tags (comma-separated)'] = [tag.strip() for tag in task_data['Extra Tags (comma-separated)'].split(',') if tag.strip()]


                recurrence_data = None
                if recurrence_freq != 'none':
                    recurrence_data = {"frequency": recurrence_freq}
                    if recurrence_data['frequency'] == 'weekly':
                        recurrence_data['days_of_week'] = task_data['Days of Week (for weekly, mon,tue,...)']
                    elif recurrence_data['frequency'] in ('monthly', 'yearly'):
                        recurrence_data['day_of_month'] = int(task_data['Day of Month (for monthly/yearly, 1-31)'])

                task_info = {
                    'title': task_data['Title'].strip(),
                    'due': due_date_str if due_date_str else None,
                    'priority': task_data['Priority'],
                    'extra_tags': task_data['Extra Tags (comma-separated)'],
                    'contexts': task_data['Context Tags (comma-separated)'],
                    'recurrence_data': recurrence_data
                }

                if not error_in_form: # Only proceed if there are no errors in the form
                    if show_confirmation_dialog(stdscr, task_info):
                        return task_info
                    else:
                        continue
                else:
                    message = "Please correct highlighted fields." # Generic error if any field has error
                    continue # Stay in the form to correct errors


            elif current_field_index == len(fields)+1:
                break
        elif key == 27:
            break
        elif key == curses.KEY_MOUSE:
            try:
                _, mx, my, _, _ = curses.getmouse()
                relative_y = my - start_y - 2
                if 0 <= relative_y < len(fields):
                    current_field_index = relative_y
            except curses.error:
                pass
        elif 0 <= current_field_index < len(fields):
            field = fields[current_field_index]
            if field["type"] == "text":
                if key == curses.KEY_BACKSPACE or key == 127 or key == 8:
                    field["value"] = field["value"][:-1]
                elif 32 <= key <= 126:
                    field["value"] += chr(key)
                field["error"] = False # Clear error when user starts typing in the field
            elif field["type"] == "dropdown":
                if key in (curses.KEY_DOWN, ord('j')):
                    current_option_index = field["options"].index(field["value"])
                    field["value"] = field["options"][(current_option_index + 1) % len(field["options"])]
                elif key in (curses.KEY_UP, ord('k')):
                    current_option_index = field["options"].index(field["value"])
                    field["value"] = field["options"][(current_option_index - 1) % len(field["options"])]
            elif field["type"] == "checkboxes":
                if key in (curses.KEY_LEFT, ord('h')):
                    current_checkbox_index = max(0, current_checkbox_index - 1)
                elif key in (curses.KEY_RIGHT, ord('l')):
                    current_checkbox_index = min(len(field["options"]) - 1, current_checkbox_index + 1)
                elif key == ord(' '):
                    option_to_toggle = field["options"][current_checkbox_index]
                    if option_to_toggle in field["value"]:
                        field["value"].remove(option_to_toggle)
                    else:
                        field["value"].append(option_to_toggle)

    curses.curs_set(0)
    curses.mousemask(0)
    form_win.clear()
    form_win.refresh()
    del form_win
    return None


def main(stdscr):
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_CYAN, -1)
    curses.init_pair(2, curses.COLOR_GREEN, -1)
    curses.init_pair(3, curses.COLOR_CYAN, -1)
    curses.init_pair(4, curses.COLOR_WHITE, -1)
    curses.init_pair(5, curses.COLOR_RED, -1) # Red for errors
    stdscr.clear()
    stdscr.refresh()
    task_manager = TaskManager(NOTES_DIR)

    task_data = show_task_creation_form(stdscr, task_manager)

    if task_data:
        filepath = task_manager.create_task(
            title=task_data['title'],
            due=task_data['due'],
            priority=task_data['priority'],
            extra_tags=task_data['extra_tags'],
            contexts=task_data['contexts'],
            recurrence_data=task_data['recurrence_data']
        )
        if filepath:
            msg = f"Task created successfully: {filepath}"
        else:
            msg = "Failed to create task. Check logs."
    else:
        msg = "Task creation cancelled."

    stdscr.clear()
    stdscr.addstr(0, 0, msg, curses.A_BOLD)
    stdscr.refresh()
    stdscr.getch()

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except Exception as e:
        logging.critical(f"Unhandled exception: {e}")
        sys.exit(1)

