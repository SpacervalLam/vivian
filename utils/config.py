import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODEL_PATH = os.path.join(BASE_DIR, "Vivian", "Vivian.model3.json")

WINDOW_WIDTH = 800
WINDOW_HEIGHT = 800
WINDOW_TITLE = "薇薇安桌宠"

LIVE2D_RENDER_CONFIG = {
    "smooth_speed": 0.1,
    "angle_range": 30.0,
    "eye_smooth_speed": 0.25,
    "mouth_smooth_speed": 0.005,
    "breath_interval": 150,
    "blink_interval": 500,
}

AI_CONFIG = {
    "provider": "openai",
    "model": "gpt-3.5-turbo",
    "endpoint": None,
    "temperature": 0.7,
    "max_tokens": 150,
}
