import requests
import os
import dotenv

# Load environment variables
dotenv.load_dotenv()

# Configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def get_updates():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    response = requests.get(url)
    data = response.json()
    return data

if __name__ == "__main__":
    updates = get_updates()
    print(updates)