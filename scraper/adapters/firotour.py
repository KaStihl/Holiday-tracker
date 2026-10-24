"""Firo-tour (firotour.sk / firotour.cz) – search links only.

From GitHub runners (2026-10-24) both hosts fail TLS certificate verification (SSLCertVerificationError);
we do not switch verification off, so nothing is fetched."""

NAME = "Firo-tour"
HOME = "https://www.firotour.sk"
DEEPLINK_ONLY = True


def deeplinks(cfg):
    return [
        {"transport": "flight", "label": "Firo-tour – letné zájazdy z Bratislavy (vyhľadávanie na webe)", "url": HOME + "/"},
        {"transport": "flight", "label": "Firo-tour CZ", "url": "https://www.firotour.cz/"},
    ]


def search(cfg):
    return []
