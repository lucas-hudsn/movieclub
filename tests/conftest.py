import os
import pathlib

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["OMDB_API_KEY"] = "testkey"
os.environ["SECRET_KEY"] = "testsecret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)



@pytest.fixture()
def db():
    Base.metadata.create_all(engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db):
    from app.database import get_db

    def override():
        yield db

    app.dependency_overrides[get_db] = override
    with TestClient(app, follow_redirects=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def omdb_mock(monkeypatch):
    from app.services import omdb

    catalog = {
        "tt0133093": {"imdb_id": "tt0133093", "title": "The Matrix", "year": "1999", "poster_url": None,
                      "plot": "A hacker discovers reality is a simulation."},
        "tt0110912": {"imdb_id": "tt0110912", "title": "Pulp Fiction", "year": "1994", "poster_url": None,
                      "plot": "Interwoven crime stories."},
        "tt1375666": {"imdb_id": "tt1375666", "title": "Inception", "year": "2010", "poster_url": None,
                      "plot": "Thieves enter dreams."},
    }

    def fake_get(imdb_id):
        if imdb_id not in catalog:
            raise omdb.OMDBError("not found")
        return dict(catalog[imdb_id])

    monkeypatch.setattr(omdb, "get_by_imdb_id", fake_get)
    monkeypatch.setattr(omdb, "search", lambda q: list(catalog.values()))
    return catalog


def register(client, email, name="op"):
    return client.post("/register", data={"email": email, "name": name, "password": "hunter2222"})


def create_team(client, name="the crew"):
    return client.post("/teams", data={"name": name})


def team_invite_code(db):
    from sqlalchemy import select

    from app.models import Team

    return db.scalars(select(Team)).first().invite_code


def join_team(client, code):
    return client.post("/teams/join", data={"code": code})
