"""
FastAPI dependency resolvers.
All tool endpoints use these — never access app.state directly.
"""
from __future__ import annotations
from typing import Annotated
from fastapi import Depends, Request

from app.services.backends.base import StorageBackend, DatabaseBackend, GraphBackend
from app.services.similarity import SimilarityService
from app.config.settings import settings


def _storage(request: Request) -> StorageBackend:
    return request.app.state.storage


def _db(request: Request) -> DatabaseBackend:
    return request.app.state.db


def _graph(request: Request) -> GraphBackend:
    return request.app.state.graph


def _similarity(request: Request) -> SimilarityService:
    return request.app.state.similarity


StorageDep = Annotated[StorageBackend, Depends(_storage)]
DatabaseDep = Annotated[DatabaseBackend, Depends(_db)]
GraphDep = Annotated[GraphBackend, Depends(_graph)]
SimilarityDep = Annotated[SimilarityService, Depends(_similarity)]


