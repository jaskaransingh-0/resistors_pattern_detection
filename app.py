from fastapi import FastAPI
import threading
import os
import sys
from pathlib import Path

from tcp_server_final import start_tcp_server
from ftp_server import start_ftp_server


app = FastAPI()


# --------------------------------------------------
# Get application folder
# --------------------------------------------------
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent

RECEIVED_FILE = BASE_DIR / "received.txt"


# --------------------------------------------------
# Startup
# --------------------------------------------------
@app.on_event("startup")
def startup():

    threading.Thread(
        target=start_tcp_server,
        daemon=True
    ).start()

    threading.Thread(
        target=start_ftp_server,
        daemon=True
    ).start()


# --------------------------------------------------
# Home
# --------------------------------------------------
@app.get("/")
def home():
    return {
        "status": "Running"
    }


# --------------------------------------------------
# Results
# --------------------------------------------------
@app.get("/results")
def results():

    try:
        with open(RECEIVED_FILE, "r") as f:
            return {
                "data": f.readlines()
            }

    except FileNotFoundError:
        return {
            "data": []
        }


# --------------------------------------------------
# Run directly
# --------------------------------------------------
if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000
    )