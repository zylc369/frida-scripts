# 需求-android-frida启动脚本-v1

编写一键启动android上的frida-server的python启动脚本。



## 初始化python虚拟环境
检测启动脚本的目录下，是否存在`.venv-frida`这个python虚拟环境，如果不存在则需要先创建。创建失败则打印日志并终止执行。



## Step1: 安装frida依赖
判断requirements.txt中的依赖是否存在：
- 如果不存在：在虚拟环境中调用`pip3 install -r requirements.txt`安装依赖。安装失败则打印日志并终止执行。
- 如果存在：如果脚本指定了`--upgrade`参数，则调用`pip3 install -r requirements.txt`更新依赖，否则跳过这一步。



## Step2: 下载、安装frida server
1. 检查android设备是否连接，如果没有连接，则打印日志并终止执行。
2. 读取`~/mobile-arsenal/frida/install_record.json`中是否有安装记录： 
   1. 如果没有：则跳转到第3步。
   2. 如果有：
      1. 如果脚本指定了`--upgrade`参数，则执行第4步。
      2. 否则，根据`install_record.json`中记录的安装到android中的位置，通过`adb`命令检查是否存在，如果存在则跳过**下载、安装frida server**整个步骤，也不需要执行**安装frida server到android设备**这个步骤，直接执行**在android上运行frida-server**这个步骤。如果不存在，意味着`install_record.json`中的数据失效了，需要删除这条失效的数据，然后执行第3步。

3. 本地是否有已经下载的`frida-server-*-android-arm64`文件：
   1. 如果有：根据创建时间选一个最新的，返回这个解压后路径，安装到android的时候要用到它。返回它的路径，安装到android的时候要用到它。
   2. 如果没有：则跳转到第4步。

4. 下载android arm64架构的frida-server压缩包：调用`bunx @zylc369/bw-gh-release-fetch "https://github.com/frida/frida" "frida-server-*-android-arm64.*" -o ~/mobile-arsenal/frida/download/`下载android arm64架构的frida-server压缩包。下载失败则打印日志并终止执行，如果下载多个则打印日志并终止执行，下载成功且只下载一个则打印下载的压缩包路径。
5. 解压第4步下载的压缩包路径打印出来，解压到`~/mobile-arsenal/frida/download/`目录下，解压失败则打印日志并终止执行，否则要打印解压后的文件路径。返回这个解压后路径，安装到android的时候要用到它。



## Step3: 安装frida server到android设备
1. 检查是否有连接的android设备，如果没有则打印错误日志然后终止执行。
2. 如果有多台android设备链接，脚本参数没有指定`-s [设备ID]`，则打印错误日志然后终止执行。
   1. `-s`参数说明：` -s SERIAL                use device with given serial (overrides $ANDROID_SERIAL)`。通常通过adb命令检测是否有android设备连接，如果有多台设备，当前需要操作某一台安卓设备的时候，adb需要`-s`参数，用于知道要操作哪台设备。
3. frida server安装根目录：`/data/local/tmp`。
4. frida server安装路径：`/data/local/tmp/[随机6~8位数字加字母 - 目录]/[随机6~8位数字加字母 - frida server可执行文件]`。
   1. `[随机6~8位数字加字母 - 目录]`解释：为了防止被APP扫描运行环境的时候扫描到frida关键字，导致分析APP的时候出问题，所以随机命名目录。
   2. `[随机6~8位数字加字母 - frida server可执行文件]`解释：为了防止被APP扫描运行环境的时候扫描到frida关键字，导致分析APP的时候出问题，所以随机文件名。
5. 安装：
   1. 通过adb创建`/data/local/tmp/[随机6~8位数字加字母 - 目录]`路径。使用`mkdir -p`，需要使用创建父目录的命令避免目录创建失败。
   2. `adb push [下载、安装frida server返回的路径] [frida server安装路径产生的路径]`
   3. 如果安装失败，则打印日志并终止执行。
   4. 如果安装成功，则将android设备ID、安装路径记录到`install_record.json`，做安装记录持久化。



## Step4: 在android上运行frida-server

1. 获取要连接的android设备ID，获取失败则打印日志并终止执行。
2. 读取`~/mobile-arsenal/frida/install_record.json`，根据**android设备ID**这个key，获取**frida server安装路径产生的路径**。
3. 调用adb判断android设备上的**frida server安装路径产生的路径**是否存在，不存在则打印日志并终止执行。
4. 查找空闲android端口：根据`adb shell netstat -an | grep <端口号>`查看端口占用情况，端口从6655开始检查，如果端口被占用则+1，直到找到一个不占用的端口。
5. 运行frida：`adb shell /data/local/tmp/tox/woeruw -l 0.0.0.0:<第4步找到的端口号>`。
6. 查询空闲的主机端口：端口从6655开始检查，如果主机端口被占用则+1，直到找到一个不占用的端口。
7. android端口转发：`adb forward tcp:<第6步找到的主机端口号> tcp:<第4步找到的android端口号>`。
8. 在`install_record.json`中找到android设备ID对应的数据然后更新：
   1. hostTcpPort：`<第6步找到的主机端口号>`。
   2. androidTcpPort：`<第4步找到的android端口号>`。



### 记录`install_record.json`

文件位置：`~/mobile-arsenal/frida/install_record.json`。写入之前，要判断目录是否存在，不存在的话先要创建目录，否则文件新要写失败了。文件写入要加锁，避免并发问题导致文件格式被破坏。



**格式：**

```json
{
  "android设备ID": {
    "sourcePath": "[下载、安装frida server返回的路径]",
    "installPath": "[frida server安装路径产生的路径]",
    "hostTcpPort": [主机端口号],
    "androidTcpPort": [android端口号]
  }
}
```



## 脚本终止需要做资源清理

1. `adb forward --remove tcp:[主机端口号]`。

