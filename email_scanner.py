import datetime
from datetime import datetime
import imaplib
import email
from email.header import decode_header
import os
from dotenv import load_dotenv
import requests
from requests.exceptions import RequestException
import logging
import json

# Configure logging
logging.basicConfig(
    filename='email_scanner.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

'''
The script reads the emails from the LBL email account and prints the subject and date of the emails.

This is written to be used with the LBL email account. Reads the emails from alsuser@lbl.gov with subject -" -- " and extract 
alsid and User Name from the email body.
Once the alsid and User Name is extracted, the script will read the User Name from the api provided from 4D and
match it with the User Name in the email.
If the User Name is found and same in the email, the script will insert the alsid into the database.
If the alsid is not found, the script will log the email body and the alsid and User Name.

'''
def decode_email_subject(subject):
    """Decode email subject from bytes to string."""
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
    """Extract badge number from email body."""
    try:
        # Get email body
        if email_message.is_multipart():
            for part in email_message.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode()
                    break
        else:
            body = email_message.get_payload(decode=True).decode()

        # Look for badge number in the body
        # Assuming the badge number follows a pattern like "Badge Number: XXXXXX"
        for line in body.splitlines():
            if "Badge Number is " in line:
                # try to extract the badge number from Berkeley Lab Id#
                print(f"Processing line: {line}")
                # badge_number = line.split(":")[-1].strip()
                # If badge number is not found, try to extract it from the line
                badge_number = line.split(" ")[-1].strip()
                badge_number = badge_number.replace("*", "").replace(" ", "")
                
                logging.info(f"Found badge number: {badge_number}")
                return badge_number

            elif  "Berkeley Lab ID#:" in line:
                print(f"Processing line: {line}")
                # Extract the badge number from the line
                badge_number = line.split(":")[-1].strip()
                badge_number = badge_number.replace("*", "").replace(" ", "")
                logging.info(f"Found Berkeley Lab Id#: {badge_number}")
                return badge_number
        logging.warning("No badge number found in email body")
        return None

    except Exception as e:
        logging.error(f"Error extracting badge number: {str(e)}")
        return None


def scan_emails():
    # Load environment variables
    load_dotenv()
    
    # Email credentials
    email_user = "sujatagoswami@lbl.gov"
    email_password = os.getenv('EMAIL_PASSWORD_LBL')  # Store your password in .env file
    
    # Connect to the IMAP server
    imap_server = "imap.gmail.com"  # Updated to Google's IMAP server
    mail = imaplib.IMAP4_SSL(imap_server)
    
    try:
        logging.info("Connecting to IMAP server...")
        # Login to the email account
        mail.login(email_user, email_password)
        logging.info("Successfully logged in to the email account.")
        
        # Select the inbox
        mail.select('INBOX')
        logging.info("Selected the inbox.")
        # Search for emails from specific sender with specific subject
        search_criteria = '(FROM "alsuser@lbl.gov" SUBJECT "ALS User Site Access")'
        _, message_numbers = mail.search(None, search_criteria)
        
        # Get the count of matching emails
        email_count = len(message_numbers[0].split())
        logging.info(f"Found {email_count} emails matching the criteria.")
        
        # Process each email
        for num in message_numbers[0].split():
            _, msg_data = mail.fetch(num, '(RFC822)')
            email_body = msg_data[0][1]
            email_message = email.message_from_bytes(email_body)
            
            # Get email details
            subject = decode_email_subject(email_message['subject'])
            date = email_message['date']
            # convert the date to a datetime object. Remove time information, keep only date
            date = datetime.strptime(date, "%a, %d %b %Y %H:%M:%S %z")
            date = date.date()
            
            # Extract name from subject
            user_name = extract_name_from_subject(subject)

            # Extract badge number from body
            badge_number = extract_badge_number(email_message)

             # Extract recipient email
            recipient_email = extract_recipient_email(email_message)
            if recipient_email:
               person_data=  fetch_person_details_from_api(recipient_email)
            
            if person_data['LBNLID'] == badge_number:
                logging.info(f"Badge number {badge_number} matches for recipient email: {recipient_email}")
            # validate the identity of the user
            elif person_data['LBNLID'] != badge_number:
                if person_data['OrgEmail'] == recipient_email and person_data['FirstName'] == user_name.split()[0] and person_data['LastName'] == user_name.split()[-1]:
                    lbnlid  = badge_number
                    alsid = person_data['alsid']
                    # Insert the ALS ID and LBNL ID into the database
                    success = insert_lbnlid_into_db_(alsid, lbnlid, date)
                    if success:
                        logging.info(f"Successfully inserted ALS ID {alsid} and LBNL ID {lbnlid}  for {person_data['FirstName']} {person_data['LastName']}into the database.")
                    else:
                        logging.error(f"Failed to insert ALS ID {alsid} and LBNL ID {lbnlid} into the database.")
            else:
                logging.warning(f"Identity mismatch for email: {recipient_email}. Expected: {user_name}, Found: {person_data.get('FirstName', '')} {person_data.get('LastName', '')}")
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
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        print(f"An error occurred: {str(e)}")
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
    """Extract recipient's email address from the forwarded message 'To:' field."""
    try:
        # Get email body
        if email_message.is_multipart():
            for part in email_message.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode()
                    break
        else:
            body = email_message.get_payload(decode=True).decode()

        # Look for "To:" in the forwarded message section
        for line in body.splitlines():
            if line.strip().startswith("To:"):
                print(f"Processing To line: {line}")
                # Extract email from the To: line
                email = line.split("To:")[-1].strip()
                # If the format is "Name <email@domain.com>", extract just the email
                if '<' in email and '>' in email:
                    email = email[email.find('<')+1:email.find('>')]
                logging.info(f"Found recipient email in forwarded message: {email}")
                return email
        
        logging.warning("No recipient email found in forwarded message")
        return None

    except Exception as e:
        logging.error(f"Error extracting recipient email: {str(e)}")
        return None


def fetch_person_details_from_api(email):
    """
    Fetch person details from the ALS API using the email address.
    Returns a dictionary with person details or None if the request fails.
    """
    try:
        # Construct API URL
        api_url = f"https://alsusweb3.lbl.gov/ALSGetPerson/?em={email}"
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
            
    except RequestException as e:
        logging.error(f"Error making API request: {str(e)}")
        return None
    except ValueError as e:  # JSON parsing error
        logging.error(f"Error parsing API response: {str(e)}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error fetching person details: {str(e)}")
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
        # API endpoint
        api_url = "https://alsusweb3.lbl.gov/UPDLbnlid"
        
        # Prepare the request data
        data = {"alsid": str(alsid), "lbnlid": str(lbnlid), "date": str(date)}
        
        
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

if __name__ == "__main__":
    logging.info("Starting email scanner...")
    count = scan_emails()
    # logging.info(f"Total count of matching emails: {count}")
    # print(f"\nTotal count of matching emails: {count}")
    
    