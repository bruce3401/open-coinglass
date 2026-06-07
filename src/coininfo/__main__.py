"""Entry point: python -m coininfo"""

import uvicorn
from coininfo.config import load_settings


def main() -> None:
    settings = load_settings()
    uvicorn.run(
        "coininfo.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
