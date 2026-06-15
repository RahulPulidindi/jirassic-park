"""SQLAlchemy ORM models.

Import every model module at package import time so that `Base.metadata` is
fully populated before `create_all` runs.
"""

from app.db import Base  # noqa: F401
from app.models.activity import Activity  # noqa: F401
from app.models.attachment import Attachment  # noqa: F401
from app.models.board import Board  # noqa: F401
from app.models.comment import Comment  # noqa: F401
from app.models.custom_field import CustomField, CustomFieldValue  # noqa: F401
from app.models.issue import ISSUE_TYPES, PRIORITIES, Issue  # noqa: F401
from app.models.label import IssueLabel, Label  # noqa: F401
from app.models.link import LINK_TYPES, IssueLink  # noqa: F401
from app.models.project import Project  # noqa: F401
from app.models.saved_filter import SavedFilter  # noqa: F401
from app.models.sprint import Sprint, SprintIssue  # noqa: F401
from app.models.user import Team, TeamMember, User  # noqa: F401
from app.models.watcher import Vote, Watcher  # noqa: F401
from app.models.workflow import Workflow, WorkflowStatus, WorkflowTransition  # noqa: F401
