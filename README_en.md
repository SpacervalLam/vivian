# Vivian - Intelligent Desktop Pet

![Vivian Banner](https://via.placeholder.com/800x200/667eea/ffffff?text=Vivian+Desktop+Pet)

> An intelligent desktop pet application based on Live2D technology, providing you with a personalized virtual companion experience

---

## Language Versions

- [简体中文](README_zh.md) | [English](README_en.md)

---

## 🌟 Features

### 🎨 Core Features
- **Live2D Animation** - High-quality 2D animation with rich expressions
- **AI Dialogue** - Multiple AI models with context understanding
- **Voice Interaction** - Speech recognition and synthesis

### 🎯 Proactive Interaction
- **Hourly Greetings** - Reminds you to take breaks
- **Emotional Support** - Detects and comforts negative emotions
- **Random Actions** - Periodically shows cute expressions

### 📝 Memory System
- **Short-term** - Recent conversation history for context
- **Mid-term** - Session summaries with vector retrieval
- **Long-term** - Extracted facts and knowledge storage

### 💖 Mood System
- **Happiness** - Affects response positivity
- **Energy** - Affects response length and activity
- **Intimacy** - Affects conversation closeness
- **Boredom** - Increases with prolonged inactivity

### 📔 Diary System
- **Auto Generation** - Daily automatic summarization
- **Smart Summary** - Extracts key events and mood changes
- **Manual Entry** - Supports manual diary entries
- **Data Export** - Export diary data

---

## 🚀 Quick Start

### Requirements
- Python 3.8+
- Windows 10/11
- 4GB+ RAM
- OpenGL 3.0+ compatible GPU

### Installation
```bash
# Clone repository
git clone https://github.com/SpacervalLam/vivian.git
cd vivian

# Install dependencies
pip install -r requirements.txt

# Run application
python main.py
```

---

## 🎮 Usage

### Basic Operations
| Action | Function |
|--------|----------|
| Click | Trigger expressions/actions |
| Double-click | Open quick chat |
| Drag | Move position |
| Right-click | Show menu |

### Keyboard Shortcuts
| Shortcut | Function |
|----------|----------|
| Ctrl+Shift+A | Open dialogue input |
| Triple-click | Open dialogue input |

### System Tools
- 🖥️ App Control - Start/close applications
- 📁 File Management - Open folders, search files
- 🖼️ Desktop Operations - Set wallpaper, take screenshots
- 💻 Window Control - Minimize/maximize/close
- 📋 Clipboard - Get/set clipboard content
- ⏰ Scheduled Tasks - Set reminders

---

## 💖 Mood System

### Status Types
| Status | Condition | Behavior |
|--------|-----------|----------|
| 😊 Happy | happiness>70, energy>50 | Positive and lively |
| 🎉 Excited | happiness>80, energy>70 | Very active |
| 😴 Tired | energy<30 | Short and lazy responses |
| 😴 Sleepy | energy<20, night time | May fall asleep |
| 😐 Bored | boredom>70 | Proactive interaction |
| 😢 Sad | happiness<30 | Low mood |
| 😠 Angry | happiness<20 | Cold responses |

---

## 📔 Diary System

### Generation Methods
1. **Scheduled** - Auto-generate at fixed times
2. **Smart Trigger** - Auto-generate based on interaction
3. **Manual** - User-created entries

### Diary Content
- Key events summary
- Mood change curve
- Interaction statistics
- Keyword tags

---

## 🔌 Plugin System

Extend functionality with plugins:

```python
from core.sdk.plugin import Plugin

class MyPlugin(Plugin):
    def __init__(self):
        super().__init__("my_plugin", "My Plugin", "v1.0")
    
    def on_load(self, context):
        print("Plugin loaded")
    
    def on_message(self, message):
        return {"text": "Plugin response"}
```

---

## 📊 Performance Optimization

- **Streaming Response** - Real-time AI response streaming
- **Connection Pool** - HTTP session reuse
- **Request Caching** - Cached identical requests
- **Async Processing** - Background thread handling

---

## 📄 License

MIT License

---

> © 2026 SpacervalLam | Made with ❤️