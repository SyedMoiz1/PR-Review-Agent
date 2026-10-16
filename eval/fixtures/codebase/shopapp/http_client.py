import json
import time
import urllib.request

from shopapp.config import HTTP_TIMEOUT_SECONDS
from shopapp.logging_utils import get_logger

logger = get_logger("http")


def get_json(url: str, retries: int = 3) -> dict:
    """GET a JSON document with a timeout and exponential-backoff retries.

    Use this for every outbound HTTP call; never call urllib/requests without a timeout.
    """
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_SECONDS) as resp:
                return json.loads(resp.read())
        except OSError as e:
            logger.warning("GET %s failed (attempt %s): %s", url, attempt + 1, e)
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
