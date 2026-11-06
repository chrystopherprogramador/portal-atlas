# ATLAS Portal

Portal de administracao retro (estilo 2005) para o controlador de dominio Atlas.

## O que faz
- Autentica via LDAP (AD Samba) - apenas membros de `PortalAdmins` ou `Domain Admins`.
- Gerencia Usuarios, Grupos, OUs, GPOs e peers WireGuard.
- Gerencia compartilhamentos Samba e usuarios FTP (vsftpd).
- Audit log em SQLite (/var/lib/portal-atlas/audit.db).
- Servido por gunicorn + nginx (HTTPS self-signed), acessivel somente pela LAN e VPN.

## Deploy

No Windows, envia o codigo para o Atlas:

```powershell
scp -i $env:USERPROFILE\.ssh\id_ed25519_atlas -r C:\Users\samos\portal-atlas tecnologia@172.16.3.100:/tmp/
ssh -i $env:USERPROFILE\.ssh\id_ed25519_atlas tecnologia@172.16.3.100 "sudo bash /tmp/portal-atlas/deploy/install.sh"
```

## URLs
- LAN: https://atlas.texasco.local/
- VPN: https://10.8.0.1/

## Usuario inicial
`Administrator@texasco.local` + senha do AD. Depois crie um usuario pessoal e coloque
em `PortalAdmins` pelo proprio portal.
