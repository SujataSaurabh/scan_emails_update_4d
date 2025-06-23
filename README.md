# Email Scanner for 4D Update

This folder contains the email scanning functionality for updating 4D database records.

## Files

- `email_scanner.py` - Main email scanning script that connects to Gmail and counts emails from specific senders with specific subjects
- `.env` - Environment file containing email credentials and configuration

## Setup

1. **Environment Variables**: The `.env` file should contain:
   ```
   EMAIL_PASSWORD_LBL=your_app_password_here
   ```

2. **Gmail App Password**: You need to generate an app password for Gmail:
   - Go to Google Account settings
   - Enable 2-factor authentication
   - Generate an app password for this application
   - Use that password in the `.env` file

## Usage

Run the email scanner:
```bash
python email_scanner.py
```

## Features

- Connects to Gmail using IMAP
- Searches for emails from specific senders
- Counts emails with specific subjects
- Logs all activities to `email_scanner.log`
- Uses secure authentication with app passwords

## Requirements

- Python 3.x
- Required packages (install with `pip install`):
  - `imaplib` (built-in)
  - `email` (built-in)
  - `os` (built-in)
  - `datetime` (built-in)
  - `python-dotenv` (for .env file support)

## Security Notes

- Never commit the `.env` file to version control
- Use app passwords instead of regular passwords
- Keep the `.env` file secure and restrict access 