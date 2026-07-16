"""
Desktop App Entry - PyInstaller friendly

Features:
- Auto finds free port (8502-8522)
- Starts Flask in daemon thread
- Tries pywebview (native window) if installed, else opens browser + Tkinter status window
- Works both in dev (python desktop_app.py) and frozen (PyInstaller .exe/.app)

Usage:
    python desktop_app.py
    # or after build:
    ./dist/ProductionPlanReview
"""
import os
import sys
import socket
import threading
import time
import webbrowser
from pathlib import Path

# Ensure project root in sys.path for dev mode
if not getattr(sys, 'frozen', False):
    ROOT = Path(__file__).parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402


def get_free_port(start=8502, end=8522):
    for port in range(start, end + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return start


def wait_for_server(port, timeout=15):
    import http.client
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
            conn.request("GET", "/")
            resp = conn.getresponse()
            if resp.status < 500:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def run_flask(port):
    app = create_app()
    # Use waitress if available (more stable for frozen app), else Flask dev server
    try:
        from waitress import serve
        print(f"[App] Serving with waitress on http://127.0.0.1:{port}")
        serve(app, host="127.0.0.1", port=port, threads=4)
    except ImportError:
        print(f"[App] Serving with Flask dev server on http://127.0.0.1:{port}")
        # threaded and no reloader for frozen
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)


def try_pywebview(port):
    """If pywebview is installed, open native window (true desktop app)."""
    try:
        import webview
        print("[App] pywebview found, opening native window")
        # Flask already running in thread, open webview window
        # webview needs to run on main thread for some platforms
        url = f"http://127.0.0.1:{port}/"
        # Small delay already handled by wait_for_server
        window = webview.create_window(
            "Production Plan Review",
            url,
            width=1280,
            height=860,
            min_size=(1024, 700),
        )
        # Start webview (blocks)
        webview.start()
        return True
    except ImportError:
        print("[App] pywebview not installed, fallback to browser + Tkinter")
        return False
    except Exception as e:
        print(f"[App] pywebview failed: {e}, fallback to browser")
        return False


def run_with_tk(port):
    """Fallback: Tkinter status window + open browser."""
    url = f"http://127.0.0.1:{port}/"
    try:
        # Open browser after short delay
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

        import tkinter as tk
        root = tk.Tk()
        root.title("Production Plan Review")
        root.geometry("420x260")
        # Center window
        root.eval('tk::PlaceWindow . center')

        # Make on top briefly
        root.attributes("-topmost", True)
        root.after(2000, lambda: root.attributes("-topmost", False))

        tk.Label(root, text="📊 Production Plan Review", font=("Arial", 14, "bold")).pack(pady=(20, 10))
        tk.Label(root, text=f"Running at\n{url}", fg="#2563eb", font=("Arial", 11)).pack(pady=5)
        tk.Label(root, text="This window keeps the server alive.\nClose this window to quit.", fg="#64748b", font=("Arial", 9), justify="center").pack(pady=10)

        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=10)

        def open_browser():
            webbrowser.open(url)

        def quit_app():
            print("[App] Quitting...")
            root.destroy()
            # Force exit, since Flask thread is daemon it will die
            os._exit(0)

        tk.Button(btn_frame, text="🌐 Open Browser", command=open_browser, width=14).pack(side="left", padx=5)
        tk.Button(btn_frame, text="❌ Quit", command=quit_app, width=8).pack(side="left", padx=5)

        root.protocol("WM_DELETE_WINDOW", quit_app)
        print(f"[App] Tkinter window started, server at {url}")
        root.mainloop()
        return True
    except Exception as e:
        print(f"[App] Tkinter failed: {e}, fallback to console mode")
        return False


def run_console_mode(port):
    """Last resort: console mode, keep alive."""
    url = f"http://127.0.0.1:{port}/"
    print(f"[App] Running at {url}")
    print("[App] Press Ctrl+C to quit")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[App] Shutting down...")


def main():
    # Fix for macOS .app bundle: change cwd to writable location if needed
    if getattr(sys, 'frozen', False):
        # When frozen, cwd may be inside bundle, ensure we don't rely on it
        try:
            os.chdir(os.path.expanduser("~"))
        except Exception:
            pass

    port = int(os.environ.get("PORT", get_free_port()))
    print(f"[App] Starting Production Plan Review on port {port}")
    print(f"[App] Frozen={getattr(sys, 'frozen', False)} Base={getattr(sys, '_MEIPASS', 'N/A')}")

    # Start Flask in daemon thread
    server_thread = threading.Thread(target=run_flask, args=(port,), daemon=True, name="FlaskServer")
    server_thread.start()

    # Wait for server ready
    if not wait_for_server(port, timeout=15):
        print("[App] ERROR: Server failed to start within 15s")
        # Still try to continue

    print(f"[App] Server ready at http://127.0.0.1:{port}/")

    # Try native window first, then Tk, then console
    if not try_pywebview(port):
        if not run_with_tk(port):
            run_console_mode(port)


if __name__ == "__main__":
    main()
