#!/usr/bin/env bash
# ==============================================================================
# ATLAS Backup - Borg wrapper
# Uso:
#   atlas-backup.sh run        # executa backup + prune (ou dispara em background)
#   atlas-backup.sh status     # JSON com estado da ultima execucao
#   atlas-backup.sh list       # JSON com archives do repo
#   atlas-backup.sh info       # JSON com stats do repo
#   atlas-backup.sh check      # borg check (integridade)
#   atlas-backup.sh prune      # aplica GFS manualmente
#   atlas-backup.sh mount PATH ARCHIVE   # monta archive em PATH (FUSE)
#   atlas-backup.sh umount PATH
#   atlas-backup.sh install-remote HOST  # adiciona SSH key + repo remoto
# ==============================================================================
set -o pipefail
umask 077

# ---------- Config ----------
ENV_FILE="/etc/atlas-backup/env"
STATE_DIR="/var/lib/atlas-backup"
LOG_FILE="/var/log/atlas-backup.log"
PID_FILE="/run/atlas-backup.pid"
LAST_JSON="${STATE_DIR}/last.json"
PROGRESS_FILE="${STATE_DIR}/progress.json"
LOCK_FILE="/run/atlas-backup.lock"
TIMER_OVERRIDE="/etc/systemd/system/atlas-backup.timer.d/schedule.conf"

# shellcheck disable=SC1090
[ -r "$ENV_FILE" ] && . "$ENV_FILE"

: "${BORG_REPO:=/var/backups/atlas-local}"
: "${BORG_PASSPHRASE:?Defina BORG_PASSPHRASE em $ENV_FILE}"
: "${RETENTION_DAILY:=7}"
: "${RETENTION_WEEKLY:=4}"
: "${RETENTION_MONTHLY:=12}"
: "${RETENTION_YEARLY:=3}"
: "${COMPRESSION:=zstd,6}"
: "${STAGE_DIR:=/var/tmp/atlas-backup-stage}"

export BORG_REPO BORG_PASSPHRASE
export BORG_RELOCATED_REPO_ACCESS_IS_OK=yes
export BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK=no

mkdir -p "$STATE_DIR"

# ---------- Helpers ----------
log()  { echo "[$(date -Is)] $*" | tee -a "$LOG_FILE" >&2; }
die()  { log "ERRO: $*"; write_state failed "$*"; write_progress 100 "falha" "$*"; exit 1; }

write_progress() {
  # write_progress PERCENT "PHASE" "DETAIL"
  local pct="${1:-0}" phase="${2:-}" detail="${3:-}"
  python3 - "$pct" "$phase" "$detail" <<'PY' > "$PROGRESS_FILE.tmp" 2>/dev/null
import json, sys, time
pct, phase, detail = sys.argv[1], sys.argv[2], sys.argv[3]
try: pct = max(0, min(100, int(pct)))
except Exception: pct = 0
json.dump({
  "percent": pct,
  "phase":   phase,
  "detail":  detail,
  "ts":      time.time(),
}, sys.stdout)
PY
  mv -f "$PROGRESS_FILE.tmp" "$PROGRESS_FILE" 2>/dev/null || true
  # Tambem loga para que aparece no log tail
  [ -n "$phase" ] && log "progress: ${pct}% $phase ${detail:+-- $detail}"
}

clear_progress() { rm -f "$PROGRESS_FILE" 2>/dev/null || true; }

write_state() {
  # write_state STATUS [ERROR]
  local status="$1" err="${2:-}"
  local archive="${ATLAS_ARCHIVE:-}" dur="${ATLAS_DUR:-0}"
  local stats_json="${ATLAS_STATS_JSON:-null}"
  local started="${ATLAS_STARTED:-}" finished; finished="$(date -Is)"
  local pid=$$
  python3 - "$status" "$err" "$archive" "$dur" "$started" "$finished" "$pid" "$stats_json" <<'PY' > "$LAST_JSON.tmp"
import json, sys
status, err, archive, dur, started, finished, pid, stats = sys.argv[1:9]
try: stats = json.loads(stats) if stats and stats != "null" else None
except Exception: stats = None
obj = {
    "status":       status,
    "error":        err or None,
    "archive":      archive or None,
    "duration_sec": int(dur) if dur and dur.isdigit() else None,
    "started":      started or None,
    "finished":     finished,
    "pid":          int(pid),
    "stats":        stats,
}
json.dump(obj, sys.stdout, indent=2)
PY
  mv -f "$LAST_JSON.tmp" "$LAST_JSON"
  emit_metrics || true
}

