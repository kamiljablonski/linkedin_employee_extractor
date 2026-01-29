"""
Helper functions for LinkedIn employee extractor
"""
import csv
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import COMPANIES_CSV, OUTPUT_CSV, COOKIE_FILE, ERROR_LOG

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(ERROR_LOG),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def read_companies() -> List[str]:
    """
    Reads the list of companies from CSV file.
    
    Returns:
        List[str]: List of company names
    """
    companies = []
    try:
        with open(COMPANIES_CSV, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                company_name = row.get('Name', '').strip()  # Changed from 'Nazwa' to 'Name'
                if company_name:
                    companies.append(company_name)
        logger.info(f"Loaded {len(companies)} companies from CSV file")
        return companies
    except FileNotFoundError:
        logger.error(f"File {COMPANIES_CSV} not found")
        return []
    except Exception as e:
        logger.error(f"Error reading CSV file: {e}")
        return []


def load_existing_data() -> Dict[str, Dict[str, str]]:
    """
    Loads existing data from CSV file.
    
    Returns:
        Dict[str, Dict]: Dictionary with URL as key and data as value
    """
    existing_data = {}
    if not OUTPUT_CSV.exists():
        return existing_data
    
    try:
        with open(OUTPUT_CSV, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row.get('Profile_URL', '').strip()
                if url:
                    existing_data[url] = {
                        'Profile_URL': url,
                        'Description': row.get('Description', '').strip(),
                        'Company': row.get('Company', '').strip()
                    }
        logger.info(f"Loaded {len(existing_data)} existing records")
        return existing_data
    except Exception as e:
        logger.error(f"Error loading existing data: {e}")
        return {}


def validate_employee_data(employee: Dict[str, str]) -> bool:
    """
    Validates employee data - checks if it has required fields.
    
    Args:
        employee: Dictionary with employee data
    
    Returns:
        bool: True if data is valid
    """
    # Required fields: First name or Last name (at least one), profile URL
    has_name = bool(employee.get('First_Name', '').strip() or employee.get('Last_Name', '').strip())
    has_url = bool(employee.get('Profile_URL', '').strip() and '/in/' in employee.get('Profile_URL', ''))
    
    return has_name and has_url


def save_employee_data(employees: List[Dict[str, str]], company_name: str = None, page_num: int = None, update_mode: bool = False, all_existing_data: Dict[str, Dict[str, str]] = None):
    """
    Saves employee data to CSV file.
    
    Args:
        employees: List of dictionaries with keys: 'Profile_URL', 'Description', 'Company'
        company_name: Company name (optional, for logging)
        page_num: Page number (optional, for logging)
        update_mode: If True, updates existing records instead of just adding new ones
        all_existing_data: All existing data (used in update mode to avoid reloading)
    """
    if not employees:
        return
    
    # Load existing data (only if not provided)
    if all_existing_data is not None:
        existing_data = all_existing_data
    else:
        # In normal mode also load existing data to avoid overwriting
        existing_data = load_existing_data()
    
    # Check if file exists to determine if header should be written
    file_exists = OUTPUT_CSV.exists()
    
    # Prepare data for saving - always start with existing data
    all_data = existing_data.copy()
    new_count = 0
    updated_count = 0
    
    for employee in employees:
        url = employee.get('Profile_URL', '').strip()
        if not url:
            continue
        
        # If URL already exists, update data (in update mode) or skip (in normal mode)
        if url in all_data:
            if update_mode:
                # Update only if new data is more complete
                existing = all_data[url]
                if employee.get('Description') and (not existing.get('Description') or len(employee.get('Description', '')) > len(existing.get('Description', ''))):
                    existing['Description'] = employee.get('Description', '')
                if employee.get('Company') and not existing.get('Company'):
                    existing['Company'] = employee.get('Company', '')
                updated_count += 1
            # In normal mode skip duplicates (don't overwrite)
        else:
            # New record - add to existing data
            all_data[url] = {
                'Profile_URL': url,
                'Description': employee.get('Description', ''),
                'Company': employee.get('Company', '')
            }
            new_count += 1
    
    # Save all data to file
    try:
        with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['Profile_URL', 'Description', 'Company']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for url, data in sorted(all_data.items()):
                writer.writerow(data)
        
        page_info = f" (page {page_num})" if page_num else ""
        if update_mode:
            logger.info(f"Updated {updated_count} records, added {new_count} new{page_info}")
        else:
            logger.info(f"Saved {new_count} new records{page_info}")
    except Exception as e:
        logger.error(f"Error saving data to CSV: {e}")


def load_linkedin_session(driver: webdriver.Chrome):
    """
    Loads LinkedIn session cookies into the browser.
    
    Args:
        driver: Selenium WebDriver instance
    """
    if not COOKIE_FILE.exists():
        logger.warning(f"Cookie file {COOKIE_FILE} does not exist. Skipping session load.")
        return False
    
    try:
        driver.get("https://www.linkedin.com")
        time.sleep(1)  # Short pause for page load
        
        with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        
        # Add each cookie to the browser
        for cookie in cookies:
            try:
                # Remove fields that might cause issues
                cookie.pop('sameSite', None)
                cookie.pop('storeId', None)
                cookie.pop('id', None)
                driver.add_cookie(cookie)
            except Exception as e:
                logger.debug(f"Failed to add cookie: {e}")
        
        # Refresh page after adding cookies
        driver.refresh()
        time.sleep(2)
        logger.info("Loaded LinkedIn session cookies")
        return True
    except Exception as e:
        logger.error(f"Error loading cookies: {e}")
        return False


def save_linkedin_session(driver: webdriver.Chrome):
    """
    Saves LinkedIn session cookies to file.
    
    Args:
        driver: Selenium WebDriver instance
    """
    try:
        # Make sure we're on LinkedIn
        current_url = driver.current_url
        if 'linkedin.com' not in current_url:
            driver.get("https://www.linkedin.com")
            time.sleep(2)
        
        # Get all cookies
        cookies = driver.get_cookies()
        
        if not cookies:
            logger.warning("No cookies to save")
            return False
        
        # Save cookies to JSON file
        with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved {len(cookies)} LinkedIn session cookies to file {COOKIE_FILE}")
        return True
    except Exception as e:
        logger.error(f"Error saving cookies: {e}")
        return False


def wait_for_element(driver, by, value, timeout=10):
    """
    Waits for an element to appear on the page.
    
    Args:
        driver: WebDriver instance
        by: Location method (By.ID, By.CSS_SELECTOR, etc.)
        value: Selector value
        timeout: Maximum wait time in seconds
    
    Returns:
        WebElement or None
    """
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
        return element
    except Exception as e:
        logger.debug(f"Element not found: {by}={value}, {e}")
        return None


def safe_click(driver, element, description=""):
    """
    Safe click on element with error handling.
    
    Args:
        driver: WebDriver instance
        element: Element to click
        description: Element description for logging
    """
    try:
        # Scroll to element
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.5)
        
        # First try normal click
        try:
            WebDriverWait(driver, 5).until(EC.element_to_be_clickable(element))
            element.click()
            if description:
                logger.debug(f"Clicked: {description}")
            return True
        except Exception as click_error:
            # If normal click doesn't work, use JavaScript
            logger.debug(f"Normal click failed, using JavaScript: {click_error}")
            driver.execute_script("arguments[0].click();", element)
            if description:
                logger.debug(f"Clicked via JavaScript: {description}")
            return True
    except Exception as e:
        logger.warning(f"Failed to click element {description}: {e}")
        return False


def assign_company_from_description(description: str, companies: List[str]) -> str:
    """
    Assigns company based on profile description.
    
    Args:
        description: LinkedIn profile description
        companies: List of company names to check
    
    Returns:
        str: Found company name or empty string
    """
    if not description:
        return ''
    
    description_lower = description.lower()
    
    # Check each company in the list
    for company in companies:
        company_lower = company.lower()
        # Check exact name and variants
        if company_lower in description_lower:
            return company
        # Also check without dots and other special characters
        company_clean = company_lower.replace('.', '').replace('-', ' ').replace('_', ' ')
        if company_clean in description_lower:
            return company
    
    return ''


def wait_for_login(driver, login_url, max_wait_time=300):
    """
    Waits for user to manually log in to LinkedIn.
    
    Args:
        driver: WebDriver instance
        login_url: LinkedIn login page URL
        max_wait_time: Maximum wait time in seconds (default 5 minutes)
    
    Returns:
        bool: True if user logged in, False on timeout
    """
    logger.info("Opening LinkedIn login page...")
    logger.info("Please log in manually in the opened browser.")
    logger.info("Script will wait until you log in...")
    
    driver.get(login_url)
    time.sleep(2)  # Short pause for page load
    
    start_time = time.time()
    check_interval = 2  # Check every 2 seconds
    
    while time.time() - start_time < max_wait_time:
        try:
            current_url = driver.current_url
            
            # Check if user is logged in
            # LinkedIn redirects after login - check if we're not on login page anymore
            if '/login' not in current_url and 'linkedin.com' in current_url:
                # Check for elements indicating login (e.g., search field, user menu)
                logged_in_indicators = [
                    "input[placeholder*='Search']",
                    "input[aria-label*='Search']",
                    "input.search-global-typeahead__input",
                    "button[aria-label*='Me']",
                    "nav[aria-label*='Main']"
                ]
                
                for selector in logged_in_indicators:
                    try:
                        element = driver.find_element(By.CSS_SELECTOR, selector)
                        if element:
                            logger.info("✓ Login detected! Continuing with data extraction...")
                            time.sleep(2)  # Short pause after login
                            return True
                    except:
                        continue
            
            # If still on login page, keep waiting
            time.sleep(check_interval)
            
        except Exception as e:
            logger.debug(f"Error checking login status: {e}")
            time.sleep(check_interval)
    
    logger.warning(f"Timeout - login not detected within {max_wait_time} seconds")
    return False
