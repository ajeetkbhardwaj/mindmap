from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum


class SourceType(Enum):
    STATIC_ANALYSIS = "static_analysis"
    DEEPWIKI_WIKI = "deepwiki_wiki"
    DEEPWIKI_CODEMAP = "deepwiki_codemap"
    GIT_HISTORY = "git_history"
    RAG_RETRIEVAL = "rag_retrieval"


class ExtractionMethod(Enum):
    TREE_SITTER = "tree_sitter"
    LLM_STRUCTURE = "llm_structure"
    LLM_PAGE = "llm_page"
    LLM_CODEMAP = "llm_codemap"
    GIT_DIFF = "git_diff"


@dataclass
class Provenance:
    source: SourceType
    extraction_method: ExtractionMethod
    confidence: float
    source_revision: str
    extracted_at: str = None
    extractor_version: str = "0.1.0"

    def __post_init__(self):
        if self.extracted_at is None:
            self.extracted_at = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> dict:
        return {
            "source": self.source.value,
            "extraction_method": self.extraction_method.value,
            "confidence": self.confidence,
            "source_revision": self.source_revision,
            "extracted_at": self.extracted_at,
            "extractor_version": self.extractor_version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Provenance":
        return cls(
            source=SourceType(data["source"]),
            extraction_method=ExtractionMethod(data["extraction_method"]),
            confidence=data["confidence"],
            source_revision=data["source_revision"],
            extracted_at=data.get("extracted_at"),
            extractor_version=data.get("extractor_version", "0.1.0"),
        )