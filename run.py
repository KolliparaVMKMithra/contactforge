import os

import uvicorn

PORT = int(os.getenv("PORT", "8080"))
HOST = os.getenv("HOST", "0.0.0.0")
RELOAD = os.getenv("RELOAD", "").lower() in {"1", "true", "yes"}

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=RELOAD)
