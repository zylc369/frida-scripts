# Frida Hook 开发经验总结

> 基于 OkHttp3 Hook 开发过程中的踩坑经验整理，目标是下次编写 Hook 代码时不再踩同样的坑。

本文档已拆分为按需加载的独立文件，AI 助手会根据任务场景自动读取对应文档：

| 文件 | 内容 | 适用场景 |
|------|------|---------|
| [01-核心原则.md](01-核心原则.md) | 4 条铁律 + 通用检查清单 | 编写任何 Hook 前**必读** |
| [02-Hook架构与模板.md](02-Hook架构与模板.md) | 主动/被动拦截策略、标准模板、拦截器链模式 | 编写 Java Hook 时 |
| [03-Java-Bridge陷阱.md](03-Java-Bridge陷阱.md) | GC、闭包、字符串混淆、Callback 等 | 编写 Java Hook 时 |
| [04-Native-Hook要点.md](04-Native-Hook要点.md) | API 上下文、SO 延迟加载、JNI 参数读取 | 编写 Native Hook 时 |
| [05-调试策略.md](05-调试策略.md) | 逐步启用、异常分类、Hook 点选择 | 排查 Hook 问题时 |
| [06-OkHttp3安全方法参考.md](06-OkHttp3安全方法参考.md) | Request/Response 安全方法表 | Hook OkHttp3 时 |
