"""Install the pinned upstream Inno Setup compiler for native CI builds."""

import hashlib
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

URL = "https://github.com/jrsoftware/issrc/releases/download/is-6_4_3/innosetup-6.4.3.exe"
SHA256 = "f3c42116542c4cc57263c5ba6c4feabfc49fe771f2f98a79d2f7628b8762723b"


def main():
    if os.name != "nt":
        raise RuntimeError("The Inno Setup compiler is installed only on Windows")
    with tempfile.TemporaryDirectory(prefix="millionaire-inno-") as directory:
        installer = Path(directory) / "innosetup.exe"
        with urllib.request.urlopen(URL, timeout=60) as response:
            installer.write_bytes(response.read())
        if hashlib.sha256(installer.read_bytes()).hexdigest() != SHA256:
            raise ValueError("Inno Setup download failed its SHA-256 check")
        subprocess.run(
            [str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"],
            check=True,
            timeout=120,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
