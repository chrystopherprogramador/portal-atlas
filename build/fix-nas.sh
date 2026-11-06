#!/bin/bash
set -e
PUB='command="borg serve --restrict-to-path /srv/borg/atlas --append-only",restrict ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEfr5CLP4BqMPLCsXy2Gn3Xpi255MJx/SdxIEdnIS1cr atlas-backup@atlas'
HOME_B=$(getent passwd backup | cut -d: -f6)
echo "HOME do usuario backup = $HOME_B"

mkdir -p "$HOME_B/.ssh"
chown backup:backup "$HOME_B"
chmod 755 "$HOME_B"
echo "$PUB" > "$HOME_B/.ssh/authorized_keys"
chown -R backup:backup "$HOME_B/.ssh"
chmod 700 "$HOME_B/.ssh"
chmod 600 "$HOME_B/.ssh/authorized_keys"

usermod -s /bin/bash backup
usermod -p '*' backup

mkdir -p /srv/borg/atlas
chown -R backup:backup /srv/borg
chmod 700 /srv/borg/atlas

# limpa o authorized_keys errado se existir em /home/backup
if [ -e /home/backup ] && [ "$HOME_B" != "/home/backup" ]; then
  rm -rf /home/backup
  echo "removido /home/backup (errado)"
fi

echo "--- authorized_keys ---"
ls -la "$HOME_B/.ssh"
echo "--- passwd -S ---"
passwd -S backup
echo "--- getent ---"
getent passwd backup
echo DONE
