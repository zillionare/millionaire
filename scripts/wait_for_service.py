"""Reject a successful installer exit until the installed service is actually healthy."""

import json
import time
import urllib.request


def main():
    """Allow native service launch to finish, including first-run imports."""
    from quantide.config.server_address import local_url

    url = local_url() + "/api/health"
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                payload = json.load(response)
            if payload.get("status") == "ok":
                return
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise RuntimeError("Installed service did not become healthy")


if __name__ == "__main__":
    main()
