"""mplxe — rule-based business text normalization core."""
from .models import (
    Attribute,
    AttributeConflict,
    AttributeConflictCandidate,
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
from .resolvers import (
    AttrCandidate,
    ConflictResolver,
    DefaultConflictResolver,
    candidates_from_matches,
)
from .errors import MplxeError, ConfigError, RuleError
from .extensions import LLMSuggestionProvider, CodeGenerator
from .io.yaml_loader import load_pipeline_config, parse_pipeline_config
from .loader import load_rules

__all__ = [
    "Attribute",
    "AttributeConflict",
    "AttributeConflictCandidate",
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
    "AttrCandidate",
    "ConflictResolver",
    "DefaultConflictResolver",
    "candidates_from_matches",
    "MplxeError",
    "ConfigError",
    "RuleError",
    "LLMSuggestionProvider",
    "CodeGenerator",
    "load_pipeline_config",
    "parse_pipeline_config",
    "load_rules",
]

__version__ = "0.2.0"
