"""
GeoIP 离线解析 — 使用 MaxMind GeoLite2 数据库

用法:
    from geoip import geoip_lookup
    result = geoip_lookup("8.8.8.8")  # {"province": "California", "city": "Mountain View"}
    result = geoip_lookup("192.168.1.1")  # None  (内网地址)

数据库文件: data/GeoLite2-City.mmdb
没有该文件时静默返回 None，不会影响业务。
"""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_GEO_READER = None
_DATA_DIR = Path(__file__).parent / "data"
_DB_PATH = _DATA_DIR / "GeoLite2-City.mmdb"

# 内网地址段 (RFC 1918 + loopback + link-local)
_PRIVATE_PREFIXES = (
    "10.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
    "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
    "172.30.", "172.31.", "192.168.", "127.", "169.254.",
)


def _is_private(ip: str) -> bool:
    return any(ip.startswith(p) for p in _PRIVATE_PREFIXES) or ip in ("::1", "0.0.0.0", "")


def _ensure_reader():
    global _GEO_READER
    if _GEO_READER is not None:
        return _GEO_READER
    if not _DB_PATH.exists():
        logger.info(f"GeoIP 数据库不存在: {_DB_PATH}，地区解析将返回空。")
        _GEO_READER = False
        return None
    try:
        import maxminddb
        _GEO_READER = maxminddb.open_database(str(_DB_PATH))
        logger.info(f"GeoIP 数据库已加载 ({_DB_PATH.name})")
        return _GEO_READER
    except ImportError:
        logger.warning("maxminddb 未安装，地区解析不可用。pip install maxminddb")
        _GEO_READER = False
        return None
    except Exception as e:
        logger.warning(f"GeoIP 数据库加载失败: {e}")
        _GEO_READER = False
        return None


def geoip_lookup(ip: str) -> dict | None:
    """查询 IP 归属地，返回 {"province": str, "city": str} 或 None"""
    if not ip or _is_private(ip):
        return None

    reader = _ensure_reader()
    if not reader:
        return None

    try:
        result = reader.get(ip)
        if not result:
            return None

        # MaxMind 返回结构: {"country": {...}, "subdivisions": [{...}], "city": {...}}
        province = ""
        city = ""
        subs = result.get("subdivisions", [])
        if subs:
            province = subs[0].get("names", {}).get("zh-CN", "") or subs[0].get("names", {}).get("en", "")
        if result.get("city"):
            city = result["city"].get("names", {}).get("zh-CN", "") or result["city"].get("names", {}).get("en", "")
        if not province:
            # fallback: 直接用 registered_country
            country = result.get("country", {}) or result.get("registered_country", {})
            province = country.get("names", {}).get("zh-CN", "") or country.get("names", {}).get("en", "")

        return {"province": province, "city": city}
    except Exception as e:
        logger.debug(f"GeoIP 查询失败 {ip}: {e}")
        return None


def close():
    """释放资源（应用退出时调用）"""
    global _GEO_READER
    if _GEO_READER and _GEO_READER is not False:
        try:
            _GEO_READER.close()
        except Exception:
            pass
    _GEO_READER = None
