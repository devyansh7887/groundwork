# conftest.py — shared pytest config for backend tests
import sys
import os

# Add backend root to sys.path so imports work from tests/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
