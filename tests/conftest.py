from pathlib import Path

from dotenv import load_dotenv

# Must run before any `app.*` import below - app.config constructs Settings()
# at import time, so .env.test has to be loaded first or the override
# arrives too late. override=True is deliberate: a DATABASE_URL already
# exported in the shell (or sitting in a dev .env) must not win over the
# test one - that's exactly the class of bug that let a stray
# Postman-created row leak into a pytest run.
load_dotenv(Path(__file__).resolve().parent.parent / ".env.test", override=True)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