emit_metrics() {
  # Prometheus textfile collector (node_exporter)
  local dir=/var/lib/node_exporter/textfile
  [ -d "$dir" ] || return 0
  python3 - "$LAST_JSON" <<'PY' > "$dir/atlas_backup.prom.tmp" 2>/dev/null || return 0
import json, sys, datetime
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
st   = d.get("status") or "unknown"
ok   = 1 if st == "ok" else 0
run  = 1 if st == "running" else 0
fail = 1 if st == "failed" else 0
dur  = d.get("duration_sec") or 0
fin  = d.get("finished") or ""
try:
    ts = int(datetime.datetime.fromisoformat(fin.replace("Z","+00:00")).timestamp()) if fin else 0
except Exception:
    ts = 0
stats = d.get("stats") or {}
orig = int(stats.get("original_size") or 0)
comp = int(stats.get("compressed_size") or 0)
ded  = int(stats.get("deduplicated_size") or 0)
lines = [
    ("atlas_backup_status", ok, "1=ok,0=other"),
    ("atlas_backup_running", run, "1 if a backup is in progress"),
    ("atlas_backup_failed", fail, "1 if last backup failed"),
    ("atlas_backup_last_finish_timestamp", ts, "Unix ts of last finished backup"),
    ("atlas_backup_duration_seconds", dur, "Duration of last backup"),
    ("atlas_backup_original_bytes", orig, "Original data size in last archive"),
    ("atlas_backup_compressed_bytes", comp, "Compressed size in last archive"),
    ("atlas_backup_deduplicated_bytes", ded, "Deduplicated size in last archive"),
]
for name, val, help_ in lines:
    print(f"# HELP {name} {help_}")
    print(f"# TYPE {name} gauge")
    print(f"{name} {val}")
PY
  mv -f "$dir/atlas_backup.prom.tmp" "$dir/atlas_backup.prom" 2>/dev/null || true
  chmod 0644 "$dir/atlas_backup.prom" 2>/dev/null || true
}

borg_cmd() { /usr/bin/borg "$@"; }

# ---------- Subcommands ----------
cmd_init() {
  if [ -f "$BORG_REPO/README" ] || [ -f "$BORG_REPO/config" ]; then
    log "Repo ja existe em $BORG_REPO"
    return 0
  fi
  log "Criando repo Borg em $BORG_REPO"
  mkdir -p "$BORG_REPO"
  borg_cmd init --encryption=repokey-blake2 "$BORG_REPO" || die "init falhou"
  # export key backup
  borg_cmd key export "$BORG_REPO" /etc/atlas-backup/key-backup.txt || true
  chmod 600 /etc/atlas-backup/key-backup.txt 2>/dev/null || true
  log "Repo criado. Chave salva em /etc/atlas-backup/key-backup.txt -- FACA BACKUP DESSE ARQUIVO OFFLINE!"
}

