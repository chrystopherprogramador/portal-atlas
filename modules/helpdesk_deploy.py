"""Wrapper para gerenciar-helpdesk.sh (deploy/rollback do Helpdesk)."""
import os
import re
import subprocess

SCRIPT = "/usr/local/sbin/gerenciar-helpdesk.sh"
LOGDIR = "/var/log/atlas-portal/helpdesk"


def _run(args, check=True, timeout=120):
    cmd = ["sudo", "-n", SCRIPT] + list(args)
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} -> rc={p.returncode}\n{p.stdout}\n{p.stderr}")
    return p


def info():
    out = _run(["info"]).stdout
    d = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def list_versions():
    out = _run(["list"], check=False).stdout
    versions = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        item = {}
        for chunk in line.split("|"):
            if "=" in chunk:
                k, v = chunk.split("=", 1)
                item[k.strip()] = v.strip()
        if item.get("STAMP"):
            versions.append(item)
    return versions


def deploy_async(zip_path, tag, jobid):
    """Inicia deploy em background. Retorna imediatamente.
    O script grava log em /var/log/atlas-portal/helpdesk/<jobid>.log e
    .status quando termina."""
    os.makedirs(LOGDIR, exist_ok=True)
    cmd = ["sudo", "-n", SCRIPT, "deploy_log", zip_path, tag or "deploy", jobid]
    subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )
    return jobid


def rollback_async(stamp, jobid):
    os.makedirs(LOGDIR, exist_ok=True)
    cmd = ["sudo", "-n", SCRIPT, "rollback_log", stamp, jobid]
    subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )
    return jobid


def status(jobid, offset=0):
    """Retorna (text, new_offset, done, rc)."""
    if not re.match(r"^[a-zA-Z0-9_-]{4,40}$", jobid):
        raise ValueError("jobid invalido")
    log = os.path.join(LOGDIR, f"{jobid}.log")
    statf = os.path.join(LOGDIR, f"{jobid}.status")
    text = ""
    new_offset = offset
    if os.path.exists(log):
        sz = os.path.getsize(log)
        if offset > sz:
            offset = 0
        with open(log, "rb") as f:
            f.seek(offset)
            chunk = f.read()
        text = chunk.decode("utf-8", errors="replace")
        new_offset = offset + len(chunk)
    rc = None
    done = False
    if os.path.exists(statf):
        try:
            content = open(statf).read().strip()
            if content.isdigit():
                rc = int(content)
                done = True
        except Exception:
            pass
    return text, new_offset, done, rc


def purge(keep):
    return _run(["purge", str(int(keep))]).stdout


def delete_version(stamp):
    return _run(["delete", stamp]).stdout
