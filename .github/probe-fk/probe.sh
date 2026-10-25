#!/usr/bin/env bash
# TEMPORARY diagnostics for Firo-tour TLS and Koala. Delete when done.
set +e
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 dovolenka-tracker/1.0 (+https://github.com/KaStihl/Holiday-tracker)"
echo "================ FIRO plain-http redirects (headers only)"
for u in http://www.firotour.sk/ http://firotour.sk/ http://www.firotour.cz/; do
  echo "--- $u"; curl -sS -A "$UA" -o /dev/null -D - --max-time 20 "$u" | grep -iE "^(HTTP|location|server)"; sleep 2
done
echo "================ FIRO alternate domains (verified TLS)"
for h in www.firotravel.sk firotravel.sk www.firo-travel.sk www.firotravel.cz www.firo-tour.cz www.firo.sk; do
  echo "--- $h"; getent hosts $h | head -2
  curl -sS -A "$UA" -o /dev/null -D - --max-time 20 "https://$h/" 2>&1 | grep -iE "^(HTTP|location|curl)"
  echo | timeout 15 openssl s_client -connect $h:443 -servername $h 2>/dev/null | openssl x509 -noout -subject -enddate -ext subjectAltName 2>/dev/null | head -4
  sleep 2
done
getent hosts www.firotour.sk firotour.sk www.firotour.cz
echo "================ KOALA"
python3 .github/probe-fk/koala.py
