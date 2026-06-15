"""REST API routes - mounted at /api in main.py."""

from fastapi import APIRouter

router = APIRouter()


# Sub-routers are imported and included below once they exist.
# We import lazily so that pieces can be implemented incrementally.
def _include_subrouters() -> None:
    from app.api import (  # noqa: F401
        admin,
        auth,
        boards,
        filters,
        issues,
        projects,
        search,
        sprints,
        users,
    )

    router.include_router(auth.router, prefix="/auth", tags=["auth"])
    router.include_router(users.router, prefix="/users", tags=["users"])
    router.include_router(projects.router, prefix="/projects", tags=["projects"])
    router.include_router(issues.router, prefix="/issues", tags=["issues"])
    router.include_router(search.router, prefix="/search", tags=["search"])
    router.include_router(sprints.router, prefix="/sprints", tags=["sprints"])
    router.include_router(boards.router, prefix="/boards", tags=["boards"])
    router.include_router(filters.router, prefix="/filters", tags=["filters"])
    router.include_router(admin.router, prefix="/admin", tags=["admin"])


_include_subrouters()
