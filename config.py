"""
Configuration for LinkedIn employee extractor
"""
import os
from pathlib import Path

# File paths
BASE_DIR = Path(__file__).parent
COMPANIES_CSV = BASE_DIR / "companies.csv"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_CSV = OUTPUT_DIR / "employees.csv"
COOKIE_FILE = BASE_DIR / "linkedin_cookies.json"
ERROR_LOG = BASE_DIR / "errors.log"

# Browser configuration
HEADLESS = False  # Set to True for headless mode (no browser window)
BROWSER = "chrome"  # chrome or firefox

# Timeouts (in seconds)
ELEMENT_TIMEOUT = 10
PAGE_LOAD_TIMEOUT = 30
IMPLICIT_WAIT = 5

# Rate limiting - delays between actions (in seconds)
DELAY_BETWEEN_ACTIONS = 3  # Delay between actions (click, scroll)
DELAY_BETWEEN_COMPANIES = 7  # Delay between processing companies
SCROLL_PAUSE_TIME = 2  # Pause after scrolling

# LinkedIn URLs
LINKEDIN_BASE_URL = "https://www.linkedin.com"
LINKEDIN_LOGIN_URL = f"{LINKEDIN_BASE_URL}/login"

# Extraction configuration
MAX_EMPLOYEES_PER_COMPANY = 1000  # Maximum number of employees to extract from one company
SCROLL_ATTEMPTS = 10  # Number of scroll attempts to load more employees

# Create output directory if it doesn't exist
OUTPUT_DIR.mkdir(exist_ok=True)
