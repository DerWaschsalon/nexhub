"""Start im Container: erst migrieren, dann den Webserver auf Port 8000."""
import logging

import uvicorn

from . import logs
from .config import Settings
from .db import migrate


def main() -> None:
    logs.setup()
    migrate(Settings().database_url)
    config = uvicorn.Config("nexhub_api.main:create_app", factory=True, host="0.0.0.0", port=8000,
                            proxy_headers=True, forwarded_allow_ips="*")
    # uvicorn richtet sein Logging in Config() ein; der Filter muss danach dazukommen
    logging.getLogger("uvicorn.access").addFilter(logs.HideSecretQuery())
    uvicorn.Server(config).run()


if __name__ == "__main__":
    main()