_run_single() {
  local started archive stage
  started="$(date -Is)"
  archive="atlas-$(date -u +%Y-%m-%dT%H-%M-%S)"
  stage="${STAGE_DIR}/$(date +%s)"
  mkdir -p "$stage"

  export ATLAS_STARTED="$started"
  export ATLAS_ARCHIVE="$archive"

  log "===== Backup START (archive=$archive) ====="
  write_state running ""
  write_progress 2 "iniciando" "archive=$archive"

  # --- 1) Dump PostgreSQL (globals + per-db custom format) ---
  log "[1/5] PostgreSQL dump"
  write_progress 5 "PostgreSQL" "dump global + por banco"
  mkdir -p "$stage/postgres"
  sudo -u postgres pg_dumpall --globals-only > "$stage/postgres/globals.sql" 2>>"$LOG_FILE" \
     || log "WARN: pg_dumpall globals falhou"
  sudo -u postgres psql -tAc "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname<>'postgres'" 2>/dev/null \
    | while read -r db; do
        [ -z "$db" ] && continue
        log "  pg_dump: $db"
        write_progress 10 "PostgreSQL" "pg_dump $db"
        sudo -u postgres pg_dump --format=custom --compress=6 \
           --file "$stage/postgres/${db}.pgdump" "$db" 2>>"$LOG_FILE" \
           || log "WARN: pg_dump $db falhou"
      done

  # --- 2) Samba AD online backup (seguro em DC ao vivo) ---
  log "[2/5] Samba AD backup"
  write_progress 18 "Samba AD" "samba-tool domain backup online"
  mkdir -p "$stage/samba-ad"
  samba-tool domain backup online \
     --targetdir="$stage/samba-ad" \
     --server=localhost \
     -UAdministrator --password="${SAMBA_ADMIN_PASSWORD:-$BORG_PASSPHRASE}" \
     >>"$LOG_FILE" 2>&1 \
     || log "WARN: samba-tool domain backup falhou (offline fallback)"
  # fallback: cp /var/lib/samba se nao conseguiu
  if [ -z "$(ls -A "$stage/samba-ad" 2>/dev/null)" ]; then
     log "  fallback: copiando /var/lib/samba (cold)"
     write_progress 22 "Samba AD" "fallback tar /var/lib/samba"
     tar -C /var/lib -cf "$stage/samba-ad/samba-varlib.tar" samba 2>>"$LOG_FILE" || true
  fi

  # --- 3) Snapshot do estado do sistema ---
  log "[3/5] Snapshot estado"
  write_progress 28 "Snapshot sistema" "dpkg, systemctl, samba-tool, wg"
  mkdir -p "$stage/state"
  dpkg -l            > "$stage/state/dpkg-list.txt"                          2>&1 || true
  systemctl list-unit-files --state=enabled > "$stage/state/enabled-units.txt" 2>&1 || true
  samba-tool domain info 127.0.0.1 > "$stage/state/domain-info.txt"          2>&1 || true
  samba-tool user list > "$stage/state/users.txt"                            2>&1 || true
  samba-tool group list > "$stage/state/groups.txt"                          2>&1 || true
  ip -json addr > "$stage/state/ip-addr.json"                                2>&1 || true
  wg showconf wg0 > "$stage/state/wg0.conf"                                  2>&1 || true
  date -Is > "$stage/state/backup-date.txt"

  # --- 4) Borg create ---
  log "[4/5] borg create"
  write_progress 35 "Borg create (local)" "comprimindo e deduplicando..."
  local t0 t1 stats_json=""
  t0=$(date +%s)

  # rodamos com --stats --json-lines e capturamos stats finais
  local create_out
  create_out="$(
    borg_cmd create \
      --compression "$COMPRESSION" \
      --exclude-caches \
      --exclude '/srv/samba/shares/*/.recycle' \
      --exclude '/var/www/*/cache' \
      --exclude '/var/www/*/tmp' \
      --exclude '/tmp' \
      --exclude '/var/tmp/atlas-backup-stage' \
      --exclude '/var/cache' \
      --exclude '/var/log/journal' \
      --one-file-system \
      --stats --json \
      "::${archive}" \
      "$stage" \
      /etc \
      /opt/atlas-portal \
      /var/www \
      /srv/samba/shares \
      /root \
      /home \
      2>>"$LOG_FILE"
  )" || die "borg create falhou"

  t1=$(date +%s)
  export ATLAS_DUR=$((t1 - t0))
  stats_json="$(echo "$create_out" | python3 -c 'import json,sys
try:
  d=json.loads(sys.stdin.read())
  a=d.get("archive",{})
  s=a.get("stats",{})
  c=d.get("cache",{}).get("stats",{})
  print(json.dumps({
    "original_size":    s.get("original_size"),
    "compressed_size":  s.get("compressed_size"),
    "deduplicated_size":s.get("deduplicated_size"),
    "nfiles":           s.get("nfiles"),
    "repo_total_unique_chunks":  c.get("total_unique_chunks"),
    "repo_total_size":           c.get("total_size"),
    "repo_total_csize":          c.get("total_csize"),
    "repo_unique_size":          c.get("unique_size"),
    "repo_unique_csize":         c.get("unique_csize"),
  }))
except Exception as e:
  print("null")
