#!/usr/bin/env python3
"""
wallpaper-pol.py -- Gera/atualiza Registry.pol e GPT.INI da GPO de papel de parede.

Uso:
    wallpaper-pol.py write <gpo_dir> <unc_path> <style>
        gpo_dir   = /var/lib/samba/sysvol/<dominio>/Policies/{GUID}
        unc_path  = \\atlas\Wallpaper$\fundo.jpg
        style     = 0 centralizado, 2 esticado, 6 ajustar, 10 preencher, 22 estender

    wallpaper-pol.py info <gpo_dir>
"""
import sys, os, re, struct
from pathlib import Path

POL_HEADER = b"PReg" + (1).to_bytes(4, "little")  # signature + version=1
REG_SZ = 1


def _utf16z(s: str) -> bytes:
    return s.encode("utf-16-le") + b"\x00\x00"


def _entry(key: str, value: str, vtype: int, data: bytes) -> bytes:
    return (
        b"[\x00"
        + _utf16z(key)
        + b";\x00"
        + _utf16z(value)
        + b";\x00"
        + vtype.to_bytes(4, "little")
        + b";\x00"
        + len(data).to_bytes(4, "little")
        + b";\x00"
        + data
        + b"]\x00"
    )


def _sz_data(s: str) -> bytes:
    return _utf16z(s)


def build_pol(unc: str, style: str) -> bytes:
    body = bytearray()
    # Caminho oficial da policy de wallpaper (User Configuration)
    POLICIES = r"Software\Microsoft\Windows\CurrentVersion\Policies\System"
    body += _entry(POLICIES, "Wallpaper",      REG_SZ, _sz_data(unc))
    body += _entry(POLICIES, "WallpaperStyle", REG_SZ, _sz_data(str(style)))
    body += _entry(POLICIES, "TileWallpaper",  REG_SZ, _sz_data("0"))
    # Tambem grava em Control Panel\Desktop (para refresh imediato)
    DESKTOP = r"Control Panel\Desktop"
    body += _entry(DESKTOP, "Wallpaper",      REG_SZ, _sz_data(unc))
    body += _entry(DESKTOP, "WallpaperStyle", REG_SZ, _sz_data(str(style)))
    body += _entry(DESKTOP, "TileWallpaper",  REG_SZ, _sz_data("0"))
    return POL_HEADER + bytes(body)


def bump_gpt_ini(path: Path, display_name: str = "Atlas - Papel de Parede") -> int:
    """Incrementa a parte 'User' (high 16 bits) do Version em GPT.INI."""
    version = 0
    if path.exists():
        txt = path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"^\s*Version\s*=\s*(\d+)", txt, re.M | re.I)
        if m:
            version = int(m.group(1))
    user_part = (version >> 16) & 0xFFFF
    machine_part = version & 0xFFFF
    user_part = (user_part + 1) & 0xFFFF
    new_version = (user_part << 16) | machine_part

    content = (
        "[General]\r\n"
        f"Version={new_version}\r\n"
        f"displayName={display_name}\r\n"
    )
    path.write_text(content, encoding="utf-8")
    return new_version


def cmd_write(gpo_dir: Path, unc: str, style: str):
    user_dir = gpo_dir / "User"
    user_dir.mkdir(parents=True, exist_ok=True)
    pol = user_dir / "Registry.pol"
    pol.write_bytes(build_pol(unc, style))
    os.chmod(pol, 0o664)

    new_v = bump_gpt_ini(gpo_dir / "GPT.INI")
    print(f"OK pol={pol} version={new_v}")


def cmd_info(gpo_dir: Path):
    pol = gpo_dir / "User" / "Registry.pol"
    gpt = gpo_dir / "GPT.INI"
    print(f"pol_exists={pol.exists()}")
    if pol.exists():
        print(f"pol_size={pol.stat().st_size}")
    if gpt.exists():
        print("gpt=" + gpt.read_text(errors="ignore").replace("\r", "").replace("\n", "|"))


def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    action = sys.argv[1]
    gpo_dir = Path(sys.argv[2])
    if action == "write":
        if len(sys.argv) < 5:
            print(__doc__); sys.exit(2)
        cmd_write(gpo_dir, sys.argv[3], sys.argv[4])
    elif action == "info":
        cmd_info(gpo_dir)
    else:
        print(__doc__); sys.exit(2)


if __name__ == "__main__":
    main()
