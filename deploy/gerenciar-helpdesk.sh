#!/bin/bash
# gerenciar-helpdesk.sh — deploy/rollback do /var/www/helpdesk
#
# Uso (root via sudo):
#   gerenciar-helpdesk.sh deploy <zipfile> [tag]
#   gerenciar-helpdesk.sh deploy_log <zipfile> <tag> <jobid>   (async; loga em /var/log/atlas-portal/helpdesk/<jobid>.log)
#   gerenciar-helpdesk.sh rollback <stamp>
#   gerenciar-helpdesk.sh rollback_log <stamp> <jobid>
#   gerenciar-helpdesk.sh list
#   gerenciar-helpdesk.sh purge <keep_n>
#   gerenciar-helpdesk.sh delete <stamp>
#   gerenciar-helpdesk.sh info

TARGET="/var/www/helpdesk"
BACKUP_ROOT="/var/backups/atlas-portal/helpdesk"
LOGDIR="/var/log/atlas-portal/helpdesk"
PRESERVE_FILE="/etc/portal-atlas/helpdesk-preserve.list"
KEEP_DEFAULT=10

mkdir -p "$BACKUP_ROOT" "$LOGDIR"

if [ ! -f "$PRESERVE_FILE" ]; then
  mkdir -p "$(dirname "$PRESERVE_FILE")"
  cat > "$PRESERVE_FILE" <<'EOF'
# Caminhos relativos a /var/www/helpdesk/ que NAO devem ser
# substituidos por deploys ou rollbacks. Um por linha.
config/database.php
EOF
fi

stamp_now() { date +%Y%m%d-%H%M%S; }
log_step()  { echo "[$(date +%H:%M:%S)] $*"; }

read_preserve_list() {
  if [ -f "$PRESERVE_FILE" ]; then
    while IFS= read -r line; do
      line="${line%%#*}"
      line="$(echo "$line" | sed -e 's/^[[:space:]]*//;s/[[:space:]]*$//')"
      [ -z "$line" ] && continue
      line="${line#/}"
      [[ "$line" == *".."* ]] && continue
      echo "$line"
    done < "$PRESERVE_FILE"
  fi
}

stash_preserved() {
  local STASH="$1"
  local count=0
  while IFS= read -r rel; do
    [ -z "$rel" ] && continue
    local src="$TARGET/$rel"
    if [ -e "$src" ]; then
      mkdir -p "$STASH/$(dirname "$rel")"
      cp -a "$src" "$STASH/$rel"
      log_step "PRESERVADO: $rel ($(stat -c%s "$src" 2>/dev/null) bytes)"
      count=$((count+1))
    else
      log_step "preserve: $rel nao existe no target (ignorado)"
    fi
  done < <(read_preserve_list)
  log_step "Total preservado: $count item(ns)"
}

restore_preserved() {
  local STASH="$1"
  if [ -d "$STASH" ] && [ -n "$(ls -A "$STASH" 2>/dev/null)" ]; then
    cp -a "$STASH/." "$TARGET/"
    log_step "Arquivos preservados restaurados em $TARGET"
  fi
}

cmd_info() {
  if [ -d "$TARGET" ]; then
    SIZE=$(du -sh "$TARGET" 2>/dev/null | awk '{print $1}')
    NF=$(find "$TARGET" -type f 2>/dev/null | wc -l)
    echo "TARGET=$TARGET"
    echo "SIZE=$SIZE"
    echo "FILES=$NF"
    if [ -f "$TARGET/.atlas-version.txt" ]; then
      echo "VERSION=$(cat "$TARGET/.atlas-version.txt")"
    fi
  else
    echo "TARGET=$TARGET (NAO EXISTE)"
  fi
  echo "BACKUP_ROOT=$BACKUP_ROOT"
  echo "PRESERVE_LIST=$PRESERVE_FILE"
  echo "PRESERVE_ITEMS=$(read_preserve_list | wc -l)"
}

cmd_list() {
  cd "$BACKUP_ROOT" || return
  shopt -s nullglob
  for d in */; do
    d="${d%/}"
    META=""
    [ -f "$d/.meta" ] && META=$(cat "$d/.meta")
    SIZE=$(du -sh "$d" 2>/dev/null | awk '{print $1}')
    echo "STAMP=$d|SIZE=$SIZE|META=$META"
  done | sort -r
}

