"""
Main script for extracting employee data from LinkedIn
"""
import time
import re
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager

from config import (
    HEADLESS, ELEMENT_TIMEOUT, PAGE_LOAD_TIMEOUT, IMPLICIT_WAIT,
    DELAY_BETWEEN_ACTIONS, DELAY_BETWEEN_COMPANIES, SCROLL_PAUSE_TIME,
    LINKEDIN_BASE_URL, LINKEDIN_LOGIN_URL, MAX_EMPLOYEES_PER_COMPANY, 
    SCROLL_ATTEMPTS, OUTPUT_CSV
)
from utils import (
    read_companies, save_employee_data, load_linkedin_session, save_linkedin_session,
    wait_for_element, safe_click, wait_for_login, logger, load_existing_data,
    assign_company_from_description
)


def setup_browser() -> Optional[webdriver.Chrome]:
    """
    Initializes Chrome browser with appropriate options.
    
    Returns:
        webdriver.Chrome: Browser instance or None on error
    """
    try:
        chrome_options = Options()
        
        if HEADLESS:
            chrome_options.add_argument("--headless")
        
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Get chromedriver path
        try:
            base_path = ChromeDriverManager().install()
            
            # ChromeDriverManager may return a folder path or invalid file
            # Always search for the correct chromedriver file
            driver_path = None
            
            # If it's a file, check if it's the correct chromedriver
            if os.path.isfile(base_path) and 'chromedriver' in base_path and 'THIRD_PARTY' not in base_path:
                driver_path = base_path
            # If it's a folder or invalid file, search recursively
            else:
                search_dir = base_path if os.path.isdir(base_path) else os.path.dirname(base_path)
                # Recursively search for chromedriver file (but not THIRD_PARTY_NOTICES)
                for root, dirs, files in os.walk(search_dir):
                    for file in files:
                        if file == 'chromedriver' and 'THIRD_PARTY' not in root:
                            full_path = os.path.join(root, file)
                            if os.path.isfile(full_path):
                                driver_path = full_path
                                break
                    if driver_path:
                        break
            
            if driver_path and os.path.isfile(driver_path):
                # Make sure the file is executable
                try:
                    os.chmod(driver_path, 0o755)
                except:
                    pass
                service = Service(driver_path)
                logger.info(f"Using chromedriver: {driver_path}")
            else:
                logger.warning(f"Chromedriver not found, trying without Service")
                service = None
        except Exception as e:
            logger.warning(f"Problem with ChromeDriverManager: {e}, trying without Service")
            service = None
        
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        driver.implicitly_wait(IMPLICIT_WAIT)
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        
        logger.info("Browser initialized")
        
        # Try to load session from cookies
        if not load_linkedin_session(driver):
            # If no cookies, ask user for manual login
            logger.info("No saved session. Manual login required.")
            if not wait_for_login(driver, LINKEDIN_LOGIN_URL):
                logger.error("Failed to log in. Closing browser.")
                driver.quit()
                return None
            else:
                # After login, save cookies for future use
                logger.info("Saving session cookies...")
                save_linkedin_session(driver)
        
        return driver
    except Exception as e:
        logger.error(f"Error initializing browser: {e}")
        return None


