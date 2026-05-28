"""Prompt Configuration Constants

This module contains all configurable constants for the prompt building system,
eliminating magic numbers and improving maintainability.
"""

# === Memory Context Configuration ===
MEMORY_CONTEXT_MAX_TOKENS = 300
MEMORY_RETRIEVAL_K = 8
MEMORY_RETRIEVAL_LIMIT = 3
MEMORY_TEXT_TRUNCATE_LENGTH = 300

# === History Configuration ===
HISTORY_MAX_TURNS_WITH_SUMMARY = 3
HISTORY_MAX_TURNS_WITHOUT_SUMMARY = 5
HISTORY_MESSAGE_TRUNCATE_LENGTH = 80

# === Conversation Rules ===
NEW_SESSION_TIMEOUT_HOURS = 1
NAME_CALL_FREQUENCY_TURNS = 3
MAX_NAME_CALL_FREQUENCY_TURNS = 5

# === Response Guidelines ===
MIN_RESPONSE_LENGTH = 10
MAX_RESPONSE_LENGTH = 500
DEFAULT_RESPONSE_LENGTH = 50

# === Scoring Configuration ===
IMPORTANCE_HARD_CONSTRAINT = 0.9
IMPORTANCE_PROJECT_DECISION = 0.6
IMPORTANCE_GENERAL_FACT = 0.3
IMPORTANCE_CASUAL = 0.0

# === Expression Configuration ===
AVAILABLE_EXPRESSIONS = ["shy", "angry", "cry", "panic", "eye_roll", "umbrella_close"]

# === JSON Output Configuration ===
REQUIRED_OUTPUT_FIELDS = ["text"]
OPTIONAL_OUTPUT_FIELDS = ["motion", "expression", "importance_user", "tool", "arguments"]

# === Format Validation ===
JSON_OUTPUT_REQUIRED = True
LANGUAGE_MATCH_REQUIRED = True