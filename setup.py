from setuptools import setup, find_packages

setup(
    name="diary-tui",
    version="0.1.0",
    packages=find_packages(),
    py_modules=["diary_tui", "task_creator"],
    install_requires=[
        "pyyaml",
    ],
    entry_points={
        "console_scripts": [
            "diary-tui=diary_tui:main",
            "task-creator=task_creator:main_cli",
        ],
    },
    author="Callum Alpass",
    author_email="",
    description="Terminal-based diary and time management application",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/username/diary-tui",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)
