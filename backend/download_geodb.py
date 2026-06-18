#!/usr/bin/env python3
"""
GeoIP 数据库下载工具

从 MaxMind 下载 GeoLite2-City.mmdb（免费离线 IP 归属库）。
需要注册 MaxMind 账号获取 License Key。

用法:
    python download_geodb.py [--license-key YOUR_KEY]

环境变量:
    MAXMIND_LICENSE_KEY=your_key_here

下载文件保存到:
    backend/data/GeoLite2-City.mmdb
"""
import argparse
import os
import sys
import zipfile
import io
from pathlib import Path

try:
    import httpx
except ImportError:
    print("需要 httpx: pip install httpx")
    sys.exit(1)

_DATA_DIR = Path(__file__).parent / "data"
_DB_PATH = _DATA_DIR / "GeoLite2-City.mmdb"

DOWNLOAD_URL = (
    "https://download.maxmind.com/app/geoip_download"
    "?edition_id=GeoLite2-City&license_key={key}&suffix=tar.gz"
)


def download(license_key: str) -> bool:
    """下载并解压 GeoLite2-City.mmdb"""
    url = DOWNLOAD_URL.format(key=license_key)
    print(f"[下载] {url[:60]}...")

    try:
        resp = httpx.get(url, follow_redirects=True, timeout=120)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"[失败] 下载失败: {e}")
        print("提示：免费注册 https://www.maxmind.com/en/geolite2/signup 获取 License Key")
        return False

    # 解压 tar.gz 中的 .mmdb 文件
    import tarfile
    try:
        with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith(".mmdb"):
                    _DATA_DIR.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(member) as src, open(_DB_PATH, "wb") as dst:
                        dst.write(src.read())
                    print(f"[完成] {_DB_PATH} ({_DB_PATH.stat().st_size / 1024 / 1024:.1f} MB)")
                    return True
        print("[失败] tar.gz 中未找到 .mmdb 文件")
        return False
    except Exception as e:
        print(f"[失败] 解压失败: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="下载 MaxMind GeoLite2-City.mmdb")
    parser.add_argument("--license-key", type=str, default=os.getenv("MAXMIND_LICENSE_KEY", ""))
    args = parser.parse_args()

    if not args.license_key:
        print("需要 MaxMind License Key。")
        print("1. 免费注册: https://www.maxmind.com/en/geolite2/signup")
        print("2. 登录后在 My Account → License Keys 生成 Key")
        print("3. 运行: python download_geodb.py --license-key YOUR_KEY")
        print("   或设置环境变量: set MAXMIND_LICENSE_KEY=YOUR_KEY")
        sys.exit(1)

    download(args.license_key)
