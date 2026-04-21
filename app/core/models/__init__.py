"""ORM-модели домена. Импортируйте этот пакет до configure_mappers / Alembic autogenerate."""

from app.core.models.role import Role
from app.core.models.user import User
from app.core.models.tag import Tag, article_tags
from app.core.models.article import Article
from app.core.models.article_question import ArticleQuestion
from app.core.models.chat_message import ChatMessage
from app.core.models.chat_session import ChatSession

__all__ = [
    "Article",
    "ArticleQuestion",
    "ChatMessage",
    "ChatSession",
    "Role",
    "Tag",
    "User",
    "article_tags",
]
