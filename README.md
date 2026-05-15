# 薇薇安 (Vivian) - 智能桌面宠物

![Vivian Banner](https://via.placeholder.com/800x200/667eea/ffffff?text=Vivian+Desktop+Pet)

> 一个基于 Live2D 技术的智能桌面宠物应用，为您提供个性化的虚拟伙伴体验

---

## 语言版本 | Language Versions

- [简体中文](README_zh.md)
- [English](README_en.md)

---

## 🌟 项目特色

- 🎨 **Live2D 动画角色** - 高质量 2D 动画，丰富的表情和动作
- 🤖 **智能对话系统** - 本地+云端 AI 模型，支持上下文理解和记忆
- 🔊 **语音交互** - 语音识别和合成，自然的声音交流
- 🎯 **主动交互** - 整点问候、调戏反馈、空闲问候等智能主动互动
- 🛠️ **工具调用** - 丰富的系统工具，帮您执行各种操作
- 📝 **记忆系统** - 长期记忆管理，个性化对话体验
- 🚀 **性能优化** - 零拷贝流式传输、并行处理、连接池复用

---

## 🚀 快速开始

### 环境要求

- Python 3.8+
- Windows 10/11 (推荐)
- 至少 4GB 内存
- 支持 OpenGL 3.0+ 的显卡

### 安装步骤

1. **克隆项目**
```bash
git clone https://github.com/SpacervalLam/vivian.git
cd vivian
```

2. **安装依赖**
```bash
pip install -r requirements.txt
```

3. **运行程序**
```bash
python main.py
```

---

## 🎮 使用说明

### 基础操作

- **点击交互**: 点击薇薇安可以唤醒她，触发不同的表情和动作
- **拖拽移动**: 按住左键拖拽可以移动薇薇安的位置
- **右键菜单**: 右键点击显示操作菜单

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| Ctrl+Shift+A | 打开对话输入框 |
| 双击薇薇安 | 显示/隐藏侧边栏 |

### 系统工具

薇薇安可以执行以下系统操作：

- 🖥️ **应用控制**: 启动/关闭应用程序
- 📁 **文件管理**: 打开文件夹、搜索文件、复制/移动/删除文件
- 🖼️ **桌面操作**: 设置壁纸、截图
- 💻 **窗口控制**: 最小化/最大化/关闭窗口
- 📋 **剪贴板**: 获取/设置剪贴板内容
- ⏰ **定时任务**: 设置提醒和定时执行

### 主动交互

薇薇安会在以下情况主动与您互动：

- **整点问候**: 每小时提醒您休息
- **空闲问候**: 长时间不操作时主动打招呼
- **情感关怀**: 检测到您表达负面情绪时给予安慰
- **随机动作**: 不定期展示可爱的表情和动作

---

## 🧠 记忆系统

### 记忆类型

1. **短期记忆**: 最近的对话记录，用于上下文理解
2. **长期记忆**: 通过语义检索存储的重要信息
3. **感官记忆**: 环境感知和交互历史

### 记忆管理

- **重要性评估**: 根据内容自动评估记忆重要性
- **时间衰减**: 记忆随时间逐渐遗忘
- **智能检索**: 基于语义相似度检索相关记忆

---

## 🔌 插件系统

### 插件开发

项目支持插件扩展，通过SDK开发自定义功能：

```python
from core.sdk.plugin import Plugin

class MyPlugin(Plugin):
    def __init__(self):
        super().__init__("my_plugin", "我的插件", "v1.0")
    
    def on_load(self, context):
        self.context = context
        print("插件已加载")
    
    def on_message(self, message):
        # 处理消息
        return {"text": "插件响应"}
```

### 插件目录

插件应放置在 `data/plugins/` 目录下，并在 `data/config/plugins.yaml` 中注册。

---

## 📊 性能优化

### 关键优化策略

1. **流式响应**: 支持AI响应流式传输，减少等待时间
2. **连接池复用**: HTTP会话池复用，减少连接开销
3. **请求缓存**: 相同请求自动使用缓存响应
4. **异步处理**: 后台线程处理AI请求，不阻塞UI
5. **批量更新**: UI更新批量处理，减少渲染次数

---

## 🤝 贡献指南

欢迎贡献代码！请遵循以下规范：

1. **代码风格**: 使用 PEP 8 规范
2. **提交信息**: 清晰描述变更内容
3. **分支管理**: 使用 feature/* 分支开发新功能
4. **测试**: 添加单元测试确保功能正确

### 开发环境

```bash
# 安装开发依赖
pip install -r requirements-dev.txt

# 运行测试
pytest tests/

# 代码格式化
black .

# 代码检查
flake8 .
```

---

## 📄 许可证

本项目采用 MIT 许可证，详见 [LICENSE](LICENSE) 文件。

---

## 📞 联系方式

- 项目地址: https://github.com/SpacervalLam/vivian
- 问题反馈: https://github.com/SpacervalLam/vivian/issues
- 邮箱: support@vivian-pet.com

---

<div align="center">
  <p>© 2026 SpacervalLam保留所有权利。</p>
  <p>Made with ❤️</p>
</div>