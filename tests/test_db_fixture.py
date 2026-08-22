from sqlalchemy import text


def test_db_session_rolls_back_after_test(db_session):
    db_session.execute(text("CREATE TABLE IF NOT EXISTS _fixture_probe (id int)"))
    db_session.execute(text("INSERT INTO _fixture_probe VALUES (1)"))
    db_session.commit()

    result = db_session.execute(text("SELECT COUNT(*) FROM _fixture_probe")).scalar()
    assert result == 1


def test_second_run_does_not_see_first_runs_data(db_session):
    db_session.execute(text("CREATE TABLE IF NOT EXISTS _fixture_probe (id int)"))
    count = db_session.execute(text("SELECT COUNT(*) FROM _fixture_probe")).scalar()
    assert count == 0
