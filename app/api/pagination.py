"""Shared, bounded offset-pagination parameters for collection endpoints."""

from typing import Annotated

from fastapi import Query


PageOffset = Annotated[int, Query(ge=0)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
