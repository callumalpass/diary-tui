import os
from setuptools import setup, find_packages

# Import version from the package without importing the whole package
with open(os.path.join('diary_tui', '__init__.py'), 'r') as f:
    for line in f:
        if line.startswith('__version__'):
            version = line.split('=')[1].strip().strip('"').strip("'")
            break

setup(
    name="diary-tui",
    version=version,
    packages=find_packages(),
    py_modules=["task_creator"],
    install_requires=[
        "pyyaml>=6.0,<7.0",
    ],
    entry_points={
        "console_scripts": [
            "diary-tui=diary_tui:main",
            "task-creator=diary_tui.task_creator:main_cli",
        ],
    },
    author="Callum Alpass",
    author_email="",
    description="Terminal-based diary and time management application",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/calluma/diary-tui",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Environment :: Console :: Curses",
        "Topic :: Office/Business :: Scheduling",
        "Topic :: Utilities",
    ],
    python_requires=">=3.6",
    include_package_data=True,
)
