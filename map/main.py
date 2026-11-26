import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from map.mcp.server import main_sse, main_stdio


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "sse":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else int(os.environ.get("PORT", 8002))
        host = os.environ.get("HOST", "0.0.0.0")
        main_sse(host=host, port=port)
    else:
        asyncio.run(main_stdio())


if __name__ == "__main__":
    main()
