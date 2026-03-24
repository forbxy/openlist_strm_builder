# OpenList STRM Builder

一个简单python脚本，用来生成openlist strm，仅依赖requests

## 使用方法

```bash
# 安装依赖
pip install -r requirements.txt

# 生成默认配置文件，生成的默认配置文件中有详细的配置项说明
python main.py --generate-config config.py

# 编辑 config.py 后运行
python main.py config.py
```

## 配置项说明

| 配置项 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `server` | 是 | - | OpenList 服务器地址，如 `http://192.168.1.100:5244` |
| `username` | 是 | - | 登录用户名 |
| `password` | 是 | - | 登录密码 |
| `openlist_paths` | 是 | - | 存储路径列表，逗号隔开，路径必须以 `/` 开头 |
| `strm_path` | 是 | - | STRM 本地存储路径，必须是绝对路径 |
| `refresh_paths` | 否 | 空 | 生成前先刷新的路径列表，逗号隔开 |
| `strm_format` | 否 | `http` | STRM 内容格式，可选 `http` / `webdav` / `kodi_webdav` / `kodi_webdav_noauth` |
| `bluray_strm` | 否 | `False` | 蓝光文件夹 STRM，识别到 BDMV/index.bdmv 时以目录名生成 STRM，内容始终使用 `kodi_webdav` 格式 |
| `infuse_compat` | 否 | `False` | 兼容 Infuse，STRM URL 末尾追加 `&type=f.{扩展名}`，仅 `http` 格式时生效 |
| `video_extensions` | 否 | 内置视频格式 | 需要生成 STRM 的文件扩展名列表 |
| `download_extensions` | 否 | 内置字幕格式 | 需要直接下载的文件扩展名列表 |
| `verify_strm` | 否 | `False` | 校验已生成的 STRM，不一致则更新 |
| `verify_download` | 否 | `False` | 校验已下载的文件，不一致则重新下载 |
| `encode_illegal_chars` | 否 | `True` | 自动 URL 编码文件名中的非法字符 |
| `delete_orphaned` | 否 | `False` | 删除服务器不存在或不应生成的本地文件，清理空目录 |
| `threads` | 否 | `4` | 并发线程数 |

## STRM 格式

| 格式 | 内容 |
|---|---|
| `http` | `{server}/d/{编码路径}?sign={签名}` |
| `webdav` | `http(s)://用户名:密码@ip:port/dav/{编码路径}` |
| `kodi_webdav` | `dav(s)://用户名:密码@ip:port/dav/{编码路径}` |
| `kodi_webdav_noauth` | `dav(s)://ip:port/dav/{编码路径}`（需匿名访问或 Kodi 已挂载） |

## 目录与文件名规则

- 本地路径 = `strm_path` + 文件在 OpenList 中的绝对路径
- STRM 文件名：`{原文件名不含扩展名}.strm`
- 下载文件名：保持原文件名不变

## 单实例保护

脚本运行时会自动获取文件锁，确保同一时间只有一个实例在运行。如果检测到已有实例在运行，会提示并退出。适配 Windows、Linux、macOS。

## 作者本人的用法
- openlist添加存储，并将换成过期时间设的极大，比如525600分钟(一年)  
- refresh_paths中添加一两个需要动态刷新的目录，这些目录每次生成的时候都会调用openlist的刷新接口  
- 将脚本用定时工具拉起，比如cron什么的，设置半小时或一小时执行一次，更短的间隔也可以但没必要吧~ 

## 提醒
- ！！！115对固定时间内访问文件夹的数量有限制，不要一个电影一个文件夹，很容易被风控  
- 使用`kodi_webdav`或`kodi_webdav_noauth`格式在kodi中无需下载字幕，kodi播放时会自己去openlist下载字幕