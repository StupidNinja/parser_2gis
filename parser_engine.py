import os
import logging
import datetime
import json
import pandas as pd
import functools
from time import sleep
from urllib.parse import unquote
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
import pathes

class Parser2GIS:
    def __init__(self, search_query, on_log=None, on_status_change=None, scrape_reviews=False, max_reviews=5, direct_url=None, on_review_update=None):
        self.search_query = search_query
        self.on_log = on_log
        self.on_status_change = on_status_change
        self.scrape_reviews = scrape_reviews
        self.max_reviews = max_reviews
        self.direct_url = direct_url
        self.on_review_update = on_review_update
        self.driver = None
        self.parsing_active = False
        self.reviews_active = True  # Control flag just for reviews
        self.page_count = 0
        self.output_filename = None

        # Data storage
        self.columns = ['Название', 'Телефон', 'Адрес', 'Ссылка', 'Широта', 'Долгота']
        if self.scrape_reviews:
            self.columns.append('Отзывы')
        self.data = {column: [] for column in self.columns}
        
    def stop_reviews(self):
        """Stop only the review scraping process"""
        self.reviews_active = False
        self.log("Review scraping will stop after current review", "warning")
        
    def log(self, message, level='info'):
        """Log message to both internal logger and UI logger if provided"""
        if level == 'info':
            logging.info(message)
        elif level == 'warning':
            logging.warning(message)
        elif level == 'error':
            logging.error(message)
            
        if self.on_log:
            self.on_log(message, level)
            
    def set_status(self, status):
        """Report status change to UI"""
        if self.on_status_change:
            self.on_status_change(status)
            
    def get_element_text(self, path):
        """Get text from element safely"""
        try:
            return self.driver.find_element(By.XPATH, path).text
        except NoSuchElementException:
            return ''
            
    def move_to_element(self, element):
        """Move to element safely"""
        try:
            webdriver.ActionChains(self.driver).move_to_element(element).perform()
        except StaleElementReferenceException:
            pass
            
    def element_click(self, element, path):
        """Click element safely"""
        try:
            element.find_element(By.XPATH, path).click()
            return True
        except:
            return False
    
    def wait_for_element(self, xpath, timeout=10):
        """Wait for element to be clickable"""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            return element
        except TimeoutException:
            return None
    
    def retry_with_backoff(self, func, max_retries=3):
        """Retry a function with exponential backoff"""
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = 2 ** attempt
                self.log(f"Retrying after {wait_time}s due to: {str(e)}", "warning")
                sleep(wait_time)
    
    def clean_memory(self, force=False):
        """Clean memory and trigger GC"""
        if (self.page_count % 3 == 0) or force:
            self.log("Running garbage collection", "info")
            self.driver.execute_script('if(window.gc) { window.gc(); }')
            
            # Clear browser console logs
            self.driver.execute_cdp_cmd('Log.clear', {})
            
            # Clear storage
            self.driver.execute_script('localStorage.clear(); sessionStorage.clear();')
    
    def setup_driver(self):
        """Set up optimized Chrome driver"""
        options = webdriver.ChromeOptions()
        
        # Performance optimizations
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--no-sandbox')
        options.add_argument('--blink-settings=imagesEnabled=false')
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-browser-side-navigation')
        
        # Disable unnecessary services
        prefs = {
            'profile.default_content_setting_values': {
                'images': 2,  # Block images
                'plugins': 2,  # Block plugins
                'popups': 2,  # Block popups
                'geolocation': 2,  # Block geolocation
                'notifications': 2  # Block notifications
            }
        }
        options.add_experimental_option('prefs', prefs)
        
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    def setup_network_interception(self):
        """Set up network interception to block unnecessary requests"""
        # Block unnecessary requests
        self.driver.execute_cdp_cmd('Network.enable', {})
        self.driver.execute_cdp_cmd('Network.setBlockedURLs', {
            'urls': [
                '*google-analytics*', '*/_/log*', '*/_/metrics*', 
                '*/favorites.api*', '*/fonts/*', '*/styles/*', 
                '*/tile*.maps*'
            ]
        })
        
        # Add API monitoring
        self.driver.execute_script("""
            window.api2gisResponses = [];
            (function() {
                const originalFetch = window.fetch;
                window.fetch = function() {
                    const promise = originalFetch.apply(this, arguments);
                    if (arguments[0] && arguments[0].includes('api.2gis')) {
                        promise.then(response => {
                            if (response.ok) {
                                response.clone().json().then(data => {
                                    window.api2gisResponses.push(data);
                                }).catch(() => {});
                            }
                        });
                    }
                    return promise;
                };
            })();
        """)
    
    def scrape_reviews(self, max_reviews=None, place_name=""):
        """Scrape reviews for the current item"""
        max_reviews = max_reviews or self.max_reviews
        reviews = []
        self.reviews_active = True  # Reset at the start of each place
    
        try:
            # Try to click on the reviews section/tab
            reviews_link = self.wait_for_element(pathes.reviews_hyperlink)
            if not reviews_link:
                self.log("No reviews section found or not clickable", "warning")
                return reviews
    
            reviews_link.click()
            self.log("Opened reviews section", "info")
            sleep(1.5)  # Wait for reviews to load
            
            # Get overall rating and total rating count
            try:
                overall_rating_element = self.driver.find_element(By.XPATH, pathes.review_overall_rating)
                overall_rating = overall_rating_element.text.strip()
                self.log(f"Overall rating: {overall_rating}", "info")
    
                total_rating_element = self.driver.find_element(By.XPATH, pathes.reviews_total_rating_count)
                total_rating_text = total_rating_element.text.strip()
    
                # Extract numeric count from text like "123 оценок"
                import re
                total_rating_count = "0"
                if match := re.search(r'(\d+)', total_rating_text):
                    total_rating_count = match.group(1)
    
                self.log(f"Total ratings: {total_rating_count}", "info")
                
                # If we have a callback for review updates, use it to notify UI
                if self.on_review_update:
                    try:
                        # Convert to int for UI display
                        max_available = int(total_rating_count)
                        
                        # If max_reviews is higher than what's available, adjust it
                        if max_reviews > max_available:
                            max_reviews = max_available
                            
                        # Update UI with current progress
                        self.on_review_update(place_name, 0, max_reviews)
                    except ValueError:
                        pass
            except Exception as e:
                self.log(f"Could not extract overall rating details: {e}", "warning")
                overall_rating = "0"
                total_rating_count = "0"
    
            # Loop to scrape reviews
            review_index = 1
            load_more_attempts = 0
            max_load_more_attempts = 15  # Maximum times to try clicking "Load More"
    
            # Continue until we reach max_reviews or run out of reviews to load
            while len(reviews) < max_reviews and self.parsing_active and self.reviews_active and load_more_attempts < max_load_more_attempts:
                # Notify UI of progress
                if self.on_review_update:
                    self.on_review_update(place_name, len(reviews), max_reviews)

                self.log(f"Extracted a total of {len(reviews)} reviews", "info")
               
                visible_reviews = []
                current_review_index = review_index

                # Try to extract visible reviews
                for i in range(current_review_index, current_review_index + 30):  # Try a reasonable range
                    if not self.parsing_active:
                        break

                    try:
                        # Check if reviewer name element exists
                        try:
                            reviewer_name_element = self.driver.find_element(By.XPATH, pathes.get_reviewer_name(i))
                        except NoSuchElementException:
                            continue  # Skip this index
                        
                        # Get reviewer name
                        reviewer_name = reviewer_name_element.text.strip()
                        if not reviewer_name:
                            continue

                        self.log(f"Processing review at index {i} with reviewer: {reviewer_name}", "info")

                        # Get star rating
                        try:
                            stars_container = self.driver.find_element(By.XPATH, pathes.get_review_stars_container(i))
                            star_count = pathes.count_stars_in_container(self.driver, stars_container)
                            stars_text = f"{star_count} stars"
                        except Exception as star_error:
                            self.log(f"Error counting stars: {star_error}", "warning")
                            stars_text = "Unknown rating"
                        # Get review text and expand if truncated
                        try:
                            review_text_element = self.driver.find_element(By.XPATH, pathes.get_review_text(i))
                            review_text = review_text_element.text.strip()

                            # Check if text is truncated (has "Читать целиком" or similar)
                            if "..." in review_text or "еще" in review_text.lower() or "целиком" in review_text.lower():
                                try:
                                    # Try to click the "read more" element if it exists
                                    read_more_elements = self.driver.find_elements(By.XPATH, f"//span[contains(@class, '_17ww69i')]")
                                    for element in read_more_elements:
                                        if element.is_displayed() and element.location['y'] > review_text_element.location['y'] and element.location['y'] < review_text_element.location['y'] + 200:
                                            element.click()
                                            sleep(0.5)
                                            # Get updated text after expanding
                                            review_text = self.driver.find_element(By.XPATH, pathes.get_review_text(i)).text.strip()
                                            break
                                except:
                                    self.log(f"Could not expand review text for review {i}", "warning")
                        except NoSuchElementException:
                            review_text = "[No review text found]"

                        # Get likes count
                        likes = "0"
                        try:
                            likes_element = self.driver.find_element(By.XPATH, pathes.get_review_likes(i))
                            likes = likes_element.text.strip()
                            if not likes:
                                likes = "0"
                        except:
                            pass
                        
                        # Create review data and add to list
                        review_data = {
                            "reviewer_name": reviewer_name,
                            "rating": stars_text,
                            "text": review_text,
                            "likes": likes
                        }
                        
                        # Add overall metrics to the first review only
                        if len(reviews) == 0:
                            review_data["overall_rating"] = overall_rating
                            review_data["total_ratings"] = total_rating_count
                        
                        visible_reviews.append(review_data)
                        
                    except Exception as e:
                        self.log(f"Error extracting review at index {i}: {e}", "warning")

                # When adding reviews to the collection, check if we should stop
                if visible_reviews:
                    self.log(f"Found {len(visible_reviews)} new reviews", "info")
                    for review in visible_reviews:
                        if len(reviews) < max_reviews and self.reviews_active:
                            reviews.append(review)
                        else:
                            # We've reached our target or review scraping was stopped
                            break

                    # Update review index to start after the last review we processed
                    review_index += len(visible_reviews) + 1

                # Check if we should continue loading more
                if not self.reviews_active:
                    self.log("Review scraping stopped by user", "warning")
                    break

                # If we haven't reached the target number of reviews yet, try to load more
                if len(reviews) < max_reviews:
                    # Try to find and click the "Load More" button
                    try:
                        # Method 1: Try to find the button by its class
                        load_more_buttons = self.driver.find_elements(By.XPATH, "//button[contains(@class, '_kuel4no')]")

                        if load_more_buttons and len(load_more_buttons) > 0 and load_more_buttons[0].is_displayed():
                            # Scroll to the button to ensure it's in view
                            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", load_more_buttons[0])
                            sleep(0.5)

                            # Click the button
                            load_more_buttons[0].click()
                            self.log("Clicked 'Load More' button", "info")
                            load_more_attempts += 1

                            # Wait for new reviews to load
                            sleep(2)
                        else:
                            # Method 2: Try alternative approach with button text
                            load_more_by_text = self.driver.execute_script("""
                                // Try to find any button that looks like "load more"
                                const buttons = Array.from(document.querySelectorAll('button'));
                                const loadMoreButton = buttons.find(btn => {
                                    const text = btn.textContent.toLowerCase();
                                    return text.includes('загрузить') || 
                                           text.includes('ещё') || 
                                           text.includes('еще') ||
                                           text.includes('показать');
                                });

                                if (loadMoreButton) {
                                    // Scroll to button
                                    loadMoreButton.scrollIntoView({behavior: 'smooth', block: 'center'});
                                    // Click it
                                    setTimeout(() => loadMoreButton.click(), 500);
                                    return true;
                                }
                                return false;
                            """)

                            if load_more_by_text:
                                self.log("Clicked 'Load More' button via JavaScript", "info")
                                load_more_attempts += 1
                                sleep(2)
                            else:
                                self.log("No 'Load More' button found - all reviews may be loaded", "info")
                                break
                    except Exception as e:
                        self.log(f"Error finding or clicking 'Load More' button: {e}", "warning")
                        # Try scrolling to the bottom as a fallback
                        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        sleep(1)
                        load_more_attempts += 1
                else:
                    self.log(f"Reached target of {max_reviews} reviews", "info")
                    break
                
            self.log(f"Extracted a total of {len(reviews)} reviews", "info")

        except Exception as e:
            self.log(f"Error in review scraping: {e}", "error")


        # Return to main screen
        try:
            self.driver.back()
            sleep(1)
        except:
            pass

        return reviews
    
    def save_data(self):
        """Save collected data to Excel file"""
        if not self.data or all(len(v) == 0 for v in self.data.values()):
            self.log("No data to save", "warning")
            return None
            
        # Ensure all arrays are the same length
        max_length = max(len(values) for values in self.data.values())
        for column in self.columns:
            while len(self.data[column]) < max_length:
                self.data[column].append('')
        
        # Create output folder if it doesn't exist
        os.makedirs("output", exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"output/{self.search_query}_{timestamp}.xlsx"
        
        self.log(f"Saving data to {filename}")
        
        # For Excel output, create a separate sheet for reviews if applicable
        if 'Отзывы' in self.data and any(self.data['Отзывы']):
            with pd.ExcelWriter(filename) as writer:
                # Write main data
                main_df = pd.DataFrame({col: self.data[col] for col in self.columns if col != 'Отзывы'})
                main_df.to_excel(writer, sheet_name='Businesses', index=False)
                
                # Process reviews and write to another sheet
                reviews_data = []
                for i, business_name in enumerate(self.data['Название']):
                    if i < len(self.data['Отзывы']) and self.data['Отзывы'][i]:
                        try:
                            business_reviews = json.loads(self.data['Отзывы'][i])
                            for review in business_reviews:
                                review['business_name'] = business_name
                                reviews_data.append(review)
                        except:
                            pass
                
                if reviews_data:
                    reviews_df = pd.DataFrame(reviews_data)
                    reviews_df.to_excel(writer, sheet_name='Reviews', index=False)
        else:
            # Just save the main data
            pd.DataFrame(self.data).to_excel(filename, index=False)
            
        self.log(f"Data saved successfully: {len(self.data['Название'])} records")
        return filename
    
    def start(self):
        """Start the parsing process"""
        if self.parsing_active:
            self.log("Parser is already running", "warning")
            return
            
        self.parsing_active = True
        self.reviews_active = True
        self.data = {column: [] for column in self.columns}
        
        # Determine URL based on inputs
        if self.direct_url:
            url = self.direct_url
            self.log(f"Starting parser with direct URL: {url}")
        else:
            self.log(f"Starting parser with query: {self.search_query}")
            url = f'https://2gis.ru/almaty/search/{self.search_query}'
        
        try:
            # Set up optimized Chrome driver
            self.driver = self.setup_driver()
            self.driver.set_window_size(1200, 800)
            
            # Set up network interception
            self.setup_network_interception()
            
            # Navigate to URL
            self.driver.get(url)
            self.log(f"Browser opened, navigating to: {url}")
            
            # Accept cookies if banner appears
            if self.element_click(self.driver, pathes.cookie_banner):
                self.log("Cookies accepted")
            
            # If using direct URL, we might be on a company page already
            if self.direct_url:
                # Try to detect if this is a company page
                try:
                    title = self.get_element_text(pathes.title)
                    if title:
                        self.log(f"Detected company page: {title}")
                        
                        # Extract company details
                        phone = ''
                        try:
                            phone_btn = self.wait_for_element(pathes.phone_btn, timeout=5)
                            if phone_btn:
                                phone_btn.click()
                                sleep(1.0)
                                phone = self.get_element_text(pathes.phone)
                        except:
                            pass
                        
                        address = self.get_element_text(pathes.address)
                        link = unquote(self.driver.current_url)
                        
                        # Store basic data
                        self.data['Название'].append(title)
                        self.data['Телефон'].append(phone)
                        self.data['Адрес'].append(address)
                        self.data['Ссылка'].append(link)
                        self.data['Широта'].append('')
                        self.data['Долгота'].append('')
                        
                        # Scrape reviews if configured
                        if self.scrape_reviews:
                            self.log(f"Scraping reviews for {title}")
                            reviews = self.scrape_reviews(place_name=title)
                            if reviews:
                                reviews_data = json.dumps(reviews, ensure_ascii=False)
                                self.data['Отзывы'].append(reviews_data)
                                self.log(f"Scraped {len(reviews)} reviews")
                            else:
                                self.data['Отзывы'].append('')
                        
                        # Skip search results processing
                        self.log("Direct URL processing complete")
                        self.output_filename = self.save_data()
                        return
                except Exception as e:
                    self.log(f"Error processing direct URL as company page: {e}", "warning")
                        # Go back to results
                    self.driver.back()
                    sleep(1.0)
                except Exception as e:
                    self.log(f"Error processing direct URL as company page: {e}", "warning")
                    
                # Go to next page (if applicable)
                page, pages = 0, 1  # Define default values for page and pages
                while self.parsing_active and page < pages - 1:
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    next_btn = self.wait_for_element(pathes.next_page_btn, timeout=5)
                    if next_btn:
                        next_btn.click()
                        self.log(f"Moving to page {page+2}")
                        sleep(2.0)  # Increased wait time for page to load
                        page += 1
                    else:
                        self.log("Could not find next page button", "warning")
                        break
        
        except Exception as e:
            self.log(f"Error occurred: {e}", "error")

        finally:
            if self.driver:
                self.driver.quit()
                self.log("Browser closed")

            self.parsing_active = False
            self.reviews_active = False
            self.set_status("Ready")
            
    def stop(self):
        """Stop the parsing process"""
        if self.parsing_active:
            self.log("Stopping parser...")
            self.parsing_active = False
            return True
        return False
    
def sandbox():
    """Sandbox environment for testing parser functionality and XPath expressions"""
    print("=== 2GIS Parser Sandbox ===")
    print("This is a testing environment for parser functionality.")
    
    # Create a basic configuration
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
    )
    
    # Ask for test URL or use default
    test_url = input("Enter test URL (or press Enter for default search): ").strip()
    if not test_url:
        search_term = input("Enter search term (default: 'Застройщики'): ").strip() or "Застройщики"
        test_url = f'https://2gis.ru/almaty/search/{search_term}'
    
    print(f"Opening browser with URL: {test_url}")
    
    # Set up driver with visualizations enabled for testing
    options = webdriver.ChromeOptions()
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-sandbox')
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.set_window_size(1200, 800)
    
    try:
        # Navigate to URL
        driver.get(test_url)
        print("Browser opened successfully")
        
        # Accept cookies if banner appears
        try:
            cookie_btn = driver.find_element(By.XPATH, pathes.cookie_banner)
            if cookie_btn:
                cookie_btn.click()
                print("Cookies accepted")
        except:
            print("No cookie banner found or could not click it")
        
        # Main interaction loop
        while True:
            print("\nOptions:")
            print("1. Test XPath expression")
            print("2. Test clicking on element")
            print("3. Extract reviews for current page")
            print("4. Navigate to URL")
            print("5. Extract all text from current page")
            print("6. Highlight element by XPath") 
            print("7. Exit sandbox")
            print("8. Scroll element by XPath")
            print("9. Automated review scraping for multiple places")
            
            choice = input("Select option (1-9): ").strip()
            
            if choice == '1':
                xpath = input("Enter XPath expression: ").strip()
                try:
                    elements = driver.find_elements(By.XPATH, xpath)
                    print(f"Found {len(elements)} elements")
                    for i, element in enumerate(elements[:5]):  # Show first 5 elements
                        print(f"Element {i+1}:")
                        print(f"  Text: {element.text}")
                        print(f"  Tag: {element.tag_name}")
                        print(f"  Attributes: {element.get_attribute('outerHTML')[:100]}...")
                    
                    if len(elements) > 5:
                        print(f"...and {len(elements) - 5} more elements")
                except Exception as e:
                    print(f"Error: {e}")
            
            elif choice == '2':
                xpath = input("Enter XPath for element to click: ").strip()
                try:
                    element = driver.find_element(By.XPATH, xpath)
                    print(f"Found element: {element.tag_name}")
                    
                    # Scroll to element
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                    sleep(1)
                    
                    # Highlight before clicking
                    driver.execute_script("arguments[0].style.border='3px solid red'", element)
                    sleep(1)
                    
                    # Click
                    element.click()
                    print("Element clicked")
                    
                    # Ask if they want to go back
                    if input("Go back? (y/n): ").lower() == 'y':
                        driver.back()
                        print("Navigated back")
                except Exception as e:
                    print(f"Error clicking element: {e}")
            
            elif choice == '3':
                print("Enhanced review extraction with 'Load More' support...")
                
                overall_rating = "0"
                total_ratings = "0"
                
                try:
                    overall_rating_element = driver.find_element(By.XPATH, pathes.review_overall_rating)
                    overall_rating = overall_rating_element.text.strip()
                    print(f"Overall rating: {overall_rating}")

                    total_rating_element = driver.find_element(By.XPATH, pathes.reviews_total_rating_count)
                    total_rating_text = total_rating_element.text.strip()

                    # Extract numeric count from text like "123 оценок"
                    if match := re.search(r'(\d+)', total_rating_text):
                        total_ratings = match.group(1)

                    print(f"Total ratings: {total_ratings}")
                except Exception as e:
                    print(f"Could not extract overall rating details: {e}")

                
                # Try to determine if we're on a company page
                try:
                    title = driver.find_element(By.XPATH, pathes.title).text
                    print(f"Current page appears to be for: {title}")
                    
                    # Try to navigate to reviews tab
                    try:
                        reviews_link = driver.find_element(By.XPATH, pathes.reviews_hyperlink)
                        reviews_count_text = driver.find_element(By.XPATH, pathes.reviews_count).text
                        print(f"Found reviews link with count: {reviews_count_text}")
                        reviews_link.click()
                        print("Navigated to reviews tab")
                        sleep(1.5)
                        
                        # Extract expected review count from text (e.g. "123 отзыва")
                        import re
                        expected_reviews = 0
                        if match := re.search(r'(\d+)', reviews_count_text):
                            expected_reviews = int(match.group(1))
                            print(f"Expecting approximately {expected_reviews} reviews")
                        
                        # Determine how many reviews to extract
                        max_reviews = int(input(f"How many reviews to extract? (max available: {expected_reviews}, default: 10): ") or "10")
                        max_reviews = min(max_reviews, expected_reviews) if expected_reviews > 0 else max_reviews
                        
                        # Track already processed reviews to avoid duplicates
                        processed_reviews = set()
                        all_reviews = []
                        review_index = 1
                        
                        # Set a maximum number of load more attempts to prevent infinite loops
                        load_more_attempts = 0
                        max_load_more_attempts = 15
                        
                        while len(all_reviews) < max_reviews and load_more_attempts < max_load_more_attempts:
                            print(f"\nExtraction cycle {load_more_attempts + 1}")
                            
                            # Extract current batch of reviews
                            new_reviews = []
                            
                            # Try a range of indices to find visible reviews
                            for i in range(review_index, review_index + 50):
                                try:
                                    # First verify the reviewer name element exists
                                    try:
                                        reviewer_name_element = driver.find_element(By.XPATH, pathes.get_reviewer_name(i))
                                    except NoSuchElementException:
                                        continue  # Skip this index
                                    
                                    # Get reviewer name
                                    reviewer_name = reviewer_name_element.text.strip()
                                    if not reviewer_name:
                                        continue
                                    
                                    # Create a unique identifier for this review to avoid duplicates
                                    review_id = f"{reviewer_name}_{i}"
                                    if review_id in processed_reviews:
                                        continue
                                        
                                    print(f"Processing review at index {i} with reviewer: {reviewer_name}")
                                    
                                    # Get star rating
                                    try:
                                        stars_container = driver.find_element(By.XPATH, pathes.get_review_stars_container(i))

                                        # Just count the spans to determine rating
                                        spans = stars_container.find_elements(By.TAG_NAME, "span")
                                        star_count = len(spans)

                                        print(f"  Found {star_count} spans in stars container")

                                        # Limit to 5 stars
                                        if star_count > 5:
                                            star_count = 5

                                        stars_text = f"{star_count} stars"

                                        # If no spans, try alternative approach
                                        if star_count == 0:
                                            star_count = driver.execute_script("""
                                                const container = arguments[0];
                                                const svgPaths = container.querySelectorAll('svg path');
                                                let goldFillCount = 0;

                                                for (const path of svgPaths) {
                                                    const fill = path.getAttribute('fill');
                                                    if (fill && (fill.includes('ffb') || fill.includes('FF') || fill.includes('gold'))) {
                                                        goldFillCount++;
                                                    }
                                                }

                                                return goldFillCount || 5;
                                            """, stars_container)
                                            stars_text = f"{star_count} stars (SVG method)"
                                    except Exception as e:
                                        print(f"  Error counting stars: {e}")
                                        stars_text = "Unknown rating"
                                    
                                    # Get review text and check if we need to expand it
                                    try:
                                        review_text_element = driver.find_element(By.XPATH, pathes.get_review_text(i))
                                        review_text = review_text_element.text.strip()
                                        
                                        # Check if text is truncated and needs expansion
                                        # Look for read more button below this review
                                        try:
                                            read_more_elements = driver.find_elements(By.XPATH, f"//span[contains(@class, '_17ww69i')]")
                                            for element in read_more_elements:
                                                if element.is_displayed() and element.location['y'] > review_text_element.location['y'] and element.location['y'] < review_text_element.location['y'] + 200:
                                                    print(f"  Expanding truncated review {i}...")
                                                    element.click()
                                                    sleep(0.5)
                                                    # Get updated text after expanding
                                                    review_text = driver.find_element(By.XPATH, pathes.get_review_text(i)).text.strip()
                                                    break
                                        except:
                                            print(f"  Could not expand review text for review {i}")
                                    except NoSuchElementException:
                                        review_text = "[No review text found]"
                                    
                                    # Get likes count
                                    likes = "0"
                                    try:
                                        likes_element = driver.find_element(By.XPATH, pathes.get_review_likes(i))
                                        likes = likes_element.text.strip()
                                        if not likes:
                                            likes = "0"
                                    except:
                                        pass
                                    
                                    # Create review data
                                    review_data = {
                                        "reviewer_name": reviewer_name,
                                        "rating": stars_text,
                                        "text": review_text,
                                        "likes": likes,
                                        "index": i
                                    }
                                    # Add overall metrics to the first review only
                                    if len(all_reviews) == 0 and len(new_reviews) == 0:
                                        review_data["overall_rating"] = overall_rating
                                        review_data["total_ratings"] = total_ratings

                                    new_reviews.append(review_data)
                                    processed_reviews.add(review_id)
                                    
                                except Exception as e:
                                    print(f"Error extracting review at index {i}: {e}")
                            
                            # Add new reviews to our collection
                            if new_reviews:
                                all_reviews.extend(new_reviews)
                                print(f"Extracted {len(new_reviews)} reviews in this batch, {len(all_reviews)} total")
                                
                                # Update the review index to start after the highest index we've processed
                                if new_reviews:
                                    highest_index = max(r["index"] for r in new_reviews)
                                    review_index = highest_index + 1
                                    print(f"Next review index will be {review_index}")
                            else:
                                print("No new reviews found in current view")
                            
                            # Check if we've reached the target number
                            if len(all_reviews) >= max_reviews:
                                print(f"Reached target of {max_reviews} reviews")
                                break
                            
                            # Try to find and click the "Load More" button
                            try:
                                # First try to find by class
                                load_more_buttons = driver.find_elements(By.XPATH, "//button[contains(@class, '_kuel4no')]")
                                
                                if load_more_buttons and len(load_more_buttons) > 0 and load_more_buttons[0].is_displayed():
                                    # Scroll to button
                                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", load_more_buttons[0])
                                    sleep(0.5)
                                    
                                    # Highlight button before clicking
                                    driver.execute_script("arguments[0].style.border='3px solid red';", load_more_buttons[0])
                                    sleep(0.5)
                                    
                                    # Click the button
                                    load_more_buttons[0].click()
                                    print("Clicked 'Load More' button")
                                    load_more_attempts += 1
                                    
                                    # Wait for new reviews to load
                                    sleep(2)
                                else:
                                    # Try alternative approach with button text
                                    load_more_by_text = driver.execute_script("""
                                        // Try to find any button that looks like "load more"
                                        const buttons = Array.from(document.querySelectorAll('button'));
                                        const loadMoreButton = buttons.find(btn => {
                                            const text = btn.textContent.toLowerCase();
                                            return text.includes('загрузить') || 
                                                   text.includes('ещё') || 
                                                   text.includes('еще') ||
                                                   text.includes('показать');
                                        });
                                        
                                        if (loadMoreButton) {
                                            // Highlight the button we found
                                            loadMoreButton.style.border = '3px solid red';
                                            // Scroll it into view
                                            loadMoreButton.scrollIntoView({behavior: 'smooth', block: 'center'});
                                            // Click it
                                            setTimeout(() => loadMoreButton.click(), 500);
                                            return true;
                                        }
                                        return false;
                                    """)
                                    
                                    if load_more_by_text:
                                        print("'Load More' button clicked via JavaScript")
                                        load_more_attempts += 1
                                        sleep(2)
                                    else:
                                        print("No 'Load More' button found - all reviews may be loaded")
                                        break
                            except Exception as e:
                                print(f"Error finding or clicking 'Load More' button: {e}")
                                # Try scrolling to the bottom as a fallback
                                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                                sleep(2)
                                load_more_attempts += 1
                                if load_more_attempts >= max_load_more_attempts:
                                    print(f"Reached maximum load attempts ({max_load_more_attempts})")
                                    break
                                
                        # Display and save results
                        if all_reviews:
                            print(f"\n=== EXTRACTED {len(all_reviews)} REVIEWS ===")
                            for i, review in enumerate(all_reviews[:5]):  # Show first 5 reviews
                                print(f"\nReview {i+1}:")
                                print(f"  Reviewer: {review['reviewer_name']}")
                                print(f"  Rating: {review['rating']}")
                                print(f"  Text: {review['text'][:100]}..." if len(review['text']) > 100 else f"  Text: {review['text']}")
                                print(f"  Likes: {review['likes']}")
                            
                            if len(all_reviews) > 5:
                                print(f"\n...and {len(all_reviews) - 5} more reviews")
                            
                            # Ask if user wants to save reviews
                            if input("\nSave reviews to JSON file? (y/n): ").lower() == 'y':
                                import json
                                from datetime import datetime
                                
                                # Create output directory
                                import os
                                os.makedirs("sandbox_output", exist_ok=True)
                                
                                # Generate filename
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                filename = f"sandbox_output/reviews_{title.replace(' ', '_')}_{timestamp}.json"
                                
                                # Save to file
                                with open(filename, 'w', encoding='utf-8') as f:
                                    json.dump({
                                        'company': title,
                                        'reviews': all_reviews,
                                        'extraction_date': datetime.now().isoformat()
                                    }, f, ensure_ascii=False, indent=2)
                                
                                print(f"Reviews saved to {filename}")
                        else:
                            print("No reviews were extracted")
                    except Exception as e:
                        print(f"Error navigating to reviews tab: {e}")
                except Exception as e:
                    print(f"This doesn't appear to be a company page: {e}")
                    print("Please navigate to a company page first.")
            elif choice == '4':
                new_url = input("Enter URL to navigate to: ").strip()
                try:
                    driver.get(new_url)
                    print(f"Navigated to: {new_url}")
                except Exception as e:
                    print(f"Error navigating: {e}")
            
            elif choice == '5':
                print("Extracting all text from current page...")
                all_text = driver.find_element(By.XPATH, "/html/body").text
                print("\n=== PAGE TEXT ===")
                print(all_text[:2000])  # Show first 2000 chars
                print("...")
                print("(Text truncated. Full page text is available)")
            
            elif choice == '6':
                xpath = input("Enter XPath for element to highlight: ").strip()
                try:
                    elements = driver.find_elements(By.XPATH, xpath)
                    print(f"Found {len(elements)} elements to highlight")
                    
                    for i, element in enumerate(elements[:10]):  # Highlight up to 10 elements
                        # Scroll to element
                        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                        sleep(0.5)
                        
                        # Highlight with different colors based on index
                        colors = ['red', 'blue', 'green', 'purple', 'orange', 'magenta', 'teal', 'brown', 'cyan', 'lime']
                        color = colors[i % len(colors)]
                        
                        # Add a number label
                        driver.execute_script(f"""
                            arguments[0].style.border='3px solid {color}';
                            let label = document.createElement('div');
                            label.style.position = 'absolute';
                            label.style.backgroundColor = '{color}';
                            label.style.color = 'white';
                            label.style.padding = '2px 6px';
                            label.style.borderRadius = '10px';
                            label.style.fontSize = '14px';
                            label.style.fontWeight = 'bold';
                            label.style.zIndex = '9999';
                            label.innerText = '{i+1}';
                            document.body.appendChild(label);
                            let rect = arguments[0].getBoundingClientRect();
                            label.style.top = (rect.top + window.scrollY - 10) + 'px';
                            label.style.left = (rect.left + window.scrollX - 10) + 'px';
                        """, element)
                    
                    print("Elements highlighted (press Enter to continue)")
                    input()
                    
                    # Remove highlights
                    driver.execute_script("""
                        // Remove all highlight borders
                        document.querySelectorAll('*').forEach(el => {
                            if (el.style.border.includes('solid')) {
                                el.style.border = '';
                            }
                        });
                        
                        // Remove all labels
                        document.querySelectorAll('div').forEach(el => {
                            if (el.style.zIndex === '9999') {
                                el.remove();
                            }
                        });
                    """)
                    print("Highlights removed")
                except Exception as e:
                    print(f"Error highlighting elements: {e}")
            
            elif choice == '7':
                print("Exiting sandbox...")
                break
            
            elif choice == '8':
                print("Scroll element by XPath")
                xpath = input("Enter XPath of element to scroll: ").strip()
                scroll_amount = input("Enter scroll amount in pixels (default: 3000): ").strip() or "3000"

                try:
                    # First verify if the element exists
                    try:
                        element = driver.find_element(By.XPATH, xpath)
                        print(f"Found scrollable element: {element.tag_name}")
                    except NoSuchElementException:
                        print("Element not found. Please check your XPath.")
                        continue

                    # Ask for scrolling method
                    print("\nScrolling methods:")
                    print("1. Scroll using JavaScript scrollTop")
                    print("2. Scroll using JavaScript scrollIntoView")
                    print("3. Scroll using JavaScript scrollBy")
                    scroll_method = input("Select method (1-3, default: 1): ").strip() or "1"

                    if scroll_method == "1":
                        # Method 1: Scroll using scrollTop (best for container scrolling)
                        result = driver.execute_script(f"""
                            // Function to scroll container by XPath
                            function scrollContainerByXPath(xpath, scrollAmount) {{
                                const xpathResult = document.evaluate(
                                    xpath, 
                                    document, 
                                    null, 
                                    XPathResult.FIRST_ORDERED_NODE_TYPE, 
                                    null
                                );
                                const container = xpathResult.singleNodeValue;
                                if (container) {{
                                    const previousScrollTop = container.scrollTop;
                                    container.scrollTop += parseInt(scrollAmount);

                                    // Return information about the scroll operation
                                    return {{
                                        success: true,
                                        previousScrollTop: previousScrollTop,
                                        newScrollTop: container.scrollTop,
                                        scrollChange: container.scrollTop - previousScrollTop,
                                        element: container.tagName,
                                        scrollHeight: container.scrollHeight,
                                        clientHeight: container.clientHeight
                                    }};
                                }}
                                return {{ success: false, error: "Element not found or not scrollable" }};
                            }}

                            return scrollContainerByXPath("{xpath}", {scroll_amount});
                        """)

                        if result.get('success'):
                            print("Scroll successful!")
                            print(f"Scrolled from {result.get('previousScrollTop')} to {result.get('newScrollTop')} ({result.get('scrollChange')} pixels)")
                            print(f"Container: {result.get('element')}, Total height: {result.get('scrollHeight')}, Visible height: {result.get('clientHeight')}")
                        else:
                            print(f"Scroll failed: {result.get('error')}")

                            # Try alternate approach - scroll the document
                            print("Trying alternate approach: scrolling the document...")
                            driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                            print("Document scrolled")

                    elif scroll_method == "2":
                        # Method 2: Scroll element into view (good for scrolling to see an element)
                        driver.execute_script(f"""
                            const xpathResult = document.evaluate(
                                "{xpath}", 
                                document, 
                                null, 
                                XPathResult.FIRST_ORDERED_NODE_TYPE, 
                                null
                            );
                            const element = xpathResult.singleNodeValue;
                            if (element) {{
                                element.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                            }}
                        """)
                        print(f"Scrolled element into view")

                    elif scroll_method == "3":
                        # Method 3: Use scrollBy on the element (alternative approach)
                        driver.execute_script(f"""
                            const xpathResult = document.evaluate(
                                "{xpath}", 
                                document, 
                                null, 
                                XPathResult.FIRST_ORDERED_NODE_TYPE, 
                                null
                            );
                            const element = xpathResult.singleNodeValue;
                            if (element) {{
                                element.scrollBy(0, {scroll_amount});
                                return true;
                            }}
                            return false;
                        """)
                        print(f"Used scrollBy on element")

                    # Wait a moment to see the results
                    sleep(2)

                    # Check if scrolling loaded more content
                    print("\nChecking if new content loaded...")
                    current_height = driver.execute_script(f"""
                        const xpathResult = document.evaluate(
                            "{xpath}", 
                            document, 
                            null, 
                            XPathResult.FIRST_ORDERED_NODE_TYPE, 
                            null
                        );
                        const container = xpathResult.singleNodeValue;
                        return container ? container.scrollHeight : document.body.scrollHeight;
                    """)

                    print(f"Current scroll height: {current_height}")

                    # Option to continue scrolling
                    if input("Continue scrolling? (y/n): ").lower() == 'y':
                        scrolls = int(input("How many more scrolls? (default: 3): ").strip() or "3")

                        for i in range(scrolls):
                            print(f"Additional scroll {i+1}/{scrolls}...")
                            driver.execute_script(f"""
                                const xpathResult = document.evaluate(
                                    "{xpath}", 
                                    document, 
                                    null, 
                                    XPathResult.FIRST_ORDERED_NODE_TYPE, 
                                    null
                                );
                                const container = xpathResult.singleNodeValue;
                                if (container) {{
                                    container.scrollTop += {scroll_amount};
                                }} else {{
                                    window.scrollBy(0, {scroll_amount});
                                }}
                            """)
                            sleep(2)  # Wait between scrolls

                        print("Multiple scrolling completed")

                except Exception as e:
                    print(f"Error scrolling element: {e}")
                    import traceback
                    traceback.print_exc()
            elif choice == '9':
                # Replace the input_type handling in option 9 with this more robust version
                print("=== Automated Review Scraping for Multiple Places ===")
                # Ask for file with URLs or search term - with better error handling
                while True:
                    input_type = input("Enter input type (1. Search term, 2. File with URLs): ").strip()
                    
                    # Check if input contains Cyrillic - user might be entering search term directly
                    has_cyrillic = any(ord(char) > 127 for char in input_type)
                    if has_cyrillic or len(input_type) > 5:
                        print("It seems you entered a search term directly. I'll use this as your search term.")
                        search_term = input_type
                        input_type = "1"  # Set to search term mode
                        break
                        
                    # Normal flow - check for valid option
                    if input_type in ["1", "2"]:
                        break
                    else:
                        print("Please enter either 1 (for search term) or 2 (for file with URLs)")
                
                # Default review count per place
                try:
                    max_reviews_per_place = int(input("Enter max reviews per place (default: 150): ").strip() or "150")
                    if max_reviews_per_place <= 0:
                        print("Invalid number. Using default 150.")
                        max_reviews_per_place = 150
                except ValueError:
                    print("Invalid number. Using default 150.")
                    max_reviews_per_place = 150
                
                places_to_process = []
                
                if input_type == "1":
                    # Search term approach - get search term if not already provided
                    if not 'search_term' in locals():
                        search_term = input("Enter search term: ").strip()
                    
                    if not search_term:
                        print("Search term is required")
                        continue
                    
                    print(f"Using search term: {search_term}")
                    
                    # Navigate to search results
                    search_url = f"https://2gis.ru/almaty/search/{search_term}"
                    driver.get(search_url)
                    print(f"Navigated to search results for: {search_term}")
                    sleep(2)
                    
                    # Ask how many places to process from results
                    places_count = int(input("How many places to process from search results? (default: 5): ").strip() or "5")
                    
                    # Extract place links from search results
                    try:
                        # Get place cards from search results
                        place_cards = driver.find_elements(By.XPATH, "//div[contains(@class, '_1h3cgic')]")
                        print(f"Found {len(place_cards)} place cards in search results")
                        
                        # Extract clickable elements for each place
                        for i, card in enumerate(place_cards[:places_count]):
                            try:
                                # Get place name for reference
                                place_name = card.find_element(By.XPATH, ".//span[contains(@class, '_tvxwjf')]").text
                                places_to_process.append({
                                    "name": place_name,
                                    "element": card,
                                    "type": "element"
                                })
                                print(f"Added place: {place_name}")
                            except Exception as e:
                                print(f"Could not process card {i+1}: {e}")
                    except Exception as e:
                        print(f"Error extracting place cards: {e}")
                
                elif input_type == "2":
                    # File with URLs approach
                    file_path = input("Enter path to file with URLs (one per line): ").strip()
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            urls = [line.strip() for line in f if line.strip()]
                        
                        print(f"Loaded {len(urls)} URLs from file")
                        
                        # Create place objects with URLs
                        for i, url in enumerate(urls):
                            places_to_process.append({
                                "name": f"Place from URL {i+1}",
                                "url": url,
                                "type": "url"
                            })
                    except Exception as e:
                        print(f"Error loading URLs from file: {e}")
                else:
                    print("Invalid input type")
                    continue
                
                # Prepare for saving all collected reviews
                import json
                from datetime import datetime
                
                # Create output directory
                os.makedirs("reviews_output", exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                # All reviews combined for final output
                all_places_reviews = []
                
                # Process each place
                for place_idx, place in enumerate(places_to_process):
                    print(f"\n[{place_idx+1}/{len(places_to_process)}] Processing place: {place['name']}")
                    
                    # Navigate to place page
                    try:
                        if place["type"] == "element":
                            # Click on the element to open place page
                            place["element"].click()
                            sleep(2)
                        else:
                            # Navigate to URL
                            driver.get(place["url"])
                            sleep(2)
                        
                        # Try to get more accurate place name from page
                        try:
                            place_title = driver.find_element(By.XPATH, pathes.title).text
                            if place_title:
                                place["name"] = place_title
                                print(f"Updated place name: {place_title}")
                        except:
                            pass
                        
                        # Get and store place details
                        place_details = {
                            "name": place["name"],
                            "url": driver.current_url,
                            "reviews": []
                        }
                        
                        # Try to navigate to reviews tab
                        try:
                            reviews_link = driver.find_element(By.XPATH, pathes.reviews_hyperlink)
                            reviews_count_text = driver.find_element(By.XPATH, pathes.reviews_count).text
                            print(f"Found reviews link with count: {reviews_count_text}")
                            reviews_link.click()
                            print("Navigated to reviews tab")
                            sleep(1.5)
                            
                            # Get overall rating and total ratings count
                            try:
                                overall_rating_element = driver.find_element(By.XPATH, pathes.review_overall_rating)
                                overall_rating = overall_rating_element.text.strip()
                                place_details["overall_rating"] = overall_rating
                                
                                total_rating_element = driver.find_element(By.XPATH, pathes.reviews_total_rating_count)
                                total_rating_text = total_rating_element.text.strip()
                                
                                if match := re.search(r'(\d+)', total_rating_text):
                                    total_ratings = match.group(1)
                                    place_details["total_ratings"] = total_ratings
                                    print(f"Overall rating: {overall_rating}, Total ratings: {total_ratings}")
                            except Exception as e:
                                print(f"Could not extract rating details: {e}")
                            
                            # Extract expected review count
                            expected_reviews = 0
                            if match := re.search(r'(\d+)', reviews_count_text):
                                expected_reviews = int(match.group(1))
                                print(f"Expecting approximately {expected_reviews} reviews")
                            
                            # Calculate how many reviews to extract
                            reviews_to_extract = min(max_reviews_per_place, expected_reviews) if expected_reviews > 0 else max_reviews_per_place
                            print(f"Will attempt to extract up to {reviews_to_extract} reviews")
                            
                            # Extract reviews using the same logic as in option 3
                            processed_reviews = set()
                            reviews = []
                            review_index = 1
                            load_more_attempts = 0
                            max_load_more_attempts = 20  # Increased for better coverage
                            
                            while len(reviews) < reviews_to_extract and load_more_attempts < max_load_more_attempts:
                                print(f"  Extraction cycle {load_more_attempts + 1}, {len(reviews)}/{reviews_to_extract} reviews so far")
                                
                                # Extract current batch of reviews
                                new_reviews = []
                                
                                # Process reviews in the current view
                                for i in range(review_index, review_index + 50):
                                    if len(reviews) + len(new_reviews) >= reviews_to_extract:
                                        break  # We have enough reviews
                                        
                                    try:
                                        # Check if reviewer name element exists
                                        try:
                                            reviewer_name_element = driver.find_element(By.XPATH, pathes.get_reviewer_name(i))
                                        except NoSuchElementException:
                                            continue  # Skip this index
                                        
                                        # Get reviewer name
                                        reviewer_name = reviewer_name_element.text.strip()
                                        if not reviewer_name:
                                            continue
                                        
                                        # Create unique ID to avoid duplicates
                                        review_id = f"{reviewer_name}_{i}"
                                        if review_id in processed_reviews:
                                            continue
                                            
                                        print(f"    Processing review {i} by {reviewer_name}")
                                        
                                        # Extract star rating
                                        try:
                                            stars_container = driver.find_element(By.XPATH, pathes.get_review_stars_container(i))
                                            star_count = pathes.count_stars_in_container(driver, stars_container)
                                            stars_text = f"{star_count} stars"
                                        except Exception as e:
                                            print(f"    Error counting stars: {e}")
                                            stars_text = "Unknown rating"
                                        
                                        # Extract review text and expand if needed
                                        try:
                                            review_text_element = driver.find_element(By.XPATH, pathes.get_review_text(i))
                                            review_text = review_text_element.text.strip()
                                            
                                            # Check for truncated text
                                            if "..." in review_text or "еще" in review_text.lower() or "целиком" in review_text.lower():
                                                try:
                                                    # Find and click "read more" if available
                                                    read_more_elements = driver.find_elements(By.XPATH, "//span[contains(@class, '_17ww69i')]")
                                                    for element in read_more_elements:
                                                        if element.is_displayed() and element.location['y'] > review_text_element.location['y'] and element.location['y'] < review_text_element.location['y'] + 200:
                                                            element.click()
                                                            sleep(0.5)
                                                            # Get updated text
                                                            review_text = driver.find_element(By.XPATH, pathes.get_review_text(i)).text.strip()
                                                            break
                                                except:
                                                    print(f"    Could not expand truncated text")
                                        except:
                                            review_text = "[No review text found]"
                                            
                                        # Get likes count
                                        likes = "0"
                                        try:
                                            likes_element = driver.find_element(By.XPATH, pathes.get_review_likes(i))
                                            likes = likes_element.text.strip()
                                            if not likes:
                                                likes = "0"
                                        except:
                                            pass
                                            
                                        # Create review data object
                                        review_data = {
                                            "reviewer_name": reviewer_name,
                                            "rating": stars_text,
                                            "text": review_text,
                                            "likes": likes,
                                            "index": i
                                        }
                                        
                                        new_reviews.append(review_data)
                                        processed_reviews.add(review_id)
                                        
                                    except Exception as e:
                                        print(f"    Error processing review {i}: {e}")
                                
                                # Add new reviews to our collection
                                if new_reviews:
                                    reviews.extend(new_reviews)
                                    print(f"    Added {len(new_reviews)} reviews, total: {len(reviews)}/{reviews_to_extract}")
                                    
                                    # Update index for next batch
                                    if new_reviews:
                                        highest_index = max(r["index"] for r in new_reviews)
                                        review_index = highest_index + 1
                                
                                # Check if we have enough reviews
                                if len(reviews) >= reviews_to_extract:
                                    print(f"    Reached target of {reviews_to_extract} reviews")
                                    break
                                    
                                # Try to click "Load More" if needed
                                try:
                                    # Try to find the button by class or text
                                    load_more_clicked = False
                                    
                                    # Method 1: Try by class
                                    load_more_buttons = driver.find_elements(By.XPATH, "//button[contains(@class, '_kuel4no')]")
                                    if load_more_buttons and len(load_more_buttons) > 0 and load_more_buttons[0].is_displayed():
                                        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", load_more_buttons[0])
                                        sleep(0.5)
                                        load_more_buttons[0].click()
                                        load_more_clicked = True
                                    
                                    # Method 2: Try by text content
                                    if not load_more_clicked:
                                        load_more_by_text = driver.execute_script("""
                                            const buttons = Array.from(document.querySelectorAll('button'));
                                            const loadMoreBtn = buttons.find(btn => {
                                                const text = btn.textContent.toLowerCase();
                                                return text.includes('загрузить') || 
                                                       text.includes('ещё') || 
                                                       text.includes('еще') ||
                                                       text.includes('показать');
                                            });
                                            
                                            if (loadMoreBtn) {
                                                loadMoreBtn.scrollIntoView({behavior: 'smooth', block: 'center'});
                                                setTimeout(() => loadMoreBtn.click(), 500);
                                                return true;
                                            }
                                            return false;
                                        """)
                                        
                                        if load_more_by_text:
                                            load_more_clicked = True
                                    
                                    if load_more_clicked:
                                        print("    Clicked 'Load More' button")
                                        load_more_attempts += 1
                                        sleep(2)  # Wait for new reviews to load
                                    else:
                                        print("    No 'Load More' button found - all reviews may be loaded")
                                        break
                                        
                                except Exception as e:
                                    print(f"    Error clicking 'Load More': {e}")
                                    # Try scrolling to bottom as fallback
                                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                                    sleep(1)
                                    load_more_attempts += 1
                                    
                                    if load_more_attempts >= max_load_more_attempts:
                                        print(f"    Reached maximum load attempts ({max_load_more_attempts})")
                                        break
                            
                            # Store collected reviews
                            place_details["reviews"] = reviews
                            all_places_reviews.append(place_details)
                            
                            print(f"Collected {len(reviews)} reviews for {place['name']}")
                            
                            # Save individual place reviews
                            place_filename = f"reviews_output/{timestamp}_{place_idx+1}_{place['name'].replace(' ', '_')[:30]}.json"
                            with open(place_filename, 'w', encoding='utf-8') as f:
                                json.dump(place_details, f, ensure_ascii=False, indent=2)
                                
                            print(f"Saved reviews to {place_filename}")
                            
                        except Exception as e:
                            print(f"Error processing reviews for {place['name']}: {e}")
                        
                        # Navigate back to search results if we're processing elements
                        if place["type"] == "element" and place_idx < len(places_to_process) - 1:
                            driver.back()
                            sleep(2)  # Wait for search results to reload
                            
                            # Re-extract place cards if needed
                            if place_idx < len(places_to_process) - 1 and places_to_process[place_idx+1]["type"] == "element":
                                # We need to refresh the elements as they become stale after navigation
                                place_cards = driver.find_elements(By.XPATH, "//div[contains(@class, '_1h3cgic')]")
                                for i in range(place_idx+1, len(places_to_process)):
                                    if places_to_process[i]["type"] == "element" and i-place_idx-1 < len(place_cards):
                                        places_to_process[i]["element"] = place_cards[i-place_idx-1]
                            
                    except Exception as e:
                        print(f"Error navigating to place {place['name']}: {e}")
                
                # Save combined output with all places
                if all_places_reviews:
                    all_places_filename = f"reviews_output/{timestamp}_all_places_reviews.json"
                    with open(all_places_filename, 'w', encoding='utf-8') as f:
                        json.dump({
                            "timestamp": timestamp,
                            "places": all_places_reviews
                        }, f, ensure_ascii=False, indent=2)
                    
                    print(f"\nProcessed {len(all_places_reviews)} places")
                    print(f"Total reviews collected: {sum(len(place['reviews']) for place in all_places_reviews)}")
                    print(f"All reviews saved to {all_places_filename}")
                    
                    # Offer to convert to Excel
                    if input("Convert reviews to Excel? (y/n): ").lower() == 'y':
                        excel_filename = f"reviews_output/{timestamp}_all_reviews.xlsx"
                        
                        try:
                            # Create a pandas DataFrame for all reviews
                            all_reviews_flat = []
                            for place in all_places_reviews:
                                place_name = place["name"]
                                place_url = place["url"]
                                place_rating = place.get("overall_rating", "")
                                place_total_ratings = place.get("total_ratings", "")
                                
                                for review in place["reviews"]:
                                    all_reviews_flat.append({
                                        "place_name": place_name,
                                        "place_url": place_url,
                                        "place_rating": place_rating,
                                        "place_total_ratings": place_total_ratings,
                                        "reviewer_name": review.get("reviewer_name", ""),
                                        "rating": review.get("rating", ""),
                                        "review_text": review.get("text", ""),
                                        "likes": review.get("likes", "0")
                                    })
                            
                            # Create DataFrame and save to Excel
                            import pandas as pd
                            df = pd.DataFrame(all_reviews_flat)
                            df.to_excel(excel_filename, index=False)
                            
                            print(f"Reviews exported to Excel: {excel_filename}")
                        except Exception as e:
                            print(f"Error exporting to Excel: {e}")
                else:
                    print("No reviews were collected")
                
                print("\nAutomated review scraping completed")
            else:
                print("Invalid option. Please try again.")
    
    except Exception as e:
        print(f"Sandbox error: {e}")
    
    finally:
        # Always close the browser
        if input("Close browser? (y/n): ").lower() != 'n':
            driver.quit()
            print("Browser closed")
        else:
            print("Browser left open. Remember to close it manually.")


# Add this at the end of your file
if __name__ == "__main__":
    sandbox()