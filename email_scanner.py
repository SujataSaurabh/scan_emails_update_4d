import datetime
from datetime import datetime, timedelta
import re
import imaplib
import email
from email.header import decode_header
import os
from dotenv import load_dotenv
import requests
from requests.exceptions import RequestException
from email.utils import parsedate_to_datetime
import logging
import json 
import traceback

# load environment variables from .env file
load_dotenv()
# Configure logging
       
# Get the log directory from the environment variable
# get LOG_DIR from environment variable 

LOG_DIR = os.getenv('LOG_DIR')
LOG_FILE = os.path.join(LOG_DIR, 'scanner.log')

# Configure logging to write to the file
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logging.info("Logs are being written to the file.")
# logging.basicConfig(
#     filename='email_scanner.log',
#     level=logging.INFO,
#     format='%(asctime)s - %(levelname)s - %(message)s'
# )

'''
The script reads the emails from the LBL email account and prints the subject and date of the emails.

This is written to be used with the LBL email account. Reads the emails from alsuser@lbl.gov with subject -" -- " and extract 
alsid and User Name from the email body.
Once the alsid and User Name is extracted, the script will read the User Name from the api provided from 4D and
match it with the User Name in the email.
If the User Name is found and same in the email, the script will insert the alsid into the database.
If the alsid is not found, the script will log the email body and the alsid and User Name.

'''

# decode email subject from bytes to string
# This function decodes the email subject from bytes to a string, handling different encodings.
def decode_email_subject(subject):
    """Decode email subject from bytes to string."""
    if subject is None:
        logging.warning("Email subject is missing")
        return ""
    decoded_parts = []
    for part, encoding in decode_header(subject):
        if isinstance(part, bytes):
            if encoding:
                decoded_parts.append(part.decode(encoding))
            else:
                decoded_parts.append(part.decode('utf-8', errors='replace'))
        else:
            decoded_parts.append(part)
    return ''.join(decoded_parts)

#  extract user name from the email subject
def extract_name_from_subject(subject):
    """Extract first and last name from email subject."""
    try:
        # Remove any extra whitespace and split by "-"
        parts = subject.strip().split("-")
        if len(parts) >= 2:
            # Get the part after "ALS User Site Access -"
            name_part = parts[1].strip()
            logging.info(f"Extracted name from subject: {name_part}")
            return name_part
        return None
    except Exception as e:
        logging.error(f"Error extracting name from subject: {str(e)}")
        return None
# 
def extract_badge_number(email_message):
    """Extract badge number (LBNL ID) from email body."""
    try:
        print("Extracting badge number from email body...")
        
        # Extract the email body as a string
        body = ""
        if email_message.is_multipart():
            for part in email_message.walk():
                # if part.get_content_type() == "text/plain" or part.get_content_type() == "text/html" or part.get_content_type() == "text/xml":
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(errors='replace')
                    break
        else:
            payload = email_message.get_payload(decode=True)
            if payload:
                body = payload.decode(errors='replace')
        
        if not body:
            logging.warning("Email body is empty")
            return None
        
        # Define the target phrase to search for
        search_phrase = "Your Berkeley Lab Identification Number/Badge Number is"
        
        # Split the entire email body into a list of individual lines
        lines = body.splitlines()
        print(f"Total lines in email body: {len(lines)}")
        
        print("Searching for the badge number line...")
        for line in lines:
            # Check if the search phrase is present in the current line
            if search_phrase in line:
                print(f"✅ Found Line: {line.strip()}")
                # Extract the badge number using regex
                badge_number_match = re.search(r'(\d{5,})', line)
                if badge_number_match:
                    badge_number = badge_number_match.group(1)
                    print(f"Extracted Badge Number: {badge_number}")
                    logging.info(f"Found badge number: {badge_number}")
                    return badge_number
                break  # Stop searching after the first match
        
        print("❌ Badge number line not found in the email body.")
        logging.warning("No badge number found in email body")
        return None
        
    except Exception as e:
        logging.error(f"Error extracting badge number: {str(e)}")
        return None

     

