# 需求-frida可视化操作和管理

## 需求1：如果有多个android设备连接，添加添加交互

如果有多个android设备连接，添加添加交互。通过`adb devices`可以知道有多少个设备连接了当前电脑。



交互方式：显示一个连接的android设备列表，通过上下键选择要连接的设备，回车确定选择设备。



## 需求2：start-frida.py支持GUI模式

### 打开GUI界面的前提

frida server在android设备上启动成功。



### 新增参数

新增`--gui`参数：可选，当满足GUI界面打开的前提以及指定了这个参数后，打开一个GUI界面。显示：

- 基本信息区域：
  - 连接的设备ID。
  - 监听的android上的tcp端口号。
  - 当前设备的端口号。
  - 在android上运行的frida server的路径。
- APP列表区域：
  - 显示所有安装的APP列表，正在运行的APP放到前面。
  - 允许通过包名或APP名搜索。
  - 正在运行的APP后面添加`kill`按钮，点击后调用`frida-kill -H 127.0.0.1:[主机上监听的端口号] [APP PID]`，关闭APP进程。
  - 没有运行的APP后面添加启动按钮，点击后能够通过frida命令启动APP。启动APP，带上HOOK脚本列表。



### GUI代码

GUI代码存放到`python-scripts`下单独的文件夹中，即，归类存放。



### GUI设计

我不会设计GUI，你帮我设计一个交互友好的GUI，谢谢！