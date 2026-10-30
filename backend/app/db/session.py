from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker, with_loader_criteria
from starlette.requests import Request

from app.core.config import settings
from app.db.url import normalize_database_url


class Base(DeclarativeBase):
    pass


database_url = normalize_database_url(settings.database_url)
connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@event.listens_for(Session, "do_orm_execute")
def _apply_owner_scope(execute_state) -> None:
    if (
        not execute_state.is_select
        or execute_state.execution_options.get("skip_owner_scope")
    ):
        return
    owner_user_id = execute_state.session.info.get("owner_user_id")
    if not owner_user_id:
        return
    statement = execute_state.statement
    for mapper in Base.registry.mappers:
        model = mapper.class_
        if hasattr(model, "owner_user_id"):
            statement = statement.options(
                with_loader_criteria(
                    model,
                    lambda entity: entity.owner_user_id == owner_user_id,
                    include_aliases=True,
                )
            )
    execute_state.statement = statement


def get_db(request: Request):
    db = SessionLocal()
    identity = getattr(getattr(request, "state", None), "authenticated_identity", None)
    if identity is not None:
        db.info["owner_user_id"] = identity.primary_user_id
    try:
        yield db
    finally:
        db.close()
