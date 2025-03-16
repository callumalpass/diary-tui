# Diary TUI - Terminal-Based Personal Knowledge & Task Management

Diary TUI is a feature-rich terminal application for managing notes, tasks, and daily schedules. It provides an integrated environment for personal knowledge management and productivity tracking.

## Features

### Diary Management
- **Daily Entries**: Create and manage daily diary entries with YAML frontmatter metadata
- **Metadata Tracking**: Track metrics like pomodoros, meditation sessions, and workouts
- **Timeblocking**: Plan your day with timeblocks to schedule activities

### Task Management
- **Task Creation**: Create tasks with title, due date, priority, and context tags
- **Recurrence Support**: Set up recurring tasks (daily, weekly, monthly, yearly)
- **Status Tracking**: Track task status (open, in-progress, done)
- **Due Date Management**: Visual indicators for upcoming and overdue tasks

### Notes Management
- **Markdown Support**: Create and edit notes in markdown format
- **YAML Frontmatter**: Organize notes with metadata
- **Internal Linking**: Supports `[[link]]` and `[[link|display text]]` syntax
- **Notes View**: See files created on the selected date

### Calendar Views
- **Multiple Views**: Year, month, and week calendar views
- **Visual Indicators**: Highlight days with entries, tasks, and current selection
- **Statistics**: View monthly statistics for tracked metrics

### User Interface
- **Flexible Layout**: Side-by-side or full-screen modes based on terminal width
- **Split Panels**: View calendar alongside diary entries, tasks, or timeblocks
- **Command Palette**: Quick access to commands with Ctrl+P
- **Search**: Find content across entries with keyword search
- **Tag Filtering**: Filter entries by tags for focused views

## Installation

### From Source
```bash
git clone https://github.com/username/diary-tui.git
cd diary-tui
pip install .
```

## Configuration

Diary TUI uses a configuration file at `~/.config/diary-tui/config.yaml`. The file will be created with default values on first run.

Configuration options:
- `diary_dir`: Directory for daily diary entries (format: YYYY-MM-DD.md)
- `notes_dir`: Directory for general markdown notes
- `tasks_file`: Path to your tasks file (optional)
- `home_file`: Path to your main notes file (optional)
- `log_file`: Path for application logs (default: /tmp/calendar_tui.log)
- `editor`: Your preferred editor (default: auto-detects nvim, vi, or nano)

## Usage

### Launch the application
```bash
diary-tui
```

### Create a new task
```bash
task-creator
```

### Key Bindings

#### Navigation
- `h/←`: Previous day
- `l/→`: Next day
- `j/↓`: Next week / Navigate down in tasks
- `k/↑`: Previous week / Navigate up in tasks
- `t`: Jump to today

#### Views
- `m`: Month view
- `w`: Week view
- `y`: Year view
- `o`: Toggle side-by-side layout
- `-`: Toggle tasks/timeblock pane
- `0`: Switch focus between panes

#### Content Management
- `a`: Add note to current diary entry
- `A`: Add task to tasks file
- `T`: Add timeblock template
- `e`: Edit current diary entry
- `ENTER`: Toggle task completion / Edit timeblock

#### Search and Organization
- `/`: Search diary entries
- `n/p`: Navigate search results
- `f`: Filter by tag
- `s`: Show statistics

#### Metadata Tracking
- `M`: Toggle meditation status
- `W`: Toggle workout status
- `P`: Increment pomodoro count
- `I`: Toggle "important" tag

#### Other
- `?`: Show help
- `Ctrl+P`: Open command palette
- `q`: Quit application

## File Formats

### Diary Entries

Diary entries use Markdown with YAML frontmatter for metadata. Files are stored in the `diary_dir` directory with the format `YYYY-MM-DD.md`.

```markdown
---
date: 2023-01-01
meditate: true
workout: false
pomodoros: 3
tags: [daily, planning]
important: true
---

# Sunday, January 1, 2023

## Notes

This is a good place for general thoughts about the day.

```

### Tasks

Tasks are stored as individual Markdown files with YAML frontmatter. They can be created with the `task-creator` command.

```markdown
---
title: Complete project proposal
zettelid: 230101abc
dateCreated: 2023-01-01T14:30:00
dateModified: 2023-01-01T14:30:00
status: open
due: 2023-01-15
tags: [task, work, project]
priority: high
contexts: [office, computer]
---

# Complete project proposal

Draft the proposal for the new client project, including:

- Timeline estimates
- Budget breakdown
- Resource requirements
- Deliverables schedule
```

### Recurring Tasks

Tasks can include recurrence data in the YAML frontmatter:

```markdown
---
title: Weekly team meeting
zettelid: 230105xyz
dateCreated: 2023-01-05T09:15:00
dateModified: 2023-01-05T09:15:00
status: open
tags: [task, meeting, team]
priority: normal
contexts: [work, zoom]
recurrence:
  frequency: weekly
  days_of_week: [mon]
complete_instances: []
---

# Weekly team meeting

- Review sprint progress
- Discuss blockers
- Plan next week's work
```

## Dependencies

- Python 3.6+
- PyYAML (for configuration and frontmatter)
- curses (included with Python on most systems)

## License

MIT
