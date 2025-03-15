# Diary TUI - Terminal-Based Diary and Time Management

This Python script, `diary_tui.py`, is a terminal-based diary and time management application designed for efficient note-taking, task management, and calendar viewing directly from your terminal. It's inspired by plain text note-taking workflows and aims to provide a fast and distraction-free environment for daily planning and reflection.

## Features

- **Daily Diary Entries:** Create and manage daily diary entries stored as Markdown files with YAML frontmatter for metadata (tags, pomodoros, etc.).
- **Timeblock Management:**  Plan your day with timeblocks within your diary entries. Easily add, update, and view your daily schedule.
- **Task Management:**  Integrated task list (stored in a separate Markdown file) with completion toggling.
- **Multiple Calendar Views:**
    - **Year View:**  Overview of the entire year with day highlighting.
    - **Month View:**  Detailed month calendar with day selection.
    - **Week View:**  Focus on the current week's schedule and days.
- **Search and Tag Filtering:**
    - **Search:** Quickly find diary entries by keywords in content or metadata.
    - **Tag Filtering:**  Filter diary entries by tags for focused views.
- **Side-by-Side and Fullscreen Modes:**
    - **Side-by-Side:** View calendar alongside diary preview, tasks, or timeblocks.
    - **Fullscreen:** Maximize preview, tasks, or timeblock views for focused work.
- **Obsidian-Style Link Parsing:**  Supports `[[link]]` and `[[link|display text]]` syntax for internal linking between diary entries and notes within your notes directory.
- **Editor Integration:**  Opens diary entries and linked notes in your preferred editor (configured in `config.yaml`). Designed to work well with Neovim (via `--server` and `--remote`), but falls back to `vi` or `nano` if available.
- **Live Screen Refresh:**  Automatically refreshes the screen periodically to reflect changes in diary files or tasks.
- **Mouse Support:**  Basic mouse interaction for navigation (scrolling).
- **Context-Aware Command Palette (Ctrl+P):**  Quickly access a list of commands relevant to your current context within the application.
- **Robust Error Handling and Logging:**  Logs errors to `/tmp/calendar_tui.log` for debugging and issue tracking.

## Dependencies

- **Python 3:**  Requires Python 3.
- **curses:**  Usually pre-installed on most Unix-like systems.
- **PyYAML:**  For YAML frontmatter parsing and manipulation. Install with:
  ```bash
  pip install pyyaml
  ```

## Configuration

The script uses a configuration file located at `~/.config/diary-tui/config.yaml`. If the directory or file doesn't exist, it will be created with default values on the first run.

Here's the default configuration structure:

```yaml
diary_dir: "/home/calluma/Dropbox/notes/diary" # Path to your diary entries directory
notes_dir: "/home/calluma/Dropbox/notes"       # Path to your general notes directory (for linking)
tasks_file: "/home/calluma/Dropbox/notes/o7qtm.md" # Path to your tasks Markdown file
home_file: "/home/calluma/Dropbox/notes/home.md"   # Path to your "home" or main notes file
log_file: "/tmp/calendar_tui.log"            # Path to the log file
editor: "nvim"                                # Preferred editor (e.g., "nvim", "vi", "nano", or leave empty for auto-detection)
```

**Configuration Options:**

- **`diary_dir`:**  **Required.**  Set this to the absolute path of the directory where you store your daily diary entries. Diary entries should be named in `YYYY-MM-DD.md` format.
- **`notes_dir`:** **Required.** Set this to the absolute path of your general notes directory. This is used for resolving internal links.
- **`tasks_file`:** **Required.**  Set this to the absolute path of the Markdown file where you keep your tasks. Tasks should be formatted as Markdown lists (`- [ ] Task description` or `- [x] Completed task`).
- **`home_file`:** **Required.** Set this to the absolute path of your "home" or main notes file. This file can be quickly opened with the `1` key.
- **`log_file`:**  Optional. Path to the log file. Defaults to `/tmp/calendar_tui.log`.
- **`editor`:** Optional.  Specify your preferred terminal editor (e.g., "nvim", "vi", "nano"). If left empty, the script will attempt to auto-detect `nvim`, `vi`, or `nano` in that order.  Ensure your editor is in your system's `$PATH`.

**To customize the configuration:**

1. **Locate the configuration file:** `~/.config/diary-tui/config.yaml`.
2. **Edit the file:** Open the file in a text editor and modify the values to match your setup.
3. **Save the file.**

## Installation

You can install `diary-tui` using pip:

```bash
pip install diary-tui
```

Or install from the source:

```bash
git clone https://github.com/username/diary-tui.git
cd diary-tui
pip install .
```

## Usage

After installation, you can run the application using the provided command:

```bash
diary-tui
```

To create a new task:

```bash
task-creator
```

You can also use it as a module:

```python
from diary_tui import main
main()
```

**Navigate and use the application:** Use the keybindings listed below to interact with the diary TUI.

## Keybindings and Commands

| Keybinding | Action                                     |
|------------|---------------------------------------------|
| `h` / `LEFT` | Move to the previous day                  |
| `l` / `RIGHT`| Move to the next day                     |
| `j` / `DOWN` | Move down one week / Navigate tasks/timeblocks down |
| `k` / `UP`   | Move up one week / Navigate tasks/timeblocks up   |
| `m`          | Switch to Month View                      |
| `w`          | Switch to Week View                       |
| `y`          | Switch to Year View                       |
| `o`          | Toggle side-by-side layout               |
| `a`          | Add a note to the current diary entry     |
| `A`          | Add a task to your tasks file             |
| `T`          | Add an empty timeblock template to the diary entry |
| `e`          | Edit the current diary entry in your editor |
| `t`          | Jump to today's date                      |
| `/`          | Initiate a diary search                   |
| `n`          | Navigate to the next search result       |
| `p`          | Navigate to the previous search result   |
| `f`          | Filter diary entries by tag               |
| `M`          | Toggle 'meditate' metadata for the day    |
| `W`          | Toggle 'workout' metadata for the day     |
| `P`          | Increment 'pomodoros' metadata for the day|
| `I`          | Toggle 'important' tag for the day       |
| `L`          | List internal links in the current entry  |
| `0`          | Toggle focus between calendar/preview/tasks/timeblock panes |
| `-`          | Toggle tasks/timeblock pane (or cycle preview/tasks/timeblock in fullscreen mode)|
| `ENTER` (in Tasks pane) | Toggle task completion |
| `ENTER` (in Timeblock pane) | Edit activity for selected timeblock |
| `1`          | Open your 'home_file' in your editor     |
| `2`          | Open your 'tasks_file' in your editor    |
| `s`          | Show weekly statistics popup              |
| `?`          | Show this help screen                     |
| `u` / `d`    | Scroll preview pane up/down (line by line)|
| `U` / `D`    | Scroll preview pane up/down (5 lines at a time)|
| `Ctrl+P`     | Open the command palette                  |
| `q`          | Quit the application                      |


