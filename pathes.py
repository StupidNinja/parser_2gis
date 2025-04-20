# Common prefix for most XPaths
COMMON_PREFIX = '/html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]'
TITLE_PREFIX = '/html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[1]'


# Base paths with replaceable div index pattern
BASE_REVIEW_STARS_PATH = f'{COMMON_PREFIX}/div[2]/div[{{index}}]/div[1]/div/div[2]/div/div[1]'
BASE_REVIEWER_NAME_PATH = f'{COMMON_PREFIX}/div[2]/div[{{index}}]/div[1]/div/div[1]/div[2]/span/span[1]/span'
BASE_REVIEW_TEXT_PATH = f'{COMMON_PREFIX}/div[2]/div[{{index}}]/div[4]/div[1]/a'
BASE_REVIEW_LIKES_PATH = f'{COMMON_PREFIX}/div[2]/div[{{index}}]/div[4]/div[2]/div/div[1]/button/div[3]'

# /html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]/div[2]/div[4]
# /html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]/div[2]/div[4]


# Regular paths
main_block = '/html/body/div[2]/div/div/div[1]/div[1]/div[3]/div/div/div[2]/div/div/div/div[2]/div[2]/div[1]/div/div/div/div[2]/div'
cookie_banner = '/html/body/div[2]/div/div/div[3]/div[1]/div[3]'
items_count = '/html/body/div[2]/div/div/div[1]/div[1]/div[3]/div/div/div[2]/div/div/div/div[1]/header/div[3]/div/div[1]/div/h2/a/span'
title = f'{TITLE_PREFIX}/h1/span[1]'
phone_btn = '/html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]/div[2]/div[1]/div/div/div[3]/div[2]/div/button'
phone = '/html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]/div[2]/div[1]/div/div/div[3]/div[2]/div/a/bdo'
address = '/html/body/div[2]/div/div/div[1]/div[1]/div[2]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]/div[2]/div[1]/div/div/div[1]/div[2]/div/div[2]/div[1]'
next_page_btn = '/html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[1]/div/div[2]/div/div/div/div[2]/div[2]/div[1]/div/div/div/div[3]/div[2]/div[2]'
reviews_hyperlink = f'{COMMON_PREFIX}/div[1]/div[2]/div/div/div[1]/div[3]/h2/a'
reviews_count = f'{COMMON_PREFIX}/div[1]/div[2]/div/div/div[1]/div[3]/h2/a/span'
#/html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]/div[1]/div[2]/div/div/div[1]/div[3]/h2/a/span path for review count
detail_main_block = '/html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div'
reviews_main_block = '/html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]/div[2]'
reviews_total_rating_count = '/html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]/div[2]/div[2]/div[1]/div[2]'
review_overall_rating = '/html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]/div[2]/div[2]/div[1]/div[1]'


# path for load more button = /html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]/div[2]/div[104]/button
#
#pathes for first in search result
# path for reviews main block = /html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]/div[2]
# path for total rating = /html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]/div[2]/div[2]/div[1]/div[2]
# in total rating there is '*number* оценок' so we need to split it by space and take the first element
# path for overall rating = /html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]/div[2]/div[2]/div[1]/div[1]

#pathes for second in search result
# path for reviews main block = /html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]/div[2]
# path for total rating = /html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]/div[2]/div[2]/div[1]/div[2]
# in total rating there is '*number* оценок' so we need to split it by space and take the first element
# path for overall rating = /html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]/div[2]/div[2]/div[1]/div[1]

# Functions to get dynamic XPaths
def get_review_stars_container(index):
  """Get XPath for review stars at the specified index"""
  return BASE_REVIEW_STARS_PATH.format(index=index)

def get_reviewer_name(index):
  """Get XPath for reviewer name at the specified index"""
  return BASE_REVIEWER_NAME_PATH.format(index=index)
  
def get_review_text(index):
  """Get XPath for review text at the specified index"""
  return BASE_REVIEW_TEXT_PATH.format(index=index)

def get_review_likes(index):
    """Get XPath for review likes counter at the specified index"""
    return BASE_REVIEW_LIKES_PATH.format(index=index)
  
def count_stars_in_container(driver, container):
    """
    Count spans inside a star container to determine rating
    
    Args:
        driver: The WebDriver instance
        container: The star container WebElement
        
    Returns:
        int: The number of stars (spans) found, capped at 5
    """
    try:
        # Simple approach - just count the spans
        spans = container.find_elements(By.TAG_NAME, "span")
        return min(len(spans), 5)  # Cap at 5 stars
    except Exception:
        # Fallback to JavaScript
        return driver.execute_script("""
            const container = arguments[0];
            const spans = container.querySelectorAll('span');
            return Math.min(spans.length, 5);
        """, container)

# og div to count stars
# /html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]/div[2]/div[37]/div[1]/div/div[2]/div/div[1]
# /html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]/div[2]/div[4]/div[1]/div/div[2]/div/div[1]
# /html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]/div[2]/div[5]/div[1]/div/div[2]/div/div[1]
# /html/body/div[2]/div/div/div[1]/div[1]/div[3]/div[2]/div/div/div/div/div[2]/div[2]/div/div[1]/div/div/div/div/div[2]/div[2]/div[803]/div[1]/div/div[2]/div/div[1]