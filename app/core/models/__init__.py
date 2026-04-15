"""ORM-модели домена. Импортируйте этот пакет до configure_mappers / Alembic autogenerate."""

from app.core.models.role import Role
from app.core.models.user import User
from app.core.models.tag import Tag, article_tags
from app.core.models.article import Article
from app.core.models.article_question import ArticleQuestion

__all__ = [
    "Article",
    "ArticleQuestion",
    "Role",
    "Tag",
    "User",
    "article_tags",
]
