"""跨 service 通用的小工具。下划线前缀表示 package-private。"""


def parse_cookies(cookies_str: str, domain: str = ".x.com") -> list[dict]:
    """把 'k1=v1; k2=v2' 字符串解析成 Playwright add_cookies 接受的字典列表。"""
    cookies: list[dict] = []
    for pair in cookies_str.split(";"):
        pair = pair.strip()
        if "=" not in pair:
            continue
        name, _, value = pair.partition("=")
        cookies.append({
            "name": name.strip(),
            "value": value.strip(),
            "domain": domain,
            "path": "/",
        })
    return cookies