def search_company(driver: webdriver.Chrome, company_name: str) -> Optional[str]:
    """
    Searches for a company on LinkedIn and returns the company page URL.
    
    Args:
        driver: WebDriver instance
        company_name: Company name to search for
    
    Returns:
        str: Company page URL or None if not found
    """
    try:
        logger.info(f"Searching for company: {company_name}")
        
        # Use direct company search URL
        search_url = f"{LINKEDIN_BASE_URL}/search/results/companies/?keywords={company_name.replace(' ', '%20')}"
        logger.info(f"Navigating to: {search_url}")
        driver.get(search_url)
        time.sleep(DELAY_BETWEEN_ACTIONS + 2)
        
        # Wait for results to load
        try:
            WebDriverWait(driver, ELEMENT_TIMEOUT).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            # Additional wait for search results to load
            time.sleep(3)
        except TimeoutException:
            logger.error("Timeout loading search results")
            return None
        
        # Find first search result (company page)
        company_url = None
        company_link = None
        
        # First try using specific XPath
        try:
            xpath_selector = "/html/body/div[6]/div[3]/div[2]/div/div[1]/main/div/div/div[3]/div/ul/li[1]/div/div/div/div[2]/div[1]/div[1]/div/span/span/a"
            company_link = wait_for_element(driver, By.XPATH, xpath_selector, timeout=10)
            if company_link:
                company_url = company_link.get_attribute('href')
                if company_url and '/company/' in company_url:
                    company_url = company_url.split('?')[0]
                    logger.info(f"✓ Found company via XPath: {company_url}")
        except Exception as e:
            pass
        
        # Fallback to other selectors if XPath didn't work
        if not company_url or not company_link:
            company_link_selectors = [
                "a[href*='/company/']",  # Najbardziej ogólny selektor
                "ul li a[href*='/company/']",
                "div[class*='search-result'] a[href*='/company/']",
                "a.search-result__result-link[href*='/company/']",
                "a[data-control-name='search_srp_result'][href*='/company/']",
                "div.search-result__info a[href*='/company/']",
                "li.search-result a[href*='/company/']"
            ]
            
            for selector in company_link_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        # Find first element with company link
                        for elem in elements:
                            href = elem.get_attribute('href')
                            if href and '/company/' in href:
                                company_link = elem
                                company_url = href.split('?')[0]
                                logger.info(f"✓ Found company via CSS selector '{selector}': {company_url}")
                                break
                        if company_url:
                            break
                except Exception as e:
                    continue
        
        if not company_url:
            logger.warning(f"Company page not found for: {company_name}")
            return None
        
        # Click on company link
        if company_link:
            try:
                safe_click(driver, company_link, f"company link {company_name}")
                time.sleep(DELAY_BETWEEN_ACTIONS + 2)
                
                # Check if we're on company page
                current_url = driver.current_url
                if '/company/' in current_url:
                    # Make sure we have clean company URL
                    company_url = current_url.split('?')[0].split('/people')[0].split('/about')[0]
                    logger.info(f"On company page: {company_url}")
                    return company_url
            except Exception as e:
                logger.warning(f"Failed to click company link: {e}")
                # Try navigating directly via URL
                driver.get(company_url)
                time.sleep(DELAY_BETWEEN_ACTIONS)
                return company_url
        
        return company_url
        
    except Exception as e:
        logger.error(f"Error searching for company {company_name}: {e}")
        return None


