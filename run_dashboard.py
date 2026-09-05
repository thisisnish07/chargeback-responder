import sys
import os

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from dashboard.server import run_server

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_server(port=port, open_browser=True)