' )"
  export ATLAS_STATS_JSON="$stats_json"
  write_progress 60 "Borg create concluido" "archive gravado em ${BORG_REPO}"

  # --- 5) Prune GFS ---
  log "[5/5] borg prune GFS ($RETENTION_DAILY/$RETENTION_WEEKLY/$RETENTION_MONTHLY/$RETENTION_YEARLY)"
  write_progress 65 "Prune GFS" "aplicando politica de retencao"
  borg_cmd prune --list \
    --glob-archives 'atlas-*' \
    --keep-daily   "$RETENTION_DAILY"   \
    --keep-weekly  "$RETENTION_WEEKLY"  \
    --keep-monthly "$RETENTION_MONTHLY" \
    --keep-yearly  "$RETENTION_YEARLY"  \
    >>"$LOG_FILE" 2>&1 || log "WARN: prune falhou"
  write_progress 70 "Compact" "liberando espaco no repo"
  borg_cmd compact >>"$LOG_FILE" 2>&1 || true

  # --- Replicacao remota (opcional) via Borg-over-SSH ---
  if [ -n "${REMOTE_REPO:-}" ]; then
    log "Replicando archive '$archive' para $REMOTE_REPO"
    write_progress 75 "Replicacao NAS" "enviando para $REMOTE_REPO"
    export BORG_RSH="ssh -i ${REMOTE_SSH_KEY:-/etc/atlas-backup/id_ed25519} -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20"
    # borg init remoto se ainda nao existe (idempotente)
    if ! BORG_REPO="$REMOTE_REPO" borg_cmd info >/dev/null 2>&1; then
      log "  repo remoto nao inicializado, rodando borg init..."
      write_progress 76 "Replicacao NAS" "borg init remoto"
      BORG_REPO="$REMOTE_REPO" borg_cmd init --encryption=repokey-blake2 >>"$LOG_FILE" 2>&1 \
        || log "  WARN: init remoto falhou (pode ja existir)"
    fi
    # borg create remoto com os MESMOS paths
    write_progress 80 "Replicacao NAS" "borg create remoto"
    BORG_REPO="$REMOTE_REPO" borg_cmd create \
      --compression "$COMPRESSION" \
      --exclude-caches \
      --exclude '/srv/samba/shares/*/.recycle' \
      --exclude '/var/www/*/cache' \
      --exclude '/var/www/*/tmp' \
      --exclude '/tmp' \
      --exclude '/var/tmp/atlas-backup-stage' \
      --exclude '/var/cache' \
      --exclude '/var/log/journal' \
      --one-file-system \
      "::${archive}" \
      "$stage" /etc /opt/atlas-portal /var/www /srv/samba/shares /root /home \
      >>"$LOG_FILE" 2>&1 \
      && log "  replicacao remota OK" \
      || log "  WARN: replicacao remota falhou (veja $LOG_FILE)"
    # prune remoto tambem
    write_progress 92 "Replicacao NAS" "prune remoto"
    BORG_REPO="$REMOTE_REPO" borg_cmd prune --list \
      --glob-archives 'atlas-*' \
      --keep-daily   "$RETENTION_DAILY"   \
      --keep-weekly  "$RETENTION_WEEKLY"  \
      --keep-monthly "$RETENTION_MONTHLY" \
      --keep-yearly  "$RETENTION_YEARLY"  \
      >>"$LOG_FILE" 2>&1 || log "  WARN: prune remoto falhou"
  fi

  # --- Cleanup ---
  write_progress 97 "Finalizando" "limpando staging"
  rm -rf "$stage"

  log "===== Backup OK (archive=$archive dur=${ATLAS_DUR}s) ====="
  write_state ok ""
  write_progress 100 "concluido" "archive=$archive duracao=${ATLAS_DUR}s"
}

cmd_run() {
  # lock exclusivo (flock)
  exec 9>"$LOCK_FILE"
  flock -n 9 || { log "Backup ja em execucao. Saindo."; exit 0; }
  echo $$ > "$PID_FILE"
  trap 'rm -f "$PID_FILE"' EXIT
  cmd_init
  _run_single
}

cmd_run_detached() {
  # Dispara em background para o portal poder retornar rapido
  nohup "$0" run >>"$LOG_FILE" 2>&1 &
  echo "{\"started\":true,\"pid\":$!}"
}

cmd_status() {
  local running="false"
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE" 2>/dev/null)" 2>/dev/null; then
    running="true"
  fi
  local last='{}'
  [ -r "$LAST_JSON" ] && last="$(cat "$LAST_JSON")"
  local next=""
  next="$(systemctl show atlas-backup.timer -p NextElapseUSecRealtime --value 2>/dev/null || true)"
  python3 - "$running" "$last" "$next" <<'PY'
import json, sys
running, last, next_run = sys.argv[1], sys.argv[2], sys.argv[3]
try: last = json.loads(last)
except Exception: last = {}
print(json.dumps({
    "running": running == "true",
    "last":    last,
    "next":    next_run or None,
}))
PY
}