def extract_employees(driver: webdriver.Chrome, company_url: str, company_name: str, existing_data: Dict[str, Dict[str, str]] = None, companies_list: List[str] = None, update_mode: bool = False) -> List[Dict[str, str]]:
    """
    Extracts list of employees from company page on LinkedIn.
    
    Args:
        driver: WebDriver instance
        company_url: Company page URL
        company_name: Company name
        existing_data: Dictionary with existing data (for update mode)
        companies_list: List of companies for assignment
        update_mode: Update mode - skips URLs with complete data
    
    Returns:
        List[Dict]: List of dictionaries with employee data
    """
    employees = []
    if existing_data is None:
        existing_data = {}
    if companies_list is None:
        companies_list = []
    
    try:
        # First make sure we're on company page
        if '/company/' not in driver.current_url:
            logger.info(f"Navigating to company page: {company_url}")
            driver.get(company_url)
            time.sleep(DELAY_BETWEEN_ACTIONS + 2)
        
        # Check if page loaded
        try:
            WebDriverWait(driver, ELEMENT_TIMEOUT).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except TimeoutException:
            logger.error(f"Timeout loading company page for {company_name}")
            return employees
        
        # Find and click on "People" tab
        logger.info("Looking for 'People' tab...")
        people_tab_selectors = [
            "a[href*='/people/']",
            "a[data-control-name='page_member_main_nav_people']",
            "//a[contains(text(), 'People') or contains(text(), 'Pracownicy')]",
            "//button[contains(text(), 'People') or contains(text(), 'Pracownicy')]",
            "nav a[href*='/people/']"
        ]
        
        people_tab_clicked = False
        for selector in people_tab_selectors:
            try:
                if selector.startswith("//"):
                    # XPath
                    element = wait_for_element(driver, By.XPATH, selector, timeout=5)
                else:
                    # CSS Selector
                    element = wait_for_element(driver, By.CSS_SELECTOR, selector, timeout=5)
                
                if element:
                    logger.info("Found People tab, clicking...")
                    safe_click(driver, element, "zakładka People")
                    time.sleep(DELAY_BETWEEN_ACTIONS + 2)
                    people_tab_clicked = True
                    break
            except Exception as e:
                continue
        
        # Check current URL - LinkedIn may redirect to search page
        current_url = driver.current_url
        
        # If we're not on employees page, try navigating directly
        if '/search/results/people/' not in current_url and '/people/' not in current_url:
            # Try navigating to /people/ - LinkedIn will redirect to /search/results/people/
            people_url = f"{company_url.rstrip('/')}/people/"
            logger.info(f"Navigating directly to: {people_url}")
            driver.get(people_url)
            time.sleep(DELAY_BETWEEN_ACTIONS + 2)
            current_url = driver.current_url
        
        # Check if employees page loaded
        try:
            WebDriverWait(driver, ELEMENT_TIMEOUT).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            # Additional wait for employee list to load
            time.sleep(3)
        except TimeoutException:
            logger.error(f"Timeout loading employees page for {company_name}")
            return employees
        
        # Check if we're actually on employees page
        final_url = driver.current_url
        if '/search/results/people/' not in final_url and '/people/' not in final_url:
            logger.warning(f"Not on employees page. Current URL: {final_url}")
            return employees
        
        logger.info(f"On employees page: {final_url}")
        
        # Find pagination list and extract ALL page URLs
        pagination_list_xpath = "/html/body/div/div[2]/div[2]/div[2]/main/div/div/div/div[1]/div/div/div/div[3]/div/ul"
        pagination_list = wait_for_element(driver, By.XPATH, pagination_list_xpath, timeout=10)
        
        page_urls = []
        current_url = driver.current_url
        # Remove page parameter from URL if it exists
        if '&page=' in current_url:
            base_url = current_url.split('&page=')[0]
        elif '?page=' in current_url:
            base_url = current_url.split('?page=')[0]
        else:
            base_url = current_url
        
        if pagination_list:
            logger.info("Found pagination, extracting all page URLs...")
            try:
                li_elements = pagination_list.find_elements(By.TAG_NAME, "li")
                logger.info(f"Found {len(li_elements)} li elements in pagination")
                
                for li in li_elements:
                    try:
                        # Find clickable element (button or link)
                        clickable = None
                        try:
                            clickable = li.find_element(By.TAG_NAME, "button")
                        except:
                            try:
                                clickable = li.find_element(By.TAG_NAME, "a")
                            except:
                                pass
                        
                        if clickable:
                            # Extract URL or page number
                            href = driver.execute_script("return arguments[0].href || '';", clickable)
                            text = driver.execute_script("return arguments[0].textContent || arguments[0].innerText || '';", clickable).strip()
                            
                            # If there's href, use it
                            if href and '/search/results/people/' in href:
                                page_urls.append(href)
                            # If no href but there's a number in text, build URL
                            elif text and text.isdigit():
                                page_num = int(text)
                                # Build URL with page parameter
                                if '?' in base_url:
                                    page_url = f"{base_url}&page={page_num}"
                                else:
                                    page_url = f"{base_url}?page={page_num}"
                                page_urls.append(page_url)
                    except Exception as e:
                        pass
                        continue
                
                # Remove duplicates and sort
                def get_page_num(url):
                    match = re.search(r'page=(\d+)', url)
                    return int(match.group(1)) if match else 999
                
                page_urls = sorted(set(page_urls), key=get_page_num)
                logger.info(f"Extracted {len(page_urls)} unique page URLs")
            except Exception as e:
                logger.error(f"Error extracting URLs from pagination: {e}")
        else:
            logger.info("No pagination found - only 1 page")
            page_urls = [driver.current_url]
        
        # Extract employees from all pages
        all_employees = []
        
        for idx, page_url in enumerate(page_urls, 1):
            logger.info(f"Extracting page {idx}/{len(page_urls)} for {company_name}")
            
            # Navigate to page URL
            try:
                driver.get(page_url)
                time.sleep(DELAY_BETWEEN_ACTIONS + 2)
                
                # Check if page loaded
                WebDriverWait(driver, ELEMENT_TIMEOUT).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                time.sleep(2)  # Additional wait for list to load
            except Exception as e:
                logger.error(f"Error navigating to page {idx}: {e}")
                continue
            
            # Extract employees from current page (with descriptions and company)
            page_employees = extract_employees_from_current_page(driver, company_name, companies_list)
            
            # For each employee check if it's a duplicate and if it needs update
            for emp in page_employees:
                url = emp.get('Profile_URL', '')
                if not url:
                    continue
                
                # In update mode check if URL already exists
                if update_mode and url in existing_data:
                    existing = existing_data[url]
                    # If it has description and company, skip
                    if existing.get('Description') and existing.get('Company'):
                        logger.debug(f"Skipping {url} - already has complete data")
                        continue
                    # If data is missing, update from newly extracted
                    if not existing.get('Description') and emp.get('Description'):
                        existing['Description'] = emp.get('Description', '')
                    if not existing.get('Company') and emp.get('Company'):
                        existing['Company'] = emp.get('Company', '')
                    # Use updated data
                    emp = existing
                
                # Add to all employees list (avoid duplicates)
                if emp not in all_employees:
                    all_employees.append(emp)
            
            logger.info(f"Page {idx}: found {len(page_employees)} employees (total: {len(all_employees)})")
            
            # Save employees from current page to file
            if page_employees:
                save_employee_data(page_employees, company_name, idx, update_mode)
        
        logger.info(f"Extraction completed. Found total {len(all_employees)} employees for {company_name}")
        return all_employees
        
    except Exception as e:
        logger.error(f"Error extracting employees for {company_name}: {e}")
        return employees


