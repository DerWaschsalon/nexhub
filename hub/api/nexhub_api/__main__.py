"""Start im Container: erst migrieren, dann den Webserver auf Port 8000."""
import logging

import uvicorn

from .config import Settings
from .db import migrate


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    migrate(Settings().database_url)
    uvicorn.run("nexhub_api.main:create_app", factory=True, host="0.0.0.0", port=8000,
                proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