cmd_list() {
  borg_cmd list --json "$BORG_REPO" 2>>"$LOG_FILE" || echo '{"archives":[]}'
}

cmd_info() {
  borg_cmd info --json "$BORG_REPO" 2>>"$LOG_FILE" || echo '{}'
}

cmd_check() {
  log "===== borg check ====="
  borg_cmd check --verbose "$BORG_REPO" >>"$LOG_FILE" 2>&1
  local rc=$?
  log "===== borg check rc=$rc ====="
  return $rc
}

cmd_prune() {
  borg_cmd prune --list \
    --glob-archives 'atlas-*' \
    --keep-daily   "$RETENTION_DAILY"   \
    --keep-weekly  "$RETENTION_WEEKLY"  \
    --keep-monthly "$RETENTION_MONTHLY" \
    --keep-yearly  "$RETENTION_YEARLY"
  borg_cmd compact "$BORG_REPO"
}

cmd_mount() {
  local mnt="$1" archive="$2"
  [ -z "$mnt" ] && die "uso: mount PATH ARCHIVE"
  mkdir -p "$mnt"
  borg_cmd mount "::${archive}" "$mnt"
}

cmd_umount() {
  local mnt="$1"
  [ -z "$mnt" ] && die "uso: umount PATH"
  borg_cmd umount "$mnt"
}

cmd_install_remote() {
  local host="$1"
  local keyfile="/etc/atlas-backup/id_ed25519"
  if [ ! -f "$keyfile" ]; then
    ssh-keygen -t ed25519 -N "" -f "$keyfile" -C "atlas-backup@$(hostname)"
    chmod 600 "$keyfile"
    chmod 644 "${keyfile}.pub"
  fi
  if [ -n "$host" ] && [ "$host" != "dummy@dummy:/dummy" ]; then
    echo "==> Chave publica para adicionar em ~/.ssh/authorized_keys no NAS:"
    cat "${keyfile}.pub"
    echo "==> Depois edite $ENV_FILE e defina REMOTE_REPO=$host"
  else
    echo "chave pronta em ${keyfile}.pub"
  fi
}

