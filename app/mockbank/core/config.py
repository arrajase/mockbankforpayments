import os

from dotenv import load_dotenv

load_dotenv()

BANK_API_KEY = os.getenv("BANK_API_KEY", "changeme")
WEBHOOK_SIGNING_SECRET = os.getenv("WEBHOOK_SIGNING_SECRET", "changeme")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mockbank.db")