def scan_emails():
    # Load environment variables
    load_dotenv()
    
    # Email credentials- fetch from environment variables
    email_user = os.getenv('EMAIL_USER')
    email_password = os.getenv('EMAIL_PASSWORD')  
    if not email_user or not email_password:
        logging.error("EMAIL_USER or EMAIL_PASSWORD is missing; check your container env vars.")
        return 0
    
    # Connect to the IMAP server
    imap_server = "imap.gmail.com"  # Updated to Google's IMAP server
    mail = imaplib.IMAP4_SSL(imap_server)
    
    try:
        logging.info("Connecting to IMAP server...")
        # Login to the email account
        mail.login(email_user, email_password)
        logging.info("Successfully logged in to the email account.")
        
        # Build "today only" IMAP date window
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)

        imap_today = today.strftime("%d-%b-%Y")      # e.g. 29-Jan-2026
        imap_tomorrow = tomorrow.strftime("%d-%b-%Y")

        # Select the inbox
        mail.select('INBOX')
        logging.info("Selected the inbox.")
        # Search for emails from specific sender with specific subject
        # search_criteria = '(FROM "do-not-reply-hrsc@hsc.lbl.gov" SUBJECT "ALS User Site Access - ")'
        # Unread + today + sender + subject filter
        search_criteria = (
            f'(UNSEEN '
            f'FROM "do-not-reply-hrsc@hsc.lbl.gov" '
            f'SUBJECT "ALS User Site Access - " '
            f'SINCE "{imap_today}" '
            f'BEFORE "{imap_tomorrow}")'
        )
        status, message_numbers = mail.search(None, search_criteria)
         
        if status != "OK":
            logging.error(f"IMAP search failed: {status}")
            return 0
        
        # Get the count of matching emails
        email_ids = message_numbers[0].split()
        email_count = len(email_ids)
        logging.info(f"Found {email_count} UNSEEN emails for today matching the criteria.")

        
        # Process each email
        # for num in message_numbers[0].split():
        #     _, msg_data = mail.fetch(num, '(RFC822)')
        for num in email_ids:
            status, msg_data = mail.fetch(num, '(RFC822)')
            if status != "OK" or not msg_data or not msg_data[0]:
                logging.warning(f"Failed to fetch message {num}")
                continue
            email_body = msg_data[0][1]
            email_message = email.message_from_bytes(email_body)
            # print("email_message = ", email_message)
            # Get email details
            subject_raw = email_message.get('subject') or ""
            subject = decode_email_subject(subject_raw)
            date = email_message.get('date') or ""
            
            # Check if date is None
            if not date:
                logging.warning(f"Email has no date header; skipping")
                continue
            
            email_date = re.sub(r'\s*\([^)]+\)$', '', date)  
           
            # If the date is in string format, convert it to a date object
            if isinstance(email_date, str):           
                # If the date is a string, parse it to a datetime object
                try:
                    email_date = datetime.strptime(email_date, "%a, %d %b %Y %H:%M:%S %z")
                    # Convert to date object
                    email_date = email_date.date()  # Remove time information, keep only date
                except ValueError as e:
                    logging.error(f"Failed to parse email date '{email_date}': {e}")
                    continue
            # get todays
            # today = datetime.today().date()
            # print("today", today)
            print("date", email_date)
            # break 
            # Extract name from subject
            user_name = extract_name_from_subject(subject)

            # Extract badge number from body
            badge_number = extract_badge_number(email_message)
            print(f"badge_number: {badge_number}")

             # Extract recipient email
            recipient_email = extract_recipient_email(email_message)
            print(f"recipient_email: {recipient_email}")
            person_data = {}
            if recipient_email:
               person_data=  fetch_person_details_from_api(recipient_email)

            datelastwelcomeletter = person_data.get("datelastwelcomeletter")
            if not datelastwelcomeletter:
                datelastwelcomeletter = "1960-01-01" # Set to minimum date if not found

            print(f"setting the datelastbnlidupdate: {datelastwelcomeletter}")
            # Check if the date received is same as found in the database
            if datetime.strptime(datelastwelcomeletter, "%Y-%m-%d").date() == email_date:
                print(f"Skipping email for {user_name} as the {datelastwelcomeletter} is same as mail date: {email_date}")
                logging.info(f"ALS ID {person_data['alsid']} already has LBNL ID {person_data['LBNLID']} for {person_data['FirstName']} {person_data['LastName']} on {date}")
                continue
            elif person_data['OrgEmail'] == recipient_email and person_data['FirstName'] == user_name.split()[0] and person_data['LastName'] == user_name.split()[-1]:
                lbnlid  = badge_number
                alsid = person_data['alsid']
                # Insert the ALS ID and LBNL ID into the database
                success = insert_lbnlid_into_db_(alsid, lbnlid, email_date)
                # success = True
                print(f"Inserting ALS ID {alsid} and LBNL ID {lbnlid} into the database for {person_data['FirstName']} {person_data['LastName']}. Test completed")
                if success:
                    mail.store(num, '+FLAGS', '\\Seen')  # Mark email as read
                    logging.info(f"Successfully inserted ALS ID {alsid} and LBNL ID {lbnlid}  for {person_data['FirstName']} {person_data['LastName']}into the database.")
                else:
                    logging.error(f"Failed to insert ALS ID {alsid} and LBNL ID {lbnlid} into the database.")
            # else:
            #     logging.warning(f"Identity mismatch for email: {recipient_email}. Expected: {user_name}, Found: {person_data.get('FirstName', '')} {person_data.get('LastName', '')}")
            # Log the email details
            logging.info(f"Processing email from {email_user} with subject: {subject}")
        
            # 
            logging.info(f"Email Details - Date: {date}, Subject: {subject}")
            print(f"\nEmail Details:")
            print(f"Date: {date}")
            print(f"Subject: {subject}")
            if user_name:
                print(f"User Name: {user_name}")
            if badge_number:
                print(f"Badge Number: {badge_number}")
            if recipient_email:
                print(f"Recipient Email: {recipient_email}")
            if person_data:
                print(f"Person Data: {person_data}")
            else:
                print("No person data found for the recipient email.")
            print("-" * 50)
        
        return email_count
    except Exception:
        logging.exception("An error occurred")
        traceback.print_exc()
        return 0
        
    finally:
        # Close the connection
        try:
            mail.close()
            mail.logout()
            logging.info("Closed the connection to the IMAP server.")
        except Exception as e:
            logging.warning(f"Failed to close the connection: {str(e)}")