cmd_deploy() {
  set -e
  local ZIP="$1"
  local TAG="${2:-deploy}"
  if [ ! -f "$ZIP" ]; then
    echo "ERRO: zip nao encontrado: $ZIP" >&2; return 2
  fi
  command -v unzip >/dev/null 2>&1 || { echo "ERRO: unzip nao instalado" >&2; return 2; }

  local ZSIZE; ZSIZE=$(stat -c%s "$ZIP" 2>/dev/null || echo "?")
  log_step "==== DEPLOY iniciado tag=$TAG ===="
  log_step "Zip: $ZIP ($ZSIZE bytes)"

  local STAMP; STAMP=$(stamp_now)
  local BK="$BACKUP_ROOT/$STAMP"

  if [ -d "$TARGET" ] && [ -n "$(ls -A "$TARGET" 2>/dev/null)" ]; then
    log_step "Fazendo backup -> $BK"
    mkdir -p "$BK"
    cp -a "$TARGET/." "$BK/"
    echo "{\"ts\":\"$STAMP\",\"tag\":\"backup_pre_$TAG\",\"src\":\"$TARGET\"}" > "$BK/.meta"
    log_step "Backup OK ($(du -sh "$BK" | awk '{print $1}'))"
  else
    log_step "TARGET vazio, sem backup"
  fi

  local STAGE; STAGE=$(mktemp -d /var/tmp/hd_stage_XXXXXX)
  log_step "Extraindo zip em $STAGE"
  unzip -q -o "$ZIP" -d "$STAGE"
  log_step "Extraido. Conteudo raiz: $(ls -1 "$STAGE" | tr '\n' ' ')"

  local ENTRIES; ENTRIES=$(ls -1 "$STAGE" | wc -l)
  if [ "$ENTRIES" = "1" ]; then
    local SUB; SUB="$STAGE/$(ls -1 "$STAGE")"
    if [ -d "$SUB" ]; then
      STAGE="$SUB"
      log_step "Pasta raiz unica detectada -> achatando para $STAGE"
    fi
  fi
  log_step "Total a publicar: $(find "$STAGE" -type f | wc -l) arquivo(s) ($(du -sh "$STAGE" | awk '{print $1}'))"

  local STASH; STASH=$(mktemp -d /var/tmp/hd_stash_XXXXXX)
  log_step "Stashing arquivos preservados..."
  stash_preserved "$STASH"

  log_step "Limpando $TARGET"
  mkdir -p "$TARGET"
  find "$TARGET" -mindepth 1 -maxdepth 1 -exec rm -rf {} +

  log_step "Copiando novo conteudo..."
  cp -a "$STAGE/." "$TARGET/"

  log_step "Restaurando arquivos preservados (sobrepoe o do zip)..."
  restore_preserved "$STASH"

  log_step "Aplicando permissoes www-data:www-data"
  chown -R www-data:www-data "$TARGET"
  find "$TARGET" -type d -exec chmod 755 {} +
  find "$TARGET" -type f -exec chmod 644 {} +
  echo "$STAMP $TAG" > "$TARGET/.atlas-version.txt"
  chown www-data:www-data "$TARGET/.atlas-version.txt"

  rm -rf "$STAGE" "$STASH" "$ZIP" 2>/dev/null || true

  log_step "==== DEPLOY OK stamp=$STAMP tag=$TAG ===="
  echo "STAMP=$STAMP"
}

