"""
Catalogo + parser/writer de politicas Registry.pol estilo GPMC.

Cada politica tem: id, scope (user/machine), title, description, hive, key, value,
type (REG_DWORD/REG_SZ), e um dict com as opcoes (label -> dado).
"""
from __future__ import annotations
import struct
import os
from pathlib import Path
from typing import List, Dict, Optional

# ----- formato PReg (Registry.pol) ----------------------------------------
PREG_HEADER = b"PReg\x01\x00\x00\x00"

REG_NONE      = 0
REG_SZ        = 1
REG_EXPAND_SZ = 2
REG_BINARY    = 3
REG_DWORD     = 4
REG_QWORD     = 11

TYPE_NAMES = {1:"REG_SZ", 2:"REG_EXPAND_SZ", 3:"REG_BINARY", 4:"REG_DWORD", 11:"REG_QWORD"}


def _utf16(s: str) -> bytes:
    return s.encode("utf-16-le") + b"\x00\x00"


def _enc_value(value, vtype: int) -> bytes:
    if vtype == REG_DWORD:
        return struct.pack("<I", int(value))
    if vtype == REG_QWORD:
        return struct.pack("<Q", int(value))
    if vtype in (REG_SZ, REG_EXPAND_SZ):
        return _utf16(str(value))
    if vtype == REG_BINARY:
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        return bytes.fromhex(str(value))
    return b""


def _entry_bytes(key: str, name: str, vtype: int, data: bytes) -> bytes:
    SEMI = ";".encode("utf-16-le")  # b";\x00"
    LBR  = "[".encode("utf-16-le")
    RBR  = "]".encode("utf-16-le")
    out  = LBR
    out += _utf16(key) + SEMI
    out += _utf16(name) + SEMI
    out += struct.pack("<I", vtype) + SEMI
    out += struct.pack("<I", len(data)) + SEMI
    out += data
    out += RBR
    return out


def write_pol(entries: List[Dict], path: Path):
    """entries = list of {key, name, type, data}."""
    buf = PREG_HEADER
    for e in entries:
        d = _enc_value(e["data"], int(e["type"]))
        buf += _entry_bytes(e["key"], e["name"], int(e["type"]), d)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf)


