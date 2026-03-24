#!/usr/bin/env python3
"""OpenList STRM Builder - 将 OpenList 存储路径下的视频文件生成对应的 STRM 文件"""

import atexit
import importlib.util
import os
import re
import sys
import argparse
import logging
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# 默认视频格式
VIDEO_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".wmv", ".flv", ".mov", ".mpg", ".mpeg",
    ".ts", ".m2ts", ".vob", ".iso", ".m4v", ".3gp", ".rmvb", ".rm",
    ".webm", ".ogv", ".divx", ".asf", ".f4v", ".tp",
}

# 默认字幕格式
SUBTITLE_EXTENSIONS = {
    ".srt", ".ass", ".ssa", ".sub", ".idx", ".sup", ".vtt", ".smi",
}


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

# 配置项名称与默认值
CONFIG_KEYS = {
    "server": None,
    "username": None,
    "password": None,
    "openlist_paths": None,
    "refresh_paths": "",
    "strm_path": None,
    "strm_format": "http",
    "bluray_strm": False,
    "infuse_compat": False,
    "video_extensions": [],
    "download_extensions": [],
    "verify_strm": False,
    "verify_download": False,
    "encode_illegal_chars": True,
    "delete_orphaned": False,
    "threads": 4,
}


def load_config(config_path: str) -> dict:
    """动态 import 一个 Python 配置文件，将模块级变量读入 dict"""
    path = os.path.abspath(config_path)
    spec = importlib.util.spec_from_file_location("_user_config", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cfg = {}
    for key, default in CONFIG_KEYS.items():
        cfg[key] = getattr(mod, key, default)
    return cfg


DEFAULT_CONFIG_CONTENT = '''\
# OpenList STRM Builder 配置文件
# 使用方法: python main.py config.py

# openlist 服务器地址，必须指定，例如 "http://192.168.1.100:5244"
server = ""

# 登录用户名，必须指定
username = ""

# 登录密码，必须指定
password = ""

# openlist 存储路径列表，必须指定，支持多个路径用逗号隔开，路径必须以 / 开头
# 示例: "/path1,/path2"
openlist_paths = ""

# 生成或下载前先执行刷新的 openlist 存储路径列表，用逗号隔开，默认为空即不刷新
# 指定后只刷新列表中的路径，例如 "/path1,/path2"
refresh_paths = ""

# strm 文件本地存储路径，必须指定，例如 "/mnt/strm" 或 r"D:\\strm"
strm_path = ""

# strm 文件内容格式，可选 "http" / "webdav" / "kodi_webdav" / "kodi_webdav_noauth"，默认 "http"
#   http:              {server}/d/{编码路径}?sign={签名}
#   webdav:            http(s)://用户名:密码@ip:port/dav/{编码路径}
#   kodi_webdav:       dav(s)://用户名:密码@ip:port/dav/{编码路径}
#   kodi_webdav_noauth: dav(s)://ip:port/dav/{编码路径} (需openlist开启匿名访问(不推荐)或 kodi 已挂载)
strm_format = "http"

# 生成 Kodi 蓝光文件夹 STRM，默认 False
# 开启后，当识别到目录下有 BDMV/index.bdmv 时，使用该目录名作为 STRM 文件名，
# STRM 内容始终为 index.bdmv 的 kodi_webdav 路径（无论 strm_format 设置为何），
# 且不再继续遍历该目录的子文件夹
bluray_strm = False

# 兼容 Infuse，默认 False
# 仅在 strm_format 为 http 时生效
# 开启后 strm 内容 URL 末尾追加 &type=f.{扩展名}，例如:
#   http://server/d/xxx.mkv?sign=xxx&type=f.mkv
infuse_compat = False

# 需要生成 strm 的文件扩展名列表，为空则使用内置默认视频格式
video_extensions = [
    ".mkv", ".mp4", ".avi", ".wmv", ".flv", ".mov", ".mpg", ".mpeg",
    ".ts", ".m2ts", ".vob", ".iso", ".m4v", ".3gp", ".rmvb", ".rm",
    ".webm", ".ogv", ".divx", ".asf", ".f4v", ".tp",
]

# 需要直接下载的文件扩展名列表，为空则使用内置默认字幕格式
download_extensions = [
    ".srt", ".ass", ".ssa", ".sub", ".idx", ".sup", ".vtt", ".smi",
]

# 校验已生成的 strm 文件：开启后检查现有 strm 内容是否与目标一致，不一致则更新
# 关闭时跳过已存在的 strm 文件，默认 False
verify_strm = False

# 校验已下载的文件：开启后检查本地文件大小是否与远程一致，不一致则重新下载
# 关闭时跳过已存在的文件，默认 False
verify_download = False

# 自动编码非法字符：开启后文件/文件夹名中的在Windows/Linux/macOS中非法的字符会被以URL编码替换
# 关闭时保留原始字符，如果有非法字符，可能导致生成 strm 或下载失败，默认开启
encode_illegal_chars = True

# 删除远程服务器不存在或不应生成 strm/下载但本地仍存在的文件，默认 False
delete_orphaned = False

# 并发线程数，默认 4
threads = 4
'''


def generate_default_config(output_path: str):
    """生成带注释的默认 Python 配置文件"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(DEFAULT_CONFIG_CONTENT)
    log.info("默认配置已生成: %s", output_path)


# ---------------------------------------------------------------------------
# OpenList API 客户端
# ---------------------------------------------------------------------------

class OpenListClient:
    """OpenList / AList API 客户端"""

    def __init__(self, server: str, username: str, password: str):
        self.server = server.rstrip("/")
        self.username = username
        self.password = password
        self.token = None
        self.session = requests.Session()

    def login(self):
        url = f"{self.server}/api/auth/login"
        resp = self.session.post(url, json={
            "username": self.username,
            "password": self.password,
        })
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            raise RuntimeError(f"登录失败: {data.get('message', '未知错误')}")
        self.token = data["data"]["token"]
        self.session.headers["Authorization"] = self.token
        log.info("登录成功")

    def list_dir(self, path: str, *, refresh: bool = False) -> dict:
        """列出目录内容，返回完整 data 字段"""
        url = f"{self.server}/api/fs/list"
        resp = self.session.post(url, json={
            "path": path,
            "page": 1,
            "per_page": 0,
            "refresh": refresh,
        })
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            raise RuntimeError(
                f"列出目录失败 [{path}]: {data.get('message', '未知错误')}"
            )
        return data["data"]

    def walk(self, root: str, *, bluray_strm: bool = False) -> list:
        """递归遍历目录，返回所有文件信息列表"""
        result = []
        self._walk(root, result, bluray_strm=bluray_strm)
        return result

    def _walk(self, path: str, result: list, *, bluray_strm: bool = False):
        data = self.list_dir(path)
        content = data.get("content") or []

        # 蓝光文件夹检测：当前目录包含 BDMV/index.bdmv 时生成蓝光 STRM
        if bluray_strm:
            dir_items = {item["name"].lower(): item["name"] for item in content if item.get("is_dir")}
            if "bdmv" in dir_items:
                bdmv_name = dir_items["bdmv"]
                bdmv_path = f"{path.rstrip('/')}/{bdmv_name}"
                try:
                    bdmv_data = self.list_dir(bdmv_path)
                    bdmv_content = bdmv_data.get("content") or []
                    for bdmv_item in bdmv_content:
                        if bdmv_item["name"].lower() == "index.bdmv" and not bdmv_item.get("is_dir"):
                            index_path = f"{bdmv_path}/{bdmv_item['name']}"
                            result.append({
                                "name": PurePosixPath(path).name,
                                "path": index_path,
                                "size": bdmv_item.get("size", 0),
                                "sign": bdmv_item.get("sign", ""),
                                "is_bluray": True,
                                "bluray_dir": path,
                            })
                            return  # 不再继续遍历子文件夹
                except Exception:
                    pass  # BDMV 目录列出失败，继续正常遍历

        for item in content:
            item_path = f"{path.rstrip('/')}/{item['name']}"
            if item.get("is_dir"):
                self._walk(item_path, result, bluray_strm=bluray_strm)
            else:
                result.append({
                    "name": item["name"],
                    "path": item_path,
                    "size": item.get("size", 0),
                    "sign": item.get("sign", ""),
                })

    def download_file(self, remote_path: str, sign: str) -> bytes:
        """通过 /d/ 端点下载文件"""
        encoded_path = quote(remote_path.lstrip("/"), safe="/")
        url = f"{self.server}/d/{encoded_path}?sign={sign}"
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.content


# ---------------------------------------------------------------------------
# STRM 构建器
# ---------------------------------------------------------------------------

class StrmBuilder:

    def __init__(self, config: dict):
        self.server = config["server"].rstrip("/")
        self.username = config["username"]
        self.password = config["password"]
        raw_paths = config.get("openlist_paths", "")
        self.openlist_paths = [
            p if p == "/" else p.rstrip("/")
            for p in (s.strip() for s in raw_paths.split(","))
            if p
        ]
        for p in self.openlist_paths:
            if not p.startswith("/"):
                log.error("openlist 路径必须以 / 开头: '%s'", p)
                sys.exit(1)
        self.strm_path = Path(config["strm_path"])
        if not self.strm_path.is_absolute():
            log.error("strm_path 必须是绝对路径: '%s'", config["strm_path"])
            sys.exit(1)
        self.strm_format = config.get("strm_format", "http")
        self.bluray_strm = config.get("bluray_strm", False)

        self.infuse_compat = config.get("infuse_compat", False)
        if self.infuse_compat and self.strm_format != "http":
            log.warning(
                "infuse_compat 仅在 strm_format 为 http 时有效，已忽略"
            )
            self.infuse_compat = False

        self.video_exts = (
            set(e.lower() for e in config.get("video_extensions") or [])
            or VIDEO_EXTENSIONS
        )
        self.download_exts = (
            set(e.lower() for e in config.get("download_extensions") or [])
            or SUBTITLE_EXTENSIONS
        )
        raw_refresh = config.get("refresh_paths", "")
        self.refresh_paths = [
            p.strip() for p in raw_refresh.split(",") if p.strip()
        ]
        self.verify_strm = config.get("verify_strm", False)
        self.verify_download = config.get("verify_download", False)
        self.encode_illegal_chars = config.get("encode_illegal_chars", True)
        self.delete_orphaned = config.get("delete_orphaned", False)
        self.threads = config.get("threads", 4)

        self.client = OpenListClient(
            self.server, config["username"], config["password"]
        )
        self.stats = {
            "strm_created": 0,
            "strm_updated": 0,
            "strm_skipped": 0,
            "downloaded": 0,
            "download_updated": 0,
            "download_skipped": 0,
            "deleted": 0,
            "errors": 0,
        }

    # ------------------------------------------------------------------

    def build(self):
        self.client.login()

        if self.refresh_paths:
            for rp in self.refresh_paths:
                log.info("刷新远程路径: %s", rp)
                self.client.list_dir(rp, refresh=True)

        remote_files = []
        walk_success = True
        for op in self.openlist_paths:
            log.info("开始遍历远程目录: %s", op)
            try:
                remote_files.extend(self.client.walk(op, bluray_strm=self.bluray_strm))
            except Exception as e:
                log.error("遍历远程目录失败 [%s]: %s", op, e)
                walk_success = False
        log.info("共发现 %d 个文件", len(remote_files))

        strm_files = []
        dl_files = []
        for f in remote_files:
            if f.get("is_bluray"):
                strm_files.append(f)
                continue
            ext = os.path.splitext(f["name"])[1].lower()
            if ext in self.video_exts:
                strm_files.append(f)
            elif ext in self.download_exts:
                dl_files.append(f)

        log.info("视频文件: %d, 下载文件: %d", len(strm_files), len(dl_files))

        # 记录远程文件对应的本地路径，用于清理孤立文件
        remote_local_paths: set[str] = set()

        with ThreadPoolExecutor(max_workers=self.threads) as pool:
            futures = []
            for f in strm_files:
                local = self._local_path(f["path"], is_strm=True, bluray_dir=f.get("bluray_dir"))
                remote_local_paths.add(os.path.normpath(local))
                futures.append(pool.submit(self._process_strm, f, local))

            for f in dl_files:
                local = self._local_path(f["path"], is_strm=False)
                remote_local_paths.add(os.path.normpath(local))
                futures.append(pool.submit(self._process_download, f, local))

            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    log.error("处理文件出错: %s", e)
                    self.stats["errors"] += 1

        if self.delete_orphaned and walk_success:
            self._cleanup_orphaned(remote_local_paths)
        elif self.delete_orphaned and not walk_success:
            log.warning("服务器未正常返回，跳过孤立文件清理")

        self._print_stats()

    # ------------------------------------------------------------------
    # 路径 / URL 工具
    # ------------------------------------------------------------------

    # Windows/Linux/macOS 文件名非法字符
    _ILLEGAL_CHARS_RE = re.compile(r'[\\/:*?"<>|]')

    def _sanitize_name(self, name: str) -> str:
        """将文件/文件夹名中的非法字符 URL 编码"""
        if not self.encode_illegal_chars:
            return name
        return self._ILLEGAL_CHARS_RE.sub(
            lambda m: quote(m.group(0), safe=""), name
        )

    def _local_path(self, remote_path: str, *, is_strm: bool, bluray_dir: str = None) -> Path:
        """将远程路径映射到本地路径: strm_path + 文件在openlist中的绝对路径"""
        if bluray_dir:
            # 蓝光目录: strm 文件以目录名命名，放在目录的父级
            parts = PurePosixPath(bluray_dir).parts[1:]
            sanitized = [self._sanitize_name(p) for p in parts]
            parent_parts = sanitized[:-1]
            dir_name = sanitized[-1] if sanitized else self._sanitize_name(PurePosixPath(bluray_dir).name)
            parent_rel = os.path.join(*parent_parts) if parent_parts else ""
            return self.strm_path / parent_rel / f"{dir_name}.strm"
        parts = PurePosixPath(remote_path).parts[1:]  # 去掉开头的 '/'
        sanitized = [self._sanitize_name(p) for p in parts]
        rel = os.path.join(*sanitized) if sanitized else ""
        if is_strm:
            stem = os.path.splitext(rel)[0]
            return self.strm_path / f"{stem}.strm"
        return self.strm_path / rel

    def _strm_content(self, remote_path: str, sign: str, *, force_kodi_webdav: bool = False) -> str:
        encoded = quote(remote_path.lstrip("/"), safe="/")
        if force_kodi_webdav:
            from urllib.parse import urlparse
            parsed = urlparse(self.server)
            scheme = "davs" if parsed.scheme == "https" else "dav"
            userinfo = quote(self.username, safe="") + ":" + quote(self.password, safe="")
            return f"{scheme}://{userinfo}@{parsed.netloc}/dav/{encoded}"
        if self.strm_format == "webdav":
            from urllib.parse import urlparse
            parsed = urlparse(self.server)
            userinfo = quote(self.username, safe="") + ":" + quote(self.password, safe="")
            return f"{parsed.scheme}://{userinfo}@{parsed.netloc}/dav/{encoded}"
        if self.strm_format == "kodi_webdav":
            from urllib.parse import urlparse
            parsed = urlparse(self.server)
            scheme = "davs" if parsed.scheme == "https" else "dav"
            userinfo = quote(self.username, safe="") + ":" + quote(self.password, safe="")
            return f"{scheme}://{userinfo}@{parsed.netloc}/dav/{encoded}"
        if self.strm_format == "kodi_webdav_noauth":
            from urllib.parse import urlparse
            parsed = urlparse(self.server)
            scheme = "davs" if parsed.scheme == "https" else "dav"
            return f"{scheme}://{parsed.netloc}/dav/{encoded}"
        url = f"{self.server}/d/{encoded}?sign={sign}"
        if self.infuse_compat:
            ext = PurePosixPath(remote_path).suffix.lstrip(".")
            if ext:
                url += f"&type=f.{ext}"
        return url

    # ------------------------------------------------------------------
    # 文件处理
    # ------------------------------------------------------------------

    def _process_strm(self, finfo: dict, local: Path):
        content = self._strm_content(
            finfo["path"], finfo["sign"],
            force_kodi_webdav=bool(finfo.get("is_bluray")),
        )
        if local.exists():
            if not self.verify_strm:
                self.stats["strm_skipped"] += 1
                return
            if local.read_text(encoding="utf-8").strip() == content:
                self.stats["strm_skipped"] += 1
                return
            local.write_text(content, encoding="utf-8")
            log.info("更新 STRM: %s", local)
            self.stats["strm_updated"] += 1
        else:
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_text(content, encoding="utf-8")
            log.info("创建 STRM: %s", local)
            self.stats["strm_created"] += 1

    def _process_download(self, finfo: dict, local: Path):
        if local.exists():
            if not self.verify_download:
                self.stats["download_skipped"] += 1
                return
            if local.stat().st_size == finfo["size"]:
                self.stats["download_skipped"] += 1
                return
            local.parent.mkdir(parents=True, exist_ok=True)
            data = self.client.download_file(finfo["path"], finfo["sign"])
            local.write_bytes(data)
            log.info("更新下载: %s", local)
            self.stats["download_updated"] += 1
        else:
            local.parent.mkdir(parents=True, exist_ok=True)
            data = self.client.download_file(finfo["path"], finfo["sign"])
            local.write_bytes(data)
            log.info("下载: %s", local)
            self.stats["downloaded"] += 1

    # ------------------------------------------------------------------
    # 孤立文件清理
    # ------------------------------------------------------------------

    def _cleanup_orphaned(self, remote_local_paths: set[str]):
        """删除本地存在但远程不存在或不应生成的文件"""
        for root, _dirs, files in os.walk(self.strm_path):
            for fname in files:
                fpath = os.path.normpath(os.path.join(root, fname))
                if fpath not in remote_local_paths:
                    os.remove(fpath)
                    log.info("删除孤立文件: %s", fpath)
                    self.stats["deleted"] += 1

        # 自底向上清理空目录
        for root, dirs, files in os.walk(self.strm_path, topdown=False):
            for d in dirs:
                dpath = os.path.join(root, d)
                if not os.listdir(dpath):
                    os.rmdir(dpath)
                    log.info("删除空目录: %s", dpath)

    # ------------------------------------------------------------------

    def _print_stats(self):
        s = self.stats
        log.info("===== 完成 =====")
        log.info(
            "STRM  - 创建: %d, 更新: %d, 跳过: %d",
            s["strm_created"], s["strm_updated"], s["strm_skipped"],
        )
        log.info(
            "下载  - 创建: %d, 更新: %d, 跳过: %d",
            s["downloaded"], s["download_updated"], s["download_skipped"],
        )
        if self.delete_orphaned:
            log.info("删除孤立文件: %d", s["deleted"])
        if s["errors"]:
            log.warning("错误: %d", s["errors"])


# ---------------------------------------------------------------------------
# 单例锁
# ---------------------------------------------------------------------------

_lock_file = None


def _acquire_singleton_lock():
    """确保同一时间只有一个脚本实例在运行，适配 Windows / Linux / macOS"""
    global _lock_file
    lock_path = os.path.join(tempfile.gettempdir(), "openlist_strm_builder.lock")
    try:
        _lock_file = open(lock_path, "w", encoding="utf-8")
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, IOError):
        log.error("检测到另一个实例正在运行，退出")
        sys.exit(1)
    atexit.register(_release_singleton_lock)


def _release_singleton_lock():
    global _lock_file
    if _lock_file is None:
        return
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(_lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(_lock_file, fcntl.LOCK_UN)
    except (OSError, IOError):
        pass
    try:
        _lock_file.close()
    except (OSError, IOError):
        pass
    _lock_file = None


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="OpenList STRM Builder - 将 OpenList 存储的视频文件生成 STRM 文件",
    )
    parser.add_argument("config", nargs="?", help="Python 配置文件路径 (.py)")
    parser.add_argument(
        "--generate-config",
        metavar="PATH",
        help="生成默认 Python 配置文件到指定路径",
    )
    args = parser.parse_args()

    if args.generate_config:
        generate_default_config(args.generate_config)
        return

    if not args.config:
        parser.error("请指定配置文件路径，或使用 --generate-config 生成默认配置")

    _acquire_singleton_lock()

    config = load_config(args.config)

    for key in ("server", "username", "password", "openlist_paths", "strm_path"):
        if not config.get(key):
            log.error("配置项 '%s' 必须指定且不能为空", key)
            sys.exit(1)

    StrmBuilder(config).build()


if __name__ == "__main__":
    main()