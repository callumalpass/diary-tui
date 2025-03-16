"""
Diary-TUI: Terminal-based diary and time management application.

This package provides a feature-rich terminal user interface for managing
diary entries, tasks, notes, and timeblocks. It includes:

- Calendar views (year, month, week)
- Diary entry management with YAML frontmatter
- Task tracking with priorities and due dates
- Timeblock scheduling for daily planning
- Note organization with internal linking

For more information, see the README.md file or visit:
https://github.com/calluma/diary-tui
"""

from .diary_tui import main

__version__ = "0.1.0"
__author__ = "Callum Alpass"
__license__ = "MIT"
__all__ = ['main']