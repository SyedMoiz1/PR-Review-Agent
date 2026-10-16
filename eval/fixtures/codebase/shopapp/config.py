import os

# all secrets come from the environment — never hardcode them
SECRET_KEY = os.environ["SHOPAPP_SECRET_KEY"]
DATABASE_PATH = os.getenv("SHOPAPP_DB", "shop.db")
PAGE_SIZE = 20
HTTP_TIMEOUT_SECONDS = 10
