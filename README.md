# LinkedIn Employee Extractor

A Python tool for extracting employee data from LinkedIn company pages. This tool extracts profile URLs, descriptions, and automatically assigns companies based on profile information - all without visiting individual profiles (reducing the risk of being flagged as a bot).

## Features

- **Extract profile URLs** - Automatically searches and extracts links to employee profiles
- **Extract descriptions** - Extracts profile descriptions from the employee list (no need to visit individual profiles)
- **Auto-assign companies** - Automatically matches companies based on profile descriptions (from your companies list)
- **Update mode** - Update existing data without scraping new URLs
- **Safe extraction** - Extracts data from employee lists, not individual profiles (reduces ban risk)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/kamiljablonski/linkedin_employee_extractor.git
cd linkedin_employee_extractor
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Prepare your companies list:
   - Copy `companies.csv.example` to `companies.csv`
   - Add your company names (one per line, column header: `Name`)

4. Set up LinkedIn session:
   - The script will prompt you to log in manually on first run
   - Session cookies will be saved for future use

## Usage

### Normal Mode (Scrape new URLs)

```bash
python linkedin_scraper.py
```

This will:
- Search for each company from `companies.csv`
- Navigate to the company's employee list
- Extract profile URLs, descriptions, and assign companies
- Save results to `output/employees.csv`

### Update Mode (Update existing data only)

```bash
python linkedin_scraper.py --update
# or
python linkedin_scraper.py -u
```

This will:
- Load existing URLs from `output/employees.csv`
- For each company, extract descriptions and assign companies
- Update only existing records (no new URLs scraped)
- Extract data from employee lists (doesn't visit individual profiles)

## Output Format

The CSV file (`output/employees.csv`) contains the following columns:

- `Profile_URL` - LinkedIn profile URL
- `Description` - Profile description (extracted from employee list)
- `Company` - Assigned company name (from your companies list)

## Configuration

You can customize settings in `config.py`:

- `HEADLESS` - Headless mode (True/False)
- `DELAY_BETWEEN_ACTIONS` - Delay between actions in seconds
- `DELAY_BETWEEN_COMPANIES` - Delay between companies in seconds
- `MAX_EMPLOYEES_PER_COMPANY` - Maximum employees to extract per company
- `ELEMENT_TIMEOUT` - Element wait timeout in seconds

## How It Works

1. **Company Search**: For each company in your list, the script searches LinkedIn
2. **Employee List**: Navigates to the company's employee list page
3. **Data Extraction**: Extracts profile URLs and descriptions directly from the list (no individual profile visits)
4. **Company Assignment**: Matches company names from your list against profile descriptions
5. **Data Saving**: Saves all data incrementally (backup every page)

## Safety Features

- **No individual profile visits** - Extracts data from employee lists only
- **Rate limiting** - Configurable delays between actions
- **Session management** - Saves and reuses LinkedIn session cookies
- **Incremental saving** - Saves data after each page (prevents data loss)

## Important Notes

- LinkedIn may require CAPTCHA verification with intensive use
- Some companies may have limited visibility of employee lists
- The script automatically handles scrolling and pagination
- Data is saved after each company (backup in case of interruption)
- In update mode, the script does not scrape new URLs, only updates existing profiles
- Descriptions and companies are extracted/updated for each profile

## Troubleshooting

### Login Issues
- Make sure you're logged into LinkedIn in the browser
- Check that `linkedin_cookies.json` exists and is valid
- Try deleting `linkedin_cookies.json` and logging in again

### No Employees Found
- Some companies may have restricted employee list visibility
- Check if the company page is accessible
- Verify the company name matches LinkedIn exactly

### Timeout Errors
- Increase `ELEMENT_TIMEOUT` in `config.py`
- Check your internet connection
- LinkedIn may be slow to respond

## License

MIT License - feel free to use and modify as needed.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Disclaimer

This tool is for educational and research purposes. Please respect LinkedIn's Terms of Service and use responsibly. The authors are not responsible for any misuse of this tool.