def extract_employees_from_current_page(driver: webdriver.Chrome, company_name: str, companies_list: List[str] = None) -> List[Dict[str, str]]:
    """
    Extracts profile links and descriptions from currently visible page.
    
    Args:
        driver: WebDriver instance
        company_name: Company name (used as default company)
        companies_list: List of companies for assignment (optional)
    
    Returns:
        List[Dict]: List of dictionaries with keys 'Profile_URL', 'Description', 'Company'
    """
    employees = _extract_visible_employees(driver, company_name)
    
    # If we have company list, try to assign company based on description
    if companies_list:
        for emp in employees:
            # If company not assigned or empty, try to find based on description
            if not emp.get('Company') or emp.get('Company') == company_name:
                description = emp.get('Description', '')
                if description:
                    assigned_company = assign_company_from_description(description, companies_list)
                    if assigned_company:
                        emp['Company'] = assigned_company
                    elif company_name:
                        # If no match found, use company_name as default
                        emp['Company'] = company_name
                elif company_name:
                    # If no description, use company_name
                    emp['Company'] = company_name
            elif not emp.get('Company'):
                # If no company, use company_name
                emp['Company'] = company_name
    
    return employees


def extract_profile_description(driver: webdriver.Chrome, profile_url: str) -> str:
    """
    Extracts description from LinkedIn profile.
    NOTE: This function is deprecated - descriptions are now extracted from employee lists.
    Kept for backward compatibility.
    
    Args:
        driver: WebDriver instance
        profile_url: LinkedIn profile URL
    
    Returns:
        str: Profile description or empty string
    """
    description = ''
    
    try:
        logger.debug(f"Extracting description from profile: {profile_url}")
        driver.get(profile_url)
        time.sleep(DELAY_BETWEEN_ACTIONS + 1)
        
        # Wait for page to load
        try:
            WebDriverWait(driver, ELEMENT_TIMEOUT).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(2)
        except TimeoutException:
            logger.warning(f"Timeout loading profile: {profile_url}")
            return description
        
        # Various selectors for profile description (About section)
        description_selectors = [
            "div[data-section='summary'] span",
            "section[data-section='summary'] span",
            "div.ph5.pb5 span",
            "div.pv-about__summary-text span",
            "div.core-section-container__content span",
            "div.break-words span",
            "section.pv-about-section div span",
            "div[data-test-id='about-us-description'] span",
            "div[data-test-id='about-us-description']",
            "div.text-body-medium span"
        ]
        
        for selector in description_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for elem in elements:
                    text = elem.text.strip()
                    if text and len(text) > 20:  # Description should be longer than 20 characters
                        description = text
                        logger.debug(f"Found description ({len(description)} characters)")
                        break
                if description:
                    break
            except Exception as e:
                continue
        
        # If not found via CSS, try XPath
        if not description:
            xpath_selectors = [
                "//section[@data-section='summary']//span",
                "//div[contains(@class, 'pv-about')]//span",
                "//div[contains(@class, 'core-section-container')]//span"
            ]
            
            for xpath in xpath_selectors:
                try:
                    elements = driver.find_elements(By.XPATH, xpath)
                    for elem in elements:
                        text = elem.text.strip()
                        if text and len(text) > 20:
                            description = text
                            logger.debug(f"Found description via XPath ({len(description)} characters)")
                            break
                    if description:
                        break
                except Exception as e:
                    continue
        
    except Exception as e:
        logger.warning(f"Error extracting description from {profile_url}: {e}")
    
    return description