def parse_pol(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    data = path.read_bytes()
    if len(data) < 8 or data[:8] != PREG_HEADER:
        return []
    out = []
    i = 8
    n = len(data)
    while i < n:
        if data[i:i+2] != b"[\x00":
            i += 2; continue
        i += 2
        # key (utf-16le, terminado em \x00\x00) seguido de ;
        def read_str():
            nonlocal i
            start = i
            while i + 1 < n:
                if data[i] == 0 and data[i+1] == 0:
                    s = data[start:i].decode("utf-16-le", errors="replace")
                    i += 2  # null
                    # separador ';' em utf-16: ';\x00'
                    if data[i:i+2] == b";\x00":
                        i += 2
                    return s
                i += 2
            return ""
        key = read_str()
        name = read_str()
        # tipo (4 bytes) + ; (utf16)
        vtype = struct.unpack("<I", data[i:i+4])[0]; i += 4
        if data[i:i+2] == b";\x00": i += 2
        size = struct.unpack("<I", data[i:i+4])[0]; i += 4
        if data[i:i+2] == b";\x00": i += 2
        raw = data[i:i+size]; i += size
        if data[i:i+2] == b"]\x00": i += 2

        # decodifica valor
        if vtype == REG_DWORD and len(raw) >= 4:
            val = struct.unpack("<I", raw[:4])[0]
        elif vtype == REG_QWORD and len(raw) >= 8:
            val = struct.unpack("<Q", raw[:8])[0]
        elif vtype in (REG_SZ, REG_EXPAND_SZ):
            s = raw.decode("utf-16-le", errors="replace")
            val = s.rstrip("\x00")
        elif vtype == REG_BINARY:
            val = raw.hex()
        else:
            val = raw.hex()

        out.append({"key": key, "name": name, "type": vtype, "data": val})
    return out


# ----- catalogo de politicas ----------------------------------------------
# Cada item: id, scope, title, desc, key, value, type, options (label->data).
# options vazias = checkbox (1=ativar, ausente=remover).

CATALOG: List[Dict] = [
    # ------------------ User Configuration ------------------
    {
        "id": "user.no_run", "scope": "user",
        "title": "Remover comando 'Executar...' do menu Iniciar",
        "desc":  "Esconde o item 'Executar' do menu iniciar do usuario.",
        "key":   "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer",
        "value": "NoRun", "type": REG_DWORD,
        "options": {"Habilitado (esconder)": 1},
    },
    {
        "id": "user.no_cmd", "scope": "user",
        "title": "Bloquear acesso ao Prompt de Comando",
        "desc":  "Impede o usuario de abrir cmd.exe.",
        "key":   "Software\\Policies\\Microsoft\\Windows\\System",
        "value": "DisableCMD", "type": REG_DWORD,
        "options": {"Bloquear inclusive scripts (.bat)": 1, "Bloquear so o prompt": 2},
    },
    {
        "id": "user.no_regedit", "scope": "user",
        "title": "Bloquear o Editor do Registro (regedit)",
        "key":   "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System",
        "value": "DisableRegistryTools", "type": REG_DWORD,
        "options": {"Habilitado": 1},
    },
    {
        "id": "user.no_taskmgr", "scope": "user",
        "title": "Bloquear o Gerenciador de Tarefas",
        "key":   "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System",
        "value": "DisableTaskMgr", "type": REG_DWORD,
        "options": {"Habilitado": 1},
    },
    {
        "id": "user.no_controlpanel", "scope": "user",
        "title": "Esconder Painel de Controle",
        "key":   "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer",
        "value": "NoControlPanel", "type": REG_DWORD,
        "options": {"Habilitado": 1},
    },
    {
        "id": "user.hide_drives", "scope": "user",
        "title": "Esconder unidades no Computador (Explorer)",
        "desc":  "Mascara letras de drive na visualizacao do Explorer (mas nao impede acesso por path).",
        "key":   "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer",
        "value": "NoDrives", "type": REG_DWORD,
        "options": {
            "Esconder A,B,C,D":     0x0F,
            "Esconder so C":         0x04,
            "Esconder todas":        0x03FFFFFF,
        },
    },
    {
        "id": "user.disable_lockscreen_change", "scope": "user",
        "title": "Impedir alteracao do papel de parede",
        "key":   "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\ActiveDesktop",
        "value": "NoChangingWallPaper", "type": REG_DWORD,
        "options": {"Habilitado": 1},
    },
    {
        "id": "user.screensaver_timeout", "scope": "user",
        "title": "Timeout de protetor de tela (segundos)",
        "desc":  "Forca um tempo maximo (em segundos) para ativar o screensaver.",
        "key":   "Control Panel\\Desktop",
        "value": "ScreenSaveTimeOut", "type": REG_SZ,
        "options": {"5 minutos": "300", "10 minutos": "600", "15 minutos": "900", "30 minutos": "1800"},
    },
    {
        "id": "user.screensaver_secure", "scope": "user",
        "title": "Exigir senha ao sair do protetor de tela",
        "key":   "Control Panel\\Desktop",
        "value": "ScreenSaverIsSecure", "type": REG_SZ,
        "options": {"Habilitado": "1"},
    },

    # ------------------ Computer Configuration --------------
    {
        "id": "comp.disable_usb_storage", "scope": "machine",
        "title": "Bloquear pendrives / discos USB",
        "desc":  "Impede o servico USBSTOR de iniciar (bloqueia pendrives e HDs USB).",
        "key":   "SYSTEM\\CurrentControlSet\\Services\\USBSTOR",
        "value": "Start", "type": REG_DWORD,
        "options": {"Bloqueado": 4, "Permitido": 3},
    },
    {
        "id": "comp.no_autorun", "scope": "machine",
        "title": "Desativar Autorun em todas as unidades",
        "key":   "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer",
        "value": "NoDriveTypeAutoRun", "type": REG_DWORD,
        "options": {"Todas as unidades (255)": 0xFF},
    },
    {
        "id": "comp.disable_smb1", "scope": "machine",
        "title": "Desabilitar cliente SMBv1",
        "key":   "SYSTEM\\CurrentControlSet\\Services\\LanmanWorkstation\\Parameters",
        "value": "AllowInsecureGuestAuth", "type": REG_DWORD,
        "options": {"Bloquear guest inseguro": 0},
    },
    {
        "id": "comp.uac_admin_prompt", "scope": "machine",
        "title": "UAC: comportamento do prompt para Administradores",
        "desc":  "0=elevar sem aviso, 2=consentir desktop seguro (default), 5=consentir sempre.",
        "key":   "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System",
        "value": "ConsentPromptBehaviorAdmin", "type": REG_DWORD,
        "options": {"Sem aviso (0)": 0, "Consentir (2)": 2, "Sempre pedir senha (1)": 1},
    },
    {
        "id": "comp.lockscreen_timeout", "scope": "machine",
        "title": "Tempo ate bloquear maquina ociosa (segundos)",
        "key":   "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System",
        "value": "InactivityTimeoutSecs", "type": REG_DWORD,
        "options": {"5 min": 300, "10 min": 600, "15 min": 900, "30 min": 1800, "1 hora": 3600},
    },
    {
        "id": "comp.windows_update_au", "scope": "machine",
        "title": "Configurar Windows Update (Auto)",
        "desc":  "2=notificar antes de baixar, 3=baixar e notificar, 4=baixar e instalar agendado.",
        "key":   "Software\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU",
        "value": "AUOptions", "type": REG_DWORD,
        "options": {"Notificar antes (2)": 2, "Baixar e notificar (3)": 3, "Auto-instalar (4)": 4},
    },
    {
        "id": "comp.firewall_domain_on", "scope": "machine",
        "title": "Ativar Firewall do Windows (perfil de Dominio)",
        "key":   "Software\\Policies\\Microsoft\\WindowsFirewall\\DomainProfile",
        "value": "EnableFirewall", "type": REG_DWORD,
        "options": {"Ativo": 1, "Desativado": 0},
    },
    {
        "id": "comp.disable_telemetry", "scope": "machine",
        "title": "Reduzir telemetria do Windows",
        "key":   "Software\\Policies\\Microsoft\\Windows\\DataCollection",
        "value": "AllowTelemetry", "type": REG_DWORD,
        "options": {"Seguranca apenas (0)": 0, "Basico (1)": 1, "Avancado (2)": 2},
    },
    {
        "id": "comp.legal_notice_caption", "scope": "machine",
        "title": "Banner de logon - Titulo",
        "desc":  "Texto que aparece no topo do banner antes do login.",
        "key":   "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System",
        "value": "legalnoticecaption", "type": REG_SZ,
        "options": {"ATLAS": "ATLAS Corp.", "Aviso": "Aviso de seguranca"},
        "free_text": True,
    },
    {
        "id": "comp.legal_notice_text", "scope": "machine",
        "title": "Banner de logon - Texto",
        "key":   "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System",
        "value": "legalnoticetext", "type": REG_SZ,
        "options": {"Padrao": "Acesso restrito a usuarios autorizados. Atividades sao monitoradas."},
        "free_text": True,
    },
]


def catalog_index() -> Dict[str, Dict]:
    return {p["id"]: p for p in CATALOG}


def find_in_catalog(scope: str, key: str, name: str) -> Optional[Dict]:
    for p in CATALOG:
        if p["scope"] == scope and p["key"].lower() == key.lower() \
                and p["value"].lower() == name.lower():
            return p
    return None