def extract_recipient_email(email_message):
    """Extract recipient's email address from the email 'To:' header field."""
    try:
        # Get the 'To:' header directly from the email message
        to_header = email_message.get('To')
        
        if not to_header:
            logging.warning("No 'To:' header found in email")
            return None
        
        to_header = to_header.strip()
        logging.info(f"Raw To header: {to_header}")
        
        # Extract email from formats like:
        # - "email@domain.com"
        # - "Name <email@domain.com>"
        # - "email1@domain.com, email2@domain.com" (take first)
        
        # If in form "Name <email@domain>", extract between <>
        if '<' in to_header and '>' in to_header:
            addr = to_header[to_header.find('<')+1:to_header.find('>')].strip()
            logging.info(f"Found recipient email from To header: {addr}")
            return addr
        
        # Otherwise extract first email address
        email_match = re.search(r'([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})', to_header)
        if email_match:
            addr = email_match.group(1)
            logging.info(f"Found recipient email from To header: {addr}")
            return addr
        
        logging.warning("Could not extract email from 'To:' header")
        return None

    except Exception as e:
        logging.error(f"Error extracting recipient email: {str(e)}")
        return None


def fetch_person_details_from_api(email):
    """
    Fetch person details from the ALS API using the email address.
    Returns a dictionary with person details or None if the request fails.
    """
        # Construct API URL
        # fetch api_url from environment variable

    if not email:
        logging.error("Email is empty. Cannot fetch person details.")
        return None
    api_url = os.getenv('prod_get_person') + f"{email}"
    if not api_url:
        logging.error("API URL is not set in environment variables.")
        return None
    print(f"Fetching person details from API: {api_url}")
    logging.info(f"Fetching person details from API: {api_url}")
    
    # Make GET request to API
    response = requests.get(api_url, timeout=10)  # 10 second timeout
    
    # Check if request was successful
    if response.status_code == 200:
        person_data = response.json()  # Parse JSON response
        logging.info(f"Successfully retrieved person details for email: {email}")
        return person_data
    else:
        logging.error(f"API request failed with status code: {response.status_code}")
        return None
        