def _extract_visible_employees(driver: webdriver.Chrome, company_name: str) -> List[Dict[str, str]]:
    """
    Extracts profile links and descriptions from currently visible employee list page.
    
    Args:
        driver: WebDriver instance
        company_name: Company name (used for company assignment)
    
    Returns:
        List[Dict]: List of dictionaries with keys 'Profile_URL', 'Description', 'Company'
    """
    employees = []
    seen_urls = set()
    
    try:
        # XPath do kontenera listy pracowników
        container_xpath = "/html/body/div/div[2]/div[2]/div[2]/main/div/div/div/div[1]/div/div/div/div[1]/div[1]"
        
        container = wait_for_element(driver, By.XPATH, container_xpath, timeout=5)
        if not container:
            logger.warning("Employee list container not found")
            return employees
        
        # Use precise XPath for main profile links (not mutual connections links)
        # Pattern from examples: div[1]/a/div/div[1]/div[1]/p/a[1], div[2]/a/div/div[1]/div[1]/p/a[1]
        # Find all links matching this pattern
        link_elements = container.find_elements(By.XPATH, ".//div/a/div/div[1]/div[1]/p/a[1]")
        
        logger.info(f"Found {len(link_elements)} main profile links")
        
        for link in link_elements:
            try:
                # Use JavaScript to get href to avoid hanging
                href = driver.execute_script("return arguments[0].href;", link)
                if not href:
                    href = link.get_attribute('href')
                
                if href and '/in/' in href:
                    # Normalize URL (remove parameters)
                    clean_url = href.split('?')[0]
                    
                    if clean_url not in seen_urls:
                        seen_urls.add(clean_url)
                        
                        # Extract description from employee list
                        # XPath to description: /html/body/div/div[2]/div[2]/div[2]/main/div/div/div/div[1]/div/div/div/div[1]/div[1]/div[1]/a/div/div[1]/div[1]/div[1]/p
                        # Use relative XPath from container - description is in the same div as link
                        description = ''
                        try:
                            # Find container for this specific employee (link's parent)
                            parent_container = link.find_element(By.XPATH, "./ancestor::div[contains(@class, 'entity-result') or position()=1][1]")
                            
                            # Try different XPath selectors for description
                            description_selectors = [
                                ".//div[1]/div[1]/div[1]/p",  # Relative from employee container
                                ".//p[contains(@class, 'entity-result__primary-subtitle')]",
                                ".//p[contains(@class, 'entity-result__summary')]",
                                ".//span[contains(@class, 'entity-result__summary')]",
                            ]
                            
                            for selector in description_selectors:
                                try:
                                    desc_elem = parent_container.find_element(By.XPATH, selector)
                                    description = desc_elem.text.strip()
                                    if description and len(description) > 5:  # Minimum 5 characters
                                        break
                                except:
                                    continue
                            
                            # If not found via relative XPath, try absolute
                            if not description:
                                # Find index of this element in the list
                                all_links = container.find_elements(By.XPATH, ".//div/a/div/div[1]/div[1]/p/a[1]")
                                link_index = all_links.index(link) + 1
                                
                                # Use absolute XPath with index
                                abs_desc_xpath = f"/html/body/div/div[2]/div[2]/div[2]/main/div/div/div/div[1]/div/div/div/div[1]/div[1]/div[{link_index}]/a/div/div[1]/div[1]/div[1]/p"
                                try:
                                    desc_elem = driver.find_element(By.XPATH, abs_desc_xpath)
                                    description = desc_elem.text.strip()
                                except:
                                    pass
                        except Exception as e:
                            logger.debug(f"Failed to extract description for {clean_url}: {e}")
                        
                        # Utwórz słownik z danymi
                        employee_data = {
                            'Profile_URL': clean_url,
                            'Description': description,
                            'Company': company_name if company_name else ''
                        }
                        
                        employees.append(employee_data)
            except Exception as e:
                logger.debug(f"Error extracting data for link: {e}")
                continue
        
        logger.info(f"Extracted {len(employees)} unique profiles with descriptions")
        return employees
    except Exception as e:
        logger.error(f"Error extracting links: {e}")
        return employees


