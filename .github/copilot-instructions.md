#### 需求  
- strm构建：python脚本接收传入python文件配置文件，动态import进来，登陆后遍历指定的openlist存储路径，将openlist存储路径下的每个要生成strm的文件生成对应的strm文件，将要直接下载的文件下载到对应的位置，strm或直接下载的文件存储路径为配置文件中指定的strm存储路径。
- 生成默认配置：生成带注释的默认配置文件，注释说明每个配置项的作用和默认值。生成的默认配置文件视频格式列表和直接下载的文件格式列表为脚本内置的所有视频格式和字幕格式。

##### 配置文件可选项包括：
- openlist服务器地址(无默认必须指定)
- 用户名(无默认必须指定)
- 密码(无默认必须指定)
- openlist存储路径列表(无默认必须指定，支持多个路径，逗号隔开，路径必须以/开头，如存在非/开头的路径，报错退出)
- 生成前先刷新的openlist存储路径列表(默认空，即不刷新，指定后只刷新列表中的路径，支持多个路径，逗号隔开)
- strm存储路径(无默认，必须指定，必须是绝对路径，如非绝对路径，报错退出)
- strm文件内容格式(可选webdav或http，默认http)
- 生成kodi蓝光文件夹strm(开启后当识别到当前目录下有bdmv目录，且bdmv目录下有index.bdmv，则使用当前目录名作为strm的名字，strm内容为index.bdmv的kodi_webdav路径(无论文件内容格式设置的是什么)，且不再继续遍历当前文件夹或子文件夹，默认关闭)
- 兼容infuse(当strm文件内容格式为http时可选，开启后生成的strm内容后面多加个 type=f.格式 的http参数，例如http://server/d/xxx.mkv?sign=xxx&type=f.mp4，默认关闭)
- 生成strm的文件格式列表（默认为脚本内置的所有视频格式）
- 直接下载的文件格式列表（默认为脚本内置的所有字幕格式）
- 校验已生成的strm(开启时，如果已生成的strm和目标strm不一致，则更新该文件，默认关闭，关闭时跳过本地已存在的strm文件)
- 校验已下载文件(开启时，如果已下载文件和目标文件不一致，则更新该文件，默认关闭，关闭时跳过本地已存在的文件)
- 自动编码非法字符(开启时，文件或文件夹名中的windows-linux-osx中的非法字符会被url编码并替换(只替换非法字符)，默认开启，关闭时非法字符将保留在文件名中，可能导致生成strm失败或下载失败)
- 删除服务器不存在或不应该生成strm或下载的但本地还存在的文件，如果清理后目录为空则删除该目录，如果服务器没有正常返回则不执行该选项，默认关闭
- 线程数(默认4)

##### 目录格式
- 下载的文件或strm文件最终目录：strm存储路径+文件在openlist中的绝对路径（不包含文件名），例如配置文件中strm存储路径为/mnt/strm，openlist中有个文件路径为/openwrt/video/xxx.mkv，则最终生成的strm文件或下载的文件目录为/mnt/strm/openwrt/video/，如果该目录不存在则创建该目录

##### 文件名格式：
- strm:{文件名（不编码不包含扩展名）}.strm  
- 直接下载的文件:{文件名（不编码包含扩展名）}  

##### strm文件内容格式：
- http: {openlist服务器地址}/d/{视频文件的相对路径，需编码}?sign={签名}
- webdav: http(s)://{用户名:密码}@ip:port/dav/{视频文件的相对路径，需编码}
- kodi_webdav:dav(s)://{用户名:密码}@ip:port/dav/{视频文件的相对路径，需编码}
- kodi_webdav_noauth:dav(s)://ip:port/dav/{视频文件的相对路径，需编码},这种格式需要服务器支持匿名访问，或kodi中挂载该openlist，挂载后，kodi会在访问时自动带上用户名和密码

#### 其他说明
- 新增或变更python依赖时，必须更新requirements.txt文件
- 需生成readme.md文件，说明脚本的功能、使用方法、配置项说明等,readme应简洁明了，当需求变更时，需更新readme.md文件，
- 需实现单例模型，同时在确保只有一个这个脚本的实例在运行，如果检测到已有实例在运行，则提示用户并退出，适配windows、linux、osx系统

#### 以下为参考文档  
- openlist api文档： https://fox.oplist.org.cn/  
- openlist 源码：workspace里的OpenList文件夹  
- strm格式举例：http://127.0.0.1:5244/d/115_0906/NAS/video/%5B%E5%A6%99%E6%83%B3%E5%A4%A9%E5%BC%80%201985%5D%5B4K%20CC%E6%A0%87%E5%87%86%E6%94%B6%E8%97%8F%20DIY%20%E4%BA%AC%E8%AF%91%E5%9B%BD%E8%AF%ADDD.2.0%20%E7%AE%80%E7%B9%81%2B%E5%8F%8C%E8%AF%AD%E7%89%B9%E6%95%88%E5%AD%97%E5%B9%95%5D%5BDolby%20Vision%20HDR10%20DTS-HDMA%202.0%5D%5BLINMENG%40CHDBits%5D%5B91.75G%5D%7BTMDB%3D68%7D.iso?sign=B9Gz4JtezyfR-3-Vl62emPv-WBKMCL-N3wUfNlcfbns=:0

