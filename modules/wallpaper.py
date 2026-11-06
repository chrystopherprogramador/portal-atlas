"""Wrapper para gerenciar a GPO de papel de parede."""
import subprocess
import shutil
import os
from pathlib import Path
from typing import Dict
import tempfile

SCRIPT = ["sudo", "-n", "/usr/local/sbin/gerenciar-wallpaper.sh"]

STYLES = {
    "0":  "Centralizado",
    "2":  "Esticado",
    "6":  "Ajustar",
    "10": "Preencher",
    "22": "Estender (multi-monitor)",
}


def _run(args, timeout=60):
    return subprocess.run(SCRIPT + args, capture_output=True, text=True, timeout=timeout)


def info() -> Dict[str, str]:
    r = _run(["info"])
    out: Dict[str, str] = {}
    if r.returncode != 0:
        return out
    for line in r.stdout.strip().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def init():
    return _run(["init"], timeout=120)


def set_style(style: str):
    return _run(["set-style", style])


def set_image_from_upload(file_storage) -> "subprocess.CompletedProcess":
    """Recebe um Werkzeug FileStorage. Converte/normaliza para JPG max 1920x1080
    e chama o script com sudo."""
    from PIL import Image  # Pillow ja vem via qrcode[pil]
    import io

    raw = file_storage.read()
    if not raw:
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="arquivo vazio")
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as e:
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=f"imagem invalida: {e}")

    # Limita resolucao para nao estourar trafego SMB
    max_w, max_h = 1920, 1200
    w, h = img.size
    if w > max_w or h > max_h:
        img.thumbnail((max_w, max_h), Image.LANCZOS)

    tmp_dir = Path("/var/tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix="wallpaper_", suffix=".jpg", dir=str(tmp_dir))
    os.close(fd)
    try:
        img.save(tmp_path, "JPEG", quality=88, optimize=True)
        os.chmod(tmp_path, 0o644)
        return _run(["set-image", tmp_path], timeout=120)
    finally:
        try: os.unlink(tmp_path)
        except OSError: pass


def disable():
    return _run(["disable"])