def process_company(driver: webdriver.Chrome, company_name: str, existing_data: Dict[str, Dict[str, str]] = None, companies_list: List[str] = None, update_mode: bool = False) -> bool:
    """
    Przetwarza jedną firmę: wyszukuje ją i ekstrahuje pracowników.
    
    Args:
        driver: Instancja WebDriver
        company_name: Nazwa firmy
        existing_data: Słownik z istniejącymi danymi (dla trybu update)
        companies_list: Lista firm do przyporządkowania
        update_mode: Tryb aktualizacji (nie używa tej funkcji w trybie update)
    
    Returns:
        bool: True jeśli przetwarzanie zakończyło się sukcesem
    """
    try:
        # In update mode this function should not be called
        if update_mode:
            logger.warning("process_company should not be called in update mode")
            return False
        
        # Search for company
        company_url = search_company(driver, company_name)
        if not company_url:
            logger.warning(f"Company not found: {company_name}")
            return False
        
        time.sleep(DELAY_BETWEEN_ACTIONS)
        
        # Extract employees
        employees = extract_employees(driver, company_url, company_name, existing_data, companies_list, update_mode)
        
        if employees:
            # Save data
            save_employee_data(employees, company_name, update_mode=update_mode)
            logger.info(f"Successfully processed company {company_name}: {len(employees)} employees")
            return True
        else:
            logger.warning(f"No employees found for company: {company_name}")
            return False
            
    except Exception as e:
        logger.error(f"Error processing company {company_name}: {e}")
        return False


