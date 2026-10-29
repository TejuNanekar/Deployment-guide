"""API and index records."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentSpec(BaseModel):
    repo_id: str
    source_path: str
    absolute_path: str
    document_type: str
    component: str
    environment: str
    status: str
    git_ref: str
    project_id: str = "matrimony-platform"


class Chunk(BaseModel):
    chunk_index: int
    heading: str
    text: str
    title: str
    document: DocumentSpec


class AskRequest(BaseModel):
    question: str = Field(min_length=3)
    component: str | None = None
    environment: str = "uat"
    debug: bool = False


class StepModel(BaseModel):
    where: str
    command: str
    purpose: str
    expected: str
    source_path: str
    git_ref: str
    status: str
    heading: str


class CitationModel(BaseModel):
    source_path: str
    heading: str
    git_ref: str
    status: str
    component: str
    excerpt: str


class ComponentOption(BaseModel):
    id: str
    label: str


class TraceModel(BaseModel):
    project_id: str
    environment: str
    component: str | None = None
    embedding_id: str
    semantic: bool
    index_status: str
    outcome: str
    sources: list[str] = Field(default_factory=list)
    latency_ms: int


class AskResponse(BaseModel):
    answer_kind: str
    message: str
    steps: list[StepModel] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    citations: list[CitationModel] = Field(default_factory=list)
    components: list[ComponentOption] = Field(default_factory=list)
    trace: TraceModel | None = None


class CatalogFile(BaseModel):
    repo_id: str
    source_path: str
    component: str
    environment: str
    status: str
    document_type: str
    git_ref: str


class CatalogResponse(BaseModel):
    project_id: str
    files: list[CatalogFile]
    unassigned: list[CatalogFile]


class IngestResponse(BaseModel):
    files: int
    chunks: int
    unassigned: int
    git_refs: dict[str, str]


class ChatChoice(BaseModel):
    id: str
    label: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    question: str | None = None
    environment: str | None = None
    component: str | None = None


class ChatResponse(BaseModel):
    reply: str
    choices: list[ChatChoice] = Field(default_factory=list)
    choice_kind: str | None = None
    question: str | None = None
    environment: str | None = None
    component: str | None = None
    answer: AskResponse | None = None
