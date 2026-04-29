"""mplxe — rule-based business text normalization core."""
from .models import (
    Attribute,
    Dictionary,
    DictionaryEntry,
    Match,
    NormalizeInput,
    NormalizeResult,
    PipelineConfig,
    Rule,
    RuleSet,
    Token,
)
from .pipeline import NormalizePipeline
from .normalizer import preprocess
from .tokenizer import Tokenizer, SimpleTokenizer
from .dictionary import DictionaryMatcher, LongestSynonymDictionaryMatcher
from .rules import RuleMatcher, DefaultRuleMatcher
from .errors import MplxeError, ConfigError, RuleError
from .extensions import LLMSuggestionProvider, CodeGenerator
from .io.yaml_loader import load_pipeline_config, parse_pipeline_config

__all__ = [
    "Attribute",
    "Dictionary",
    "DictionaryEntry",
    "Match",
    "NormalizeInput",
    "NormalizeResult",
    "PipelineConfig",
    "Rule",
    "RuleSet",
    "Token",
    "NormalizePipeline",
    "preprocess",
    "Tokenizer",
    "SimpleTokenizer",
    "DictionaryMatcher",
    "LongestSynonymDictionaryMatcher",
    "RuleMatcher",
    "DefaultRuleMatcher",
    "MplxeError",
    "ConfigError",
    "RuleError",
    "LLMSuggestionProvider",
    "CodeGenerator",
    "load_pipeline_config",
    "parse_pipeline_config",
]

__version__ = "0.1.0"
