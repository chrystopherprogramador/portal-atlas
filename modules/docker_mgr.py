"""Wrapper para CLI do Docker."""
import json
import subprocess

DOCKER = "/usr/bin/docker"


def _run(args, timeout=30, check=False):
    cmd = ["sudo", "-n", DOCKER] + list(args)
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)} -> {p.returncode}\n{p.stderr}")
    return p


def _json_lines(out):
    items = []
    for line in (out or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except Exception:
            pass
    return items


# =============== CONTAINERS ===============
def list_containers(all=True):
    p = _run(["ps", "-a" if all else "", "--format", "{{json .}}"])
    return _json_lines(p.stdout)


def container_action(cid, action):
    """action: start|stop|restart|pause|unpause|kill|rm"""
    if action not in ("start", "stop", "restart", "pause", "unpause", "kill", "rm"):
        raise ValueError("acao invalida")
    args = [action]
    if action == "rm":
        args = ["rm", "-f"]
    args.append(cid)
    p = _run(args, timeout=60)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def container_logs(cid, tail=200):
    p = _run(["logs", "--tail", str(int(tail)), "--timestamps", cid], timeout=20)
    return p.stdout + p.stderr


def container_inspect(cid):
    p = _run(["inspect", cid], timeout=10)
    try:
        data = json.loads(p.stdout)
        return data[0] if data else None
    except Exception:
        return None


def container_stats():
    """Snapshot de uso (CPU/mem) — --no-stream para ser rapido."""
    p = _run(["stats", "--no-stream", "--format", "{{json .}}"], timeout=15)
    return _json_lines(p.stdout)


# =============== IMAGES ===============
def list_images():
    p = _run(["images", "--format", "{{json .}}"])
    return _json_lines(p.stdout)


def pull_image(image):
    p = _run(["pull", image], timeout=600)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def remove_image(iid, force=False):
    args = ["rmi"]
    if force:
        args.append("-f")
    args.append(iid)
    p = _run(args, timeout=60)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


# =============== VOLUMES ===============
def list_volumes():
    p = _run(["volume", "ls", "--format", "{{json .}}"])
    return _json_lines(p.stdout)


def remove_volume(name):
    p = _run(["volume", "rm", name], timeout=30)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


# =============== NETWORKS ===============
def list_networks():
    p = _run(["network", "ls", "--format", "{{json .}}"])
    return _json_lines(p.stdout)


def remove_network(name):
    p = _run(["network", "rm", name], timeout=30)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


# =============== SYSTEM ===============
def system_info():
    p = _run(["version", "--format", "{{json .}}"], timeout=10)
    ver = {}
    try:
        ver = json.loads(p.stdout)
    except Exception:
        pass
    p2 = _run(["system", "df", "--format", "{{json .}}"], timeout=15)
    df = _json_lines(p2.stdout)
    return {"version": ver, "df": df}


def system_prune(volumes=False):
    args = ["system", "prune", "-a", "-f"]
    if volumes:
        args.append("--volumes")
    p = _run(args, timeout=120)
    return p.returncode == 0, (p.stdout + p.stderr).strip()
