#!/bin/bash
set +e
echo "=== OUs ==="
sudo -u root samba-tool ou list 2>&1 | sort
echo
echo "=== Grupos ==="
sudo -u root samba-tool group list 2>&1 | sort
echo
echo "=== Usuarios (sample) ==="
sudo -u root samba-tool user list 2>&1 | head -30
echo
echo "=== GPOs existentes ==="
sudo -u root samba-tool gpo listall 2>&1
