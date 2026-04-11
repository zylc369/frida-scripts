# 需求-frida可视化操作和管理-v3

## 新需求1：打开GUI界面的前提 - 需要改造

### 之前的需求
之前的需求：`frida server在android设备上启动成功。`。当前已经实现了这个需求。


### 需求描述
**之前的需求**对于GUI我现在认为是没有必要的，新逻辑：
1. 先启动GUI。
2. 如果没有检测到Android设备，显示错误信息以及提供重试按钮。如果检测到多个Android设备，显示多个设备让用户选择。如果只检测到一个设备，立即对这个设备启动frida server。
3. 在android设备上启动frida server（复用这个逻辑）：
    - 启动失败：提醒错误信息，提供重试按钮。
    - 启动成功：按照之前的逻辑执行、渲染UI。
4. GUI提供切换Android设备的交互。


**新需求1围绕着调整GUI启动时候的逻辑顺序。**


## 新需求2：允许切换多个Android设备
- 显示Android设备切换交互，即使检测到一个Android设备也要显示这样的交互。
- 提供刷新按钮，能够手动刷新当前设备连接的Android设备列表。


### 切换多个android设备
- 切换到新的设备后，之前的设备如果已经启动frida server，不要断联。
- 切换到新的设备后，如果当前设备是启动frida server的状态，则刷新app列表，刷新出错需要提示错误信息。
- 切换到新的设备后，如果当前设备没有启动frida server，需要手动启动。


### 刷新后如果之前连接的android设备不存在
清理这个连接的设备的资源，但是要注意，因为这个设备已经断联，所以adb相关的操作应该是有问题的，要兼容这个情况。


### 根据需求2升级代码
- 需求2核心诉求是允许同时在多个android设备上启动frida server，操作多个android设备上面的进程，这就需要**在逻辑上复用，在数据上隔离**。创建一个frida_client.py里面创建FridaClient类，所有对frida的操作挪到这个类中，每个启动frida server的android设备创建一个FridaClient类实例，每个实例存储特定android设备的数据，操作特定android设备。
- 之前APP启动的时候指定的日志路径是`~/bw-frida/frida-target-app.log`，要改成`~/bw-frida/frida-[android 设备ID]-app.log`这个路径。即，不同设备的app启动日志做隔离。


**我认为这是最好的架构设计。**


### 添加FridaClient类实例管理器，统一管理所有的实例
- 创建frida_client_manager.py，里面创建FridaClientManager类，这个类必须是全局单例，线程安全。
- FridaClientManager可以创建新的FridaClient，可以关闭单个FridaClient，可以关闭所有的FridaClient。
- FridaClientManager可以根据android device id获取FridaClient，操作某个特定的android设备。


### 进程退出、关闭
因为现在允许连接多个android设备，进程退出、关闭要清理所有android设备的资源，调用FridaClientManager里面的函数关闭所有FridaClient。


## GUI设计

我不会设计GUI，你帮我设计一个交互友好的GUI，谢谢！


## 必须遵守的规则
- 必须有良好的抽象。
- 必须有良好的复用。
- 类似逻辑禁止写多遍。
- 代码做好边界条件检查。
- 要有良好的日志，帮助排查问题。
- GUI操作要有良好的提示，帮助用户感知运行结果。