def update_existing_profiles(driver: webdriver.Chrome, existing_data: Dict[str, Dict[str, str]], companies_list: List[str]):
    """
    Updates existing profiles - extracts description and assigns company from employee list.
    Does not scrape new URLs, only updates those already in the file.
    Does not visit individual profiles - extracts data from employee list.
    
    Args:
        driver: WebDriver instance
        existing_data: Dictionary with existing data
        companies_list: List of companies for assignment
    """
    logger.info("=== Starting update of existing profiles ===")
    logger.info("Update mode: will NOT scrape new URLs, only update existing ones")
    logger.info("Extracting data from employee list (without visiting profiles)")
    
    # Count how many profiles need update
    profiles_needing_update = sum(1 for data in existing_data.values() 
                                  if not data.get('Description') or not data.get('Company'))
    logger.info(f"Found {profiles_needing_update} profiles to update out of {len(existing_data)} total")
    
    updated_count = 0
    skipped_count = 0
    
    # For each company in the list, search and extract data from employee list
    for company_idx, company_name in enumerate(companies_list, 1):
        logger.info(f"\n--- Processing company {company_idx}/{len(companies_list)}: {company_name} ---")
        
        company_updated = 0
        
        try:
            # Search for company
            company_url = search_company(driver, company_name)
            if not company_url:
                logger.warning(f"Company not found: {company_name}")
                continue
            
            time.sleep(DELAY_BETWEEN_ACTIONS)
            
            # Navigate to employee list
            # First make sure we're on company page
            if '/company/' not in driver.current_url:
                driver.get(company_url)
                time.sleep(DELAY_BETWEEN_ACTIONS + 2)
            
            # Navigate to employee list
            people_url = f"{company_url.rstrip('/')}/people/"
            logger.info(f"Navigating to employee list: {people_url}")
            driver.get(people_url)
            time.sleep(DELAY_BETWEEN_ACTIONS + 2)
            
            # Check if employees page loaded
            try:
                WebDriverWait(driver, ELEMENT_TIMEOUT).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                time.sleep(3)
            except TimeoutException:
                logger.error(f"Timeout loading employees page for {company_name}")
                continue
            
            # Check if we're actually on employees page
            current_url = driver.current_url
            if '/search/results/people/' not in current_url and '/people/' not in current_url:
                logger.warning(f"Not on employees page. Current URL: {current_url}")
                continue
            
            # Find all pagination pages (similar to extract_employees)
            pagination_list_xpath = "/html/body/div/div[2]/div[2]/div[2]/main/div/div/div/div[1]/div/div/div/div[3]/div/ul"
            pagination_list = wait_for_element(driver, By.XPATH, pagination_list_xpath, timeout=10)
            
            page_urls = []
            base_url = current_url.split('&page=')[0] if '&page=' in current_url else (current_url.split('?page=')[0] if '?page=' in current_url else current_url)
            
            if pagination_list:
                try:
                    li_elements = pagination_list.find_elements(By.TAG_NAME, "li")
                    for li in li_elements:
                        try:
                            clickable = None
                            try:
                                clickable = li.find_element(By.TAG_NAME, "button")
                            except:
                                try:
                                    clickable = li.find_element(By.TAG_NAME, "a")
                                except:
                                    pass
                            
                            if clickable:
                                href = driver.execute_script("return arguments[0].href || '';", clickable)
                                text = driver.execute_script("return arguments[0].textContent || arguments[0].innerText || '';", clickable).strip()
                                
                                if href and '/search/results/people/' in href:
                                    page_urls.append(href)
                                elif text and text.isdigit():
                                    page_num = int(text)
                                    if '?' in base_url:
                                        page_url = f"{base_url}&page={page_num}"
                                    else:
                                        page_url = f"{base_url}?page={page_num}"
                                    page_urls.append(page_url)
                        except:
                            continue
                    
                    def get_page_num(url):
                        match = re.search(r'page=(\d+)', url)
                        return int(match.group(1)) if match else 999
                    
                    page_urls = sorted(set(page_urls), key=get_page_num)
                    logger.info(f"Found {len(page_urls)} pages to search")
                except Exception as e:
                    logger.error(f"Error extracting URLs from pagination: {e}")
                    page_urls = [current_url]
            else:
                page_urls = [current_url]
            
            # Go through all pages and extract data
            for page_idx, page_url in enumerate(page_urls, 1):
                logger.info(f"Extracting page {page_idx}/{len(page_urls)} for {company_name}")
                
                try:
                    driver.get(page_url)
                    time.sleep(DELAY_BETWEEN_ACTIONS + 2)
                    
                    WebDriverWait(driver, ELEMENT_TIMEOUT).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    time.sleep(2)
                except Exception as e:
                    logger.error(f"Error navigating to page {page_idx}: {e}")
                    continue
                
                # Extract data from current page
                page_employees = extract_employees_from_current_page(driver, company_name, companies_list)
                
                # Update only URLs that are already in existing_data
                for emp in page_employees:
                    url = emp.get('Profile_URL', '')
                    if not url:
                        continue
                    
                    # Check if this URL is in existing data
                    if url in existing_data:
                        data = existing_data[url]
                        
                        # Check if it needs update
                        needs_update = False
                        if not data.get('Description') and emp.get('Description'):
                            data['Description'] = emp.get('Description', '')
                            needs_update = True
                        if not data.get('Company') and emp.get('Company'):
                            data['Company'] = emp.get('Company', '')
                            needs_update = True
                        
                        if needs_update:
                            updated_count += 1
                            company_updated += 1
                            logger.debug(f"Updated: {url}")
                        else:
                            skipped_count += 1
            
            # Save progress per company
            save_employee_data(list(existing_data.values()), company_name, update_mode=True, all_existing_data=existing_data)
            
            logger.info(f"Company {company_name}: updated {company_updated} profiles")
            
            # Delay between companies
            if company_idx < len(companies_list):
                time.sleep(DELAY_BETWEEN_COMPANIES)
                
        except Exception as e:
            logger.error(f"Error processing company {company_name}: {e}")
            continue
    
    # Save all updated data
    save_employee_data(list(existing_data.values()), update_mode=True, all_existing_data=existing_data)
    logger.info(f"\n=== Update completed ===")
    logger.info(f"Updated: {updated_count} profiles")
    logger.info(f"Skipped (already complete or not found): {skipped_count} profiles")


def main():
    """
    Main function that starts the extraction process.
    """
    import sys
    
    # Check if running in update mode
    update_mode = '--update' in sys.argv or '-u' in sys.argv
    
    if update_mode:
        logger.info("=== UPDATE MODE - will NOT scrape new URLs ===")
    else:
        logger.info("=== Starting LinkedIn data extraction ===")
    
    # Load company list
    companies = read_companies()
    if not companies:
        logger.error("No companies to process")
        return
    
    # Load existing data in update mode
    existing_data = {}
    if update_mode:
        existing_data = load_existing_data()
        if not existing_data:
            logger.warning("No existing data to update. Switching to normal mode.")
            update_mode = False
    
    # Initialize browser
    driver = setup_browser()
    if not driver:
        logger.error("Failed to initialize browser")
        return
    
    try:
        if update_mode:
            # Tryb aktualizacji - tylko aktualizuj istniejące profile
            update_existing_profiles(driver, existing_data, companies)
        else:
            # Normalny tryb - scrapuj nowe URL-e
            total_companies = len(companies)
            successful = 0
            failed = 0
            
            for idx, company_name in enumerate(companies, 1):
                logger.info(f"\n--- Processing company {idx}/{total_companies}: {company_name} ---")
                
                success = process_company(driver, company_name, existing_data, companies, update_mode)
                if success:
                    successful += 1
                else:
                    failed += 1
                
                # Delay between companies (except last)
                if idx < total_companies:
                    logger.info(f"Waiting {DELAY_BETWEEN_COMPANIES} seconds before next company...")
                    time.sleep(DELAY_BETWEEN_COMPANIES)
            
            logger.info(f"\n=== Extraction completed ===")
            logger.info(f"Successfully processed: {successful} companies")
            logger.info(f"Failures: {failed} companies")
        
        logger.info(f"Results saved to: {OUTPUT_CSV}")
        
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
    except Exception as e:
        logger.error(f"Critical error: {e}")
    finally:
        logger.info("Closing browser...")
        driver.quit()


if __name__ == "__main__":
    main()
