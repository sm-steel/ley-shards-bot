import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ley_shards_bot.models import Base


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