cmd_rollback() {
  set -e
  local STAMP="$1"
  local BK="$BACKUP_ROOT/$STAMP"
  if [ ! -d "$BK" ]; then
    echo "ERRO: backup nao encontrado: $STAMP" >&2; return 2
  fi
  log_step "==== ROLLBACK iniciado para $STAMP ===="

  local NOW; NOW=$(stamp_now)
  local BK2="$BACKUP_ROOT/$NOW"
  if [ -d "$TARGET" ] && [ -n "$(ls -A "$TARGET" 2>/dev/null)" ]; then
    log_step "Backup pre-rollback -> $BK2"
    mkdir -p "$BK2"
    cp -a "$TARGET/." "$BK2/"
    echo "{\"ts\":\"$NOW\",\"tag\":\"backup_pre_rollback_to_$STAMP\",\"src\":\"$TARGET\"}" > "$BK2/.meta"
  fi

  local STASH; STASH=$(mktemp -d /var/tmp/hd_stash_XXXXXX)
  log_step "Stashing arquivos preservados (estado atual)..."
  stash_preserved "$STASH"

  log_step "Restaurando $STAMP -> $TARGET"
  find "$TARGET" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  cp -a "$BK/." "$TARGET/"
  # remove o .meta do backup que foi copiado pra dentro do target
  rm -f "$TARGET/.meta"

  log_step "Restaurando arquivos preservados sobre o backup..."
  restore_preserved "$STASH"

  chown -R www-data:www-data "$TARGET"
  find "$TARGET" -type d -exec chmod 755 {} +
  find "$TARGET" -type f -exec chmod 644 {} +
  echo "$STAMP rollback" > "$TARGET/.atlas-version.txt"
  chown www-data:www-data "$TARGET/.atlas-version.txt"

  rm -rf "$STASH" 2>/dev/null || true
  log_step "==== ROLLBACK OK $STAMP ===="
}

cmd_purge() {
  local KEEP="${1:-$KEEP_DEFAULT}"
  cd "$BACKUP_ROOT" || return
  shopt -s nullglob
  local arr=( */ )
  local sorted
  IFS=$'\n' read -r -d '' -a sorted < <(printf '%s\n' "${arr[@]}" | sort -r && printf '\0')
  local i=0 removed=0
  for d in "${sorted[@]}"; do
    d="${d%/}"
    i=$((i+1))
    if [ "$i" -gt "$KEEP" ]; then
      rm -rf "$d"
      removed=$((removed+1))
    fi
  done
  echo "OK purge keep=$KEEP removidos=$removed"
}

cmd_delete() {
  local STAMP="$1"
  local BK="$BACKUP_ROOT/$STAMP"
  if [ ! -d "$BK" ]; then
    echo "backup nao encontrado: $STAMP" >&2; exit 2
  fi
  rm -rf "$BK"
  echo "OK delete stamp=$STAMP"
}

# wrapper async: executa cmd_X redirecionando p/ logfile e gravando status
run_async() {
  local SUBCMD="$1"; shift
  local JOBID="$1"; shift
  if ! [[ "$JOBID" =~ ^[a-zA-Z0-9_-]{4,40}$ ]]; then
    echo "ERRO: jobid invalido" >&2; exit 2
  fi
  local LOG="$LOGDIR/$JOBID.log"
  local STATUS="$LOGDIR/$JOBID.status"
  : > "$LOG"
  echo "RUNNING" > "$STATUS"
  {
    "$SUBCMD" "$@"
  } >> "$LOG" 2>&1
  local RC=$?
  echo "" >> "$LOG"
  if [ "$RC" = "0" ]; then
    echo "[$(date +%H:%M:%S)] === Concluido com sucesso (rc=0) ===" >> "$LOG"
  else
    echo "[$(date +%H:%M:%S)] === FALHOU (rc=$RC) ===" >> "$LOG"
  fi
  echo "$RC" > "$STATUS"
  exit $RC
}

case "${1:-}" in
  info)         cmd_info ;;
  list)         cmd_list ;;
  deploy)       shift; cmd_deploy "$@" ;;
  rollback)     shift; cmd_rollback "$@" ;;
  deploy_log)   ZIP="$2"; TAG="$3"; JOBID="$4"
                run_async cmd_deploy "$JOBID" "$ZIP" "$TAG" ;;
  rollback_log) STAMP="$2"; JOBID="$3"
                run_async cmd_rollback "$JOBID" "$STAMP" ;;
  purge)        shift; cmd_purge "$@" ;;
  delete)       shift; cmd_delete "$@" ;;
  *)
    echo "uso: $0 {info|list|deploy|deploy_log|rollback|rollback_log|purge|delete}" >&2
    exit 2 ;;
esac
