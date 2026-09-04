"""
SocraticAI - Universal 1-Click Runner
Starts the backend and serves the clean Vanilla HTML/CSS Web UI on http://127.0.0.1:8000
"""
import os
import sys
import webbrowser

# Set UTF-8 encoding for Windows console to prevent charmap errors
os.environ["PYTHONUTF8"] = "1"

# Add backend directory to sys.path and set cwd
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.chdir(BACKEND_DIR)

if __name__ == "__main__":
    import uvicorn

    print("=" * 65)
    print("  SOCRATIC-AI: Multi-Agent RAG Learning Platform")
    print("=" * 65)
    print("[*] Web UI is available at: http://127.0.0.1:8000")
    print("[*] API Documentation at:  http://127.0.0.1:8000/docs")
    print("=" * 65)

    # Open default browser automatically
    try:
        webbrowser.open("http://127.0.0.1:8000")
    except Exception:
        pass

    # Run Uvicorn server
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
