"""WireGuard wrapper."""
import subprocess
import re
from pathlib import Path
import config


def run(cmd, input_=None):
    return subprocess.run(cmd, capture_output=True, text=True, input=input_, timeout=30)


def wg_show():
    r = run(config.WG + ["show", "wg0"])
    return r.stdout


def wg_dump():
    """Retorna lista de peers com transfer/handshake."""
    r = run(config.WG + ["show", "wg0", "dump"])
    lines = r.stdout.strip().splitlines()
    if not lines:
        return {"iface": None, "peers": []}
    iface = lines[0].split("\t")
    peers = []
    for line in lines[1:]:
        p = line.split("\t")
        if len(p) < 8:
            continue
        peers.append({
            "public_key": p[0],
            "endpoint": p[2],
            "allowed_ips": p[3],
            "latest_handshake": int(p[4]) if p[4].isdigit() else 0,
            "rx_bytes": int(p[5]) if p[5].isdigit() else 0,
            "tx_bytes": int(p[6]) if p[6].isdigit() else 0,
        })
    return {"iface": iface, "peers": peers}


def list_peers_from_conf():
    """Le wg0.conf e extrai nomes de peers."""
    peers = []
    try:
        r = run(["sudo", "-n", "cat", "/etc/wireguard/wg0.conf"])
        if r.returncode != 0:
            return []
        current = None
        for line in r.stdout.splitlines():
            line = line.strip()
            m = re.match(r"^# Peer:\s*(\S+)", line)
            if m:
                current = {"name": m.group(1)}
            elif line.startswith("PublicKey") and current:
                current["public_key"] = line.split("=", 1)[1].strip()
            elif line.startswith("AllowedIPs") and current:
                current["ip"] = line.split("=", 1)[1].strip()
                peers.append(current)
                current = None
    except Exception:
        return []
    return peers


def add_peer(name, endpoint=None):
    ep = endpoint or config.VPN_ENDPOINT
    r = run(["sudo", "-n", "/usr/local/sbin/add-peer.sh", name, ep])
    return r


def del_peer(name):
    r = run(["sudo", "-n", "/usr/local/sbin/del-peer.sh", name])
    return r


def read_conf(name):
    p = config.VPN_CLIENTS_DIR / f"{name}.conf"
    try:
        r = run(["sudo", "-n", "cat", str(p)])
        if r.returncode == 0 and r.stdout:
            return r.stdout
    except Exception:
        pass
    p2 = config.VPN_SHARE_DIR / f"{name}.conf"
    try:
        r = run(["sudo", "-n", "cat", str(p2)])
        if r.returncode == 0:
            return r.stdout
    except Exception:
        pass
    return ""
