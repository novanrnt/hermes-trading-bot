#!/usr/bin/env python3
"""Cron wrapper: runs trailing stop check silently."""
import sys, os
sys.path.insert(0, r"C:\Users\Administrator\AppData\Local\hermes")
from trailing_manager import run_trailing_check, main_silent
sys.exit(main_silent())
