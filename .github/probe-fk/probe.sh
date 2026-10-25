#!/usr/bin/env bash
# TEMPORARY diagnostics for Firo-tour TLS and Koala robots/sitemaps. Delete when done.
set +e
for h in www.firotour.sk firotour.sk www.firotour.cz; do
  echo "================ $h"
  echo | timeout 20 openssl s_client -connect $h:443 -servername $h -showcerts 2>&1 \
    | grep -E "^( *[0-9] s:| *i:|depth|verify|Verify return|Verification|subject=|issuer=| +v:)" | head -30
  echo | timeout 20 openssl s_client -connect $h:443 -servername $h -showcerts 2>/dev/null \
    | awk '/BEGIN CERT/{n++} n==1{print} /END CERT/{if(n==1) exit}' > /tmp/leaf_$h.pem
  openssl x509 -in /tmp/leaf_$h.pem -noout -subject -issuer -dates -ext subjectAltName,authorityInfoAccess -fingerprint -sha256 2>&1
  curl -sS -o /dev/null -w "curl %{http_code} ssl_verify=%{ssl_verify_result}\n" https://$h/ 2>&1 | head -3
done
python3 - <<'PY'
import requests, ssl, certifi
for u in ["https://www.firotour.sk/robots.txt", "https://www.firotour.cz/robots.txt"]:
    try:
        r = requests.get(u, timeout=20); print(u, r.status_code)
    except Exception as e:
        print(u, "ERR", repr(e)[:400])
PY
echo "================ KOALA"
python3 .github/probe-fk/koala.py
