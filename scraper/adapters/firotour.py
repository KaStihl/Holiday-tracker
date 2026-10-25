"""Firo-tour (firotour.sk / firotour.cz) – search links only, because neither host has a valid TLS certificate.

Diagnosed from GitHub runners on 2026-10-25 (openssl s_client -servername …, curl, python requests):
 - www.firotour.sk / firotour.sk (148.251.66.86, nginx/1.22.1): the chain itself is complete and valid
   (Let's Encrypt YE1 -> ISRG Root YE -> ISRG Root X2 -> X1), but the leaf is CN=mobile.sonic-labs.net with
   SAN DNS:mobile.sonic-labs.net only -> "Hostname mismatch, certificate is not valid for 'www.firotour.sk'".
   The server hands out another site's default certificate (no TLS vhost for firotour.sk). Plain
   http://www.firotour.sk/ answers 200 without redirecting to https.
 - www.firotour.cz (185.219.170.113, Microsoft-IIS/10.0; http redirects to https) and the same server's
   firotravel.sk / firo-travel.sk / firo-tour.cz aliases: the leaf CN=www.firotravel.cz (SAN covers all Firo
   domains, issuer Let's Encrypt R13) expired on 2025-12-15 -> "certificate has expired".
   www.firotravel.cz (178.238.43.210) timed out.
Neither is an incomplete chain (which could be fixed by bundling the missing intermediate); a hostname mismatch
and an expired certificate are exactly what verification is meant to reject, and falling back to plain http
would only hide the problem. So nothing is fetched until Firo fixes its certificates – then re-check robots.txt
and the terms and build the adapter. Note for users: the links below show a browser certificate warning too.
"""

NAME = "Firo-tour"
HOME = "https://www.firotour.sk"
DEEPLINK_ONLY = True


def deeplinks(cfg):
    return [
        {"transport": "flight", "label": "Firo-tour – letné zájazdy z Bratislavy (web má neplatný TLS certifikát)",
         "url": HOME + "/"},
        {"transport": "flight", "label": "Firo-tour CZ (certifikát webu vypršal 15. 12. 2025)",
         "url": "https://www.firotour.cz/"},
    ]


def search(cfg):
    return []