# 
def insert_lbnlid_into_db_(alsid, lbnlid, date):
    """
    Insert the ALS ID and LBNL ID mapping using the ALS API.
    
    Args:
        alsid (str): ALS ID of the user
        lbnlid (str): LBNL ID (badge number) of the user
        date (str): Date of the email
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # get API endpoint
        api_url = os.getenv('prod_update_lbnlid')        
        if not api_url:
            logging.error("API URL is not set in environment variables.")
            return False
        # get security token from environment variable
        security_token = os.getenv('4D_SECURITY_TOKEN')
        if not security_token:
            logging.error("4D Security Token is not set in environment variables.")
            return False
        # Prepare the request data
        data = {"alsid": str(alsid), "lbnlid": str(lbnlid), "date": str(date), "securitytoken": str(security_token)}
        logging.info(f"Preparing to insert ALS ID {alsid} and LBNL ID {lbnlid} into the database.")
        # Set up headers for JSON request
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        # Log the request details
        logging.info(f"Sending POST request to {api_url}")
        logging.info(f"Request data: {data}")
        
        # Make the POST request
        response = requests.post(
            api_url,
            json=data,
            headers=headers,
            timeout=10  # 10 second timeout
        )
        
        # Check response status
        if response.status_code == 200:
            logging.info(f"Successfully updated LBNL ID for ALS ID {alsid}")
            logging.info(f"Response: {response.text}")
            return True
        else:
            logging.error(f"API request failed with status code: {response.status_code}")
            logging.error(f"Response: {response.text}")
            return False
            
    except RequestException as e:
        logging.error(f"Network error while making API request: {str(e)}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error in insert_lbnlid_into_db: {str(e)}")
        return False

def test_insert_lbnlid_into_db():
    """
    Test function to insert dummy data into the database.
    """
    alsid = "123456"
    lbnlid = "654321"
    success = insert_lbnlid_into_db_(alsid, lbnlid)
    if success:
        print(f"Successfully inserted ALS ID {alsid} and LBNL ID {lbnlid} into the database.")
    else:
        print(f"Failed to insert ALS ID {alsid} and LBNL ID {lbnlid} into the database.")

def send_notification_email(subject, body, to_email, from_email, smtp_server="smtp.lbl.gov"):
    import smtplib
    from email.mime.text import MIMEText
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    try:
        with smtplib.SMTP(smtp_server) as server:
            server.send_message(msg)
        logging.info(f"Notification email sent to {to_email}")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")

if __name__ == "__main__":
    logging.info("Starting email scanner...")
    count = scan_emails()
    logging.info(f"Total count of matching emails: {count}")
    # print(f"\nTotal count of matching emails: {count}")
    # person_data = fetch_person_details_from_api('thomas.blank@ubc.ca')
    # print(person_data["datelastbnlidupdate"])
    # print(datetime.strptime(person_data["datelastbnlidupdate"], "%Y-%m-%d").date(),  datetime.today().date())
