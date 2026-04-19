"""
One-time Google OAuth authorization helper.

Run this locally after completing the Google Cloud Console setup (see README Section 8.3).
It opens a browser for the consent flow, saves token.json, then prints the values
you need to copy into Railway environment variables.

Usage:
    python scripts/auth.py
"""
import json
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/calendar']


def main() -> None:
    creds_path = os.path.join(os.path.dirname(__file__), '..', 'credentials.json')
    creds_path = os.path.abspath(creds_path)
    token_path = os.path.join(os.path.dirname(__file__), '..', 'token.json')
    token_path = os.path.abspath(token_path)

    if not os.path.exists(creds_path):
        print('ERROR: credentials.json not found.')
        print('Download it from Google Cloud Console → APIs & Services → Credentials → your OAuth client → Download JSON.')
        print(f'Expected at: {creds_path}')
        sys.exit(1)

    print('Opening browser for Google authorization...')
    flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
    creds = flow.run_local_server(port=0)

    token_data = json.loads(creds.to_json())

    with open(token_path, 'w', encoding='utf-8') as f:
        json.dump(token_data, f, indent=2)

    print('\n\u2705 Authorization successful! token.json saved.\n')
    print('=' * 60)
    print('NEXT STEPS:')
    print('=' * 60)
    print('\n1. Copy the following into Railway → Variables → GOOGLE_TOKEN_JSON:\n')
    print(json.dumps(token_data))
    print('\n2. Copy the contents of credentials.json into Railway → Variables → GOOGLE_CREDENTIALS_JSON:')
    with open(creds_path, encoding='utf-8') as f:
        creds_raw = f.read().strip()
    print(creds_raw)
    print('\n3. DELETE both credentials.json and token.json from your local machine.')
    print('   They are in .gitignore — do NOT commit them.\n')


if __name__ == '__main__':
    main()
