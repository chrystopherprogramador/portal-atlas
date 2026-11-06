# Snippet nginx para terminal web (ttyd) - incluir no server block do portal.
# Deve ser colado ANTES do 'location / { proxy_pass ... 127.0.0.1:8080 ... }'

# Endpoint interno chamado por auth_request; valida sessao Flask
location = /terminal-auth-check {
    internal;
    proxy_pass              http://127.0.0.1:8080/auth-check;
    proxy_pass_request_body off;
    proxy_set_header        Content-Length "";
    proxy_set_header        X-Original-URI $request_uri;
    proxy_set_header        Cookie $http_cookie;
}

# Proxy para o ttyd (inclui WebSocket upgrade)
location /terminal-ws/ {
    auth_request /terminal-auth-check;
    error_page 401 = @terminal_redir;

    proxy_pass          http://127.0.0.1:7681;
    proxy_http_version  1.1;
    proxy_set_header    Host $host;
    proxy_set_header    Upgrade $http_upgrade;
    proxy_set_header    Connection "upgrade";
    proxy_set_header    X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header    X-Forwarded-Proto https;
    proxy_read_timeout  86400s;
    proxy_send_timeout  86400s;
    proxy_buffering     off;
}

location @terminal_redir {
    return 302 /login?next=/terminal;
}