cmd_set_remote() {
  local url="$1"
  [ -z "$url" ] && die "uso: set-remote ssh://user@host:port/path"
  mkdir -p "$(dirname "$ENV_FILE")"
  if [ -f "$ENV_FILE" ]; then
    # remove linha antiga REMOTE_REPO= (se houver) e acrescenta nova
    sed -i '/^REMOTE_REPO=/d' "$ENV_FILE"
  fi
  echo "REMOTE_REPO=$url" >> "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "{\"ok\":true,\"remote_repo\":\"$url\"}"
}

cmd_init_remote() {
  [ -z "${REMOTE_REPO:-}" ] && die "REMOTE_REPO nao configurado em $ENV_FILE"
  export BORG_RSH="ssh -i ${REMOTE_SSH_KEY:-/etc/atlas-backup/id_ed25519} -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20"
  # se ja inicializado, ok
  if BORG_REPO="$REMOTE_REPO" borg_cmd info >/dev/null 2>&1; then
    echo "{\"ok\":true,\"already\":true}"
    return 0
  fi
  BORG_REPO="$REMOTE_REPO" borg_cmd init --encryption=repokey-blake2 \
    || die "falha ao inicializar repo remoto"
  echo "{\"ok\":true,\"already\":false}"
}

cmd_remote_test() {
  local url="${1:-${REMOTE_REPO:-}}"
  [ -z "$url" ] && die "uso: remote-test URL (ou configure REMOTE_REPO)"
  export BORG_RSH="ssh -i ${REMOTE_SSH_KEY:-/etc/atlas-backup/id_ed25519} -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -o BatchMode=yes"
  BORG_REPO="$url" borg_cmd info --json 2>&1
}

cmd_progress() {
  # Retorna JSON com progresso atual + tail do log
  local n="${1:-40}"
  local prog='{}'
  [ -r "$PROGRESS_FILE" ] && prog="$(cat "$PROGRESS_FILE")"
  local tail_lines=""
  [ -r "$LOG_FILE" ] && tail_lines="$(tail -n "$n" "$LOG_FILE" 2>/dev/null || true)"
  local running="false"
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE" 2>/dev/null)" 2>/dev/null; then
    running="true"
  fi
  python3 - "$prog" "$tail_lines" "$running" <<'PY'
import json, sys
prog_raw, tail, running = sys.argv[1], sys.argv[2], sys.argv[3]
try: prog = json.loads(prog_raw) if prog_raw.strip() else {}
except Exception: prog = {}
print(json.dumps({
    "running": running == "true",
    "percent": prog.get("percent", 0),
    "phase":   prog.get("phase", ""),
    "detail":  prog.get("detail", ""),
    "ts":      prog.get("ts", 0),
    "log":     tail.splitlines()[-60:],
}))
PY
}

cmd_logtail() {
  local n="${1:-100}"
  [ -r "$LOG_FILE" ] && tail -n "$n" "$LOG_FILE" || echo ""
}

cmd_get_schedule() {
  # Retorna JSON {hour, minute, source, next, oncalendar}
  local oncal=""
  if [ -r "$TIMER_OVERRIDE" ]; then
    oncal="$(grep -E '^OnCalendar=' "$TIMER_OVERRIDE" | tail -n1 | cut -d= -f2-)"
  fi
  if [ -z "$oncal" ]; then
    oncal="$(systemctl show atlas-backup.timer -p TimersCalendar --value 2>/dev/null | head -n1)"
  fi
  local next
  next="$(systemctl show atlas-backup.timer -p NextElapseUSecRealtime --value 2>/dev/null || true)"
  python3 - "$oncal" "$next" <<'PY'
import json, sys, re
oncal, nxt = sys.argv[1], sys.argv[2]
hour = minute = None
# extrai HH:MM de "OnCalendar=*-*-* 01:30:00" ou "{ OnCalendar=*-*-* 01:30:00 ; ... }"
m = re.search(r'(\d{1,2}):(\d{2})(?::\d{2})?', oncal or "")
if m:
    hour, minute = int(m.group(1)), int(m.group(2))
print(json.dumps({
  "hour":       hour,
  "minute":     minute,
  "oncalendar": oncal.strip(),
  "next":       nxt,
  "source":     "override" if hour is not None else "default",
}))
PY
}

cmd_set_schedule() {
  # uso: set-schedule HH:MM  (hora local)
  local hm="$1"
  [ -z "$hm" ] && die "uso: set-schedule HH:MM"
  if ! [[ "$hm" =~ ^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$ ]]; then
    die "formato invalido. Use HH:MM entre 00:00 e 23:59"
  fi
  local HH="${BASH_REMATCH[1]}" MM="${BASH_REMATCH[2]}"
  # pad zero
  printf -v HH "%02d" "$((10#$HH))"
  mkdir -p "$(dirname "$TIMER_OVERRIDE")"
  cat > "$TIMER_OVERRIDE" <<EOF
# Gerado pelo portal ATLAS em $(date -Is)
[Timer]
OnCalendar=
OnCalendar=*-*-* ${HH}:${MM}:00
Persistent=true
EOF
  systemctl daemon-reload
  systemctl restart atlas-backup.timer
  log "Schedule alterado para ${HH}:${MM} (local). OnCalendar=*-*-* ${HH}:${MM}:00"
  echo "{\"ok\":true,\"hour\":${HH#0},\"minute\":${MM#0},\"oncalendar\":\"*-*-* ${HH}:${MM}:00\"}"
}

# ---------- Main ----------
case "${1:-}" in
  run)            cmd_run ;;
  run-detached)   cmd_run_detached ;;
  status)         cmd_status ;;
  list)           cmd_list ;;
  info)           cmd_info ;;
  check)          cmd_check ;;
  prune)          cmd_prune ;;
  mount)          shift; cmd_mount "$@" ;;
  umount)         shift; cmd_umount "$@" ;;
  install-remote) shift; cmd_install_remote "$@" ;;
  set-remote)     shift; cmd_set_remote "$@" ;;
  init-remote)    cmd_init_remote ;;
  remote-test)    shift; cmd_remote_test "$@" ;;
  progress)       shift; cmd_progress "$@" ;;
  logtail)        shift; cmd_logtail "$@" ;;
  get-schedule)   cmd_get_schedule ;;
  set-schedule)   shift; cmd_set_schedule "$@" ;;
  init)           cmd_init ;;
  metrics)        emit_metrics ;;
  *) echo "Uso: $0 {run|run-detached|status|list|info|check|prune|mount|umount|install-remote|set-remote|init-remote|remote-test|progress|logtail|get-schedule|set-schedule|init|metrics}" >&2; exit 1 ;;
esac
