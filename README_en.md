# Vivian - Intelligent Desktop Pet

![Vivian Banner](https://via.placeholder.com/800x200/667eea/ffffff?text=Vivian+Desktop+Pet)

> An intelligent desktop pet application based on Live2D technology, providing you with a personalized virtual companion experience

---

## Language Versions

- [简体中文](README_zh.md)
- [English](README_en.md)

---

## 🌟 Project Highlights

- 🎨 **Live2D Animated Character** - High-quality 2D animation with rich expressions and actions
- 🤖 **AI Dialogue System** - Local + cloud AI models with context understanding and memory
- 🔊 **Voice Interaction** - Speech recognition and synthesis for natural voice communication
- 🎯 **Proactive Interaction** - Hourly greetings, teasing feedback, idle greetings, and intelligent proactive interactions
- 🛠️ **Tool Calling** - Rich system tools to help you perform various operations
- 📝 **Memory System** - Long-term memory management for personalized dialogue experiences
- 🚀 **Performance Optimization** - Zero-copy streaming, parallel processing, connection pooling

---

## 🚀 Quick Start

### System Requirements

- Python 3.8+
- Windows 10/11 (recommended)
- At least 4GB RAM
- GPU with OpenGL 3.0+ support

### Installation Steps

1. **Clone the repository**
```bash
git clone https://github.com/SpacervalLam/vivian.git
cd vivian
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Run the application**
```bash
python main.py
```

---

## 🎮 Usage

### Basic Operations

- **Click Interaction**: Click Vivian to wake her up and trigger different expressions and actions
- **Drag to Move**: Hold left mouse button and drag to move Vivian's position
- **Right-click Menu**: Right-click to show operation menu

### Keyboard Shortcuts

| Shortcut | Function |
|----------|----------|
| Ctrl+Shift+A | Open dialogue input box |
| Triple-click Vivian | Open dialogue input box |

### System Tools

Vivian can perform the following system operations:

- 🖥️ **Application Control**: Start/close applications
- 📁 **File Management**: Open folders, search files, copy/move/delete files
- 🖼️ **Desktop Operations**: Set wallpaper, take screenshots
- 💻 **Window Control**: Minimize/maximize/close windows
- 📋 **Clipboard**: Get/set clipboard content
- ⏰ **Scheduled Tasks**: Set reminders and scheduled executions

### Proactive Interactions

Vivian will proactively interact with you in the following situations:

- **Hourly Greetings**: Reminds you to take a break every hour
- **Idle Greetings**: Greets you when idle for a long time
- **Emotional Support**: Comforts you when detecting negative emotions
- **Random Actions**: Shows cute expressions and actions periodically

---

## 🧠 Memory System

### Memory Types

1. **Short-term Memory**: Recent conversation history for context understanding
2. **Long-term Memory**: Important information stored via semantic retrieval
3. **Sensory Memory**: Environment perception and interaction history

### Memory Management

- **Importance Evaluation**: Automatically evaluates memory importance based on content
- **Time Decay**: Memories gradually fade over time
- **Intelligent Retrieval**: Retrieve related memories based on semantic similarity

---

## 🔌 Plugin System

### Plugin Development

The project supports plugin extensions. Develop custom features via SDK:

```python
from core.sdk.plugin import Plugin

class MyPlugin(Plugin):
    def __init__(self):
        super().__init__("my_plugin", "My Plugin", "v1.0")
    
    def on_load(self, context):
        self.context = context
        print("Plugin loaded")
    
    def on_message(self, message):
        # Handle message
        return {"text": "Plugin response"}
```

### Plugin Directory

Plugins should be placed in the `data/plugins/` directory and registered in `data/config/plugins.yaml`.

---

## 📊 Performance Optimization

### Key Optimization Strategies

1. **Streaming Response**: Supports AI response streaming to reduce waiting time
2. **Connection Pool Reuse**: HTTP session pool reuse reduces connection overhead
3. **Request Caching**: Identical requests automatically use cached responses
4. **Async Processing**: Background threads handle AI requests without blocking UI
5. **Batch Updates**: UI updates are processed in batches to reduce rendering frequency

---

## 📄 License

This project uses the MIT License. See [LICENSE](LICENSE) for details.

---

## 📞 Contact

- Project: https://github.com/SpacervalLam/vivian
- Issues: https://github.com/SpacervalLam/vivian/issues
- Email: spacervallam@gmail.com

---

> © 2026 SpacervalLam. All rights reserved.
> 
> Made with ❤️