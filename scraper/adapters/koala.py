"""CK Koala Tours (koala.sk; ckkoala.sk does not resolve) – search links only.

Part of the TIP travel group (same MagicWare platform, same chat/backend); its robots.txt disallows every
search filter (?date=, ?destinationId=, &transportationId=, …) and the home page is a JS shell (no links)."""

NAME = "Koala Tours"
HOME = "https://koala.sk"
DEEPLINK_ONLY = True


def deeplinks(cfg):
    return [{"transport": "flight", "label": "Koala Tours – ponuka zájazdov (vyhľadávanie na webe)", "url": HOME + "/"}]


def search(cfg):
    return []
