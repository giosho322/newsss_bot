#!/usr/bin/env python3
"""
Launcher script for the news bot
Run this from the root directory of the project
"""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the main bot
import asyncio
from bot.main import main

if __name__ == "__main__":
    asyncio.run(main())
