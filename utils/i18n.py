"""
Internationalization support.
"""

import json
from pathlib import Path

_translations = {}
_current_language = "zh_CN"


def init_i18n(language: str = "zh_CN"):
    """Initialize internationalization."""
    global _current_language
    _current_language = language
    
    locales_dir = Path(__file__).parent.parent / "i18n" / "locales"
    
    language_file = language.replace("-", "_")
    
    try:
        with open(locales_dir / f"{language_file}.json", "r", encoding="utf-8") as f:
            _translations.update(json.load(f))
    except FileNotFoundError:
        print(f"Locale file not found: {language_file}.json")
        with open(locales_dir / "en.json", "r", encoding="utf-8") as f:
            _translations.update(json.load(f))


def tr(key: str, **kwargs) -> str:
    """Translate a key to the current language."""
    translation = _translations.get(key, key)
    
    if kwargs:
        try:
            translation = translation.format(**kwargs)
        except KeyError:
            pass
    
    return translation


def tr_in_bundle(key: str, language: str) -> str:
    """Translate a key to a specific language."""
    locales_dir = Path(__file__).parent.parent / "i18n" / "locales"
    
    language_file = language.replace("-", "_")
    
    try:
        with open(locales_dir / f"{language_file}.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get(key, key)
    except FileNotFoundError:
        return key


def get_language() -> str:
    """Get the current language code."""
    return _current_language


def set_language(language: str) -> None:
    """Set the current language and reload translations."""
    init_i18n(language)


# 别名，简化翻译调用（与 Shinsekai 项目保持一致）
_ = tr


class Translator:
    """Translator class to manage language settings."""
    
    def get_language(self) -> str:
        """Get the current language code."""
        return get_language()
    
    def set_language(self, language: str) -> None:
        """Set the current language and reload translations."""
        set_language(language)


translator = Translator()


# 可用语言列表
available_languages = {
    "zh-CN": "简体中文",
    "en": "English",
}
