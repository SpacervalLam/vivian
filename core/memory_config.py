"""Memory Configuration Constants

This module contains all configurable constants for the memory system,
eliminating magic numbers and improving maintainability.
"""

from typing import List

# === Memory Retrieval Configuration ===
DEFAULT_RETRIEVAL_K = 8
RETRIEVAL_EXPANSION_FACTOR = 3

# === Scoring Weights ===
SEMANTIC_SCORE_WEIGHT = 0.65
BM25_SCORE_WEIGHT = 0.35
IMPORTANCE_FACTOR = 0.1
RECENCY_FACTOR = 0.1
NAME_MEMORY_BOOST_SCORE = 0.8

# === Token Budgets ===
DEFAULT_TOKEN_BUDGET = 3000
SHORT_TERM_TOKEN_LIMIT = 30000
LONG_TERM_TOKEN_LIMIT = 100000
MID_TERM_TOKEN_LIMIT = 50000
MID_TERM_SUMMARY_THRESHOLD = 30000

# === Memory Block Configuration ===
MEMORY_BLOCK_TOKEN_LIMITS = {
    "important_events": 5000,
    "conversation_history": 10000,
    "knowledge_base": 15000,
}

# === Decay Configuration ===
DEFAULT_DECAY_RATE = 0.01
DIALOGUE_DECAY_RATE = 0.02
DECAY_TYPE = "exponential"
RECENCY_HALF_LIFE_HOURS = 24.0

# === Token Flush Configuration ===
TOKEN_FLUSH_RATIO = 0.1
CHAT_HISTORY_TOKEN_RATIO = 0.7

# === Name Detection Keywords ===
NAME_KEYWORDS: List[str] = [
    "中文名", "英文名", "名字", "叫我", "我是", "称呼我",
    "我的名字是",
]

# === Default Memory Block Configuration ===
DEFAULT_MEMORY_BLOCKS = [
    {"name": "important_events", "priority": 0, "token_limit": 5000},
    {"name": "conversation_history", "priority": 1, "token_limit": 10000},
    {"name": "knowledge_base", "priority": 2, "token_limit": 15000},
]