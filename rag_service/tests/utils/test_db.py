from unittest.mock import MagicMock, patch

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.utils.db import DatabaseManager


class TestDatabaseManager:
    def test_get_session_returns_session(self) -> None:
        manager = DatabaseManager()
        with patch.object(manager, "_session_local") as mock_session:
            mock_session.return_value = MagicMock(spec=Session)
            session = manager.get_session()
            assert session is not None

    def test_test_connection_success(self) -> None:
        manager = DatabaseManager()
        with patch.object(manager.engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_connect.return_value.__exit__ = MagicMock(return_value=False)
            result = manager.test_connection()
            assert result is True

    def test_test_connection_failure(self) -> None:
        manager = DatabaseManager()
        with patch.object(
            manager.engine, "connect", side_effect=Exception("connection refused")
        ):
            result = manager.test_connection()
            assert result is False

    def test_get_raw_connection(self) -> None:
        manager = DatabaseManager()
        fake_pool = MagicMock()
        fake_pool.getconn.return_value = MagicMock()
        with patch.object(manager, "_raw_pool", fake_pool):
            conn = manager.get_raw_connection()
            assert conn is not None
            fake_pool.getconn.assert_called_once()

    def test_engine_created_lazily(self) -> None:
        manager = DatabaseManager()
        assert manager._engine is None  # not created yet
        with (
            patch(
                "src.utils.db.db_config",
                new=MagicMock(database_url="postgresql://db.example/test"),
            ),
            patch("src.utils.db.create_engine") as mock_engine,
        ):
            mock_engine.return_value = MagicMock(spec=Engine)
            engine = manager.engine  # triggers creation
            assert engine is not None
            mock_engine.assert_called_once_with(
                "postgresql://db.example/test",
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
            )

    def test_engine_not_recreated(self) -> None:
        manager = DatabaseManager()
        with patch("src.utils.db.create_engine") as mock_engine:
            mock_engine.return_value = MagicMock(spec=Engine)
            _ = manager.engine
            _ = manager.engine  # second access
            mock_engine.assert_called_once()  # still only called once

    def test_session_local_created(self) -> None:
        manager = DatabaseManager()
        assert manager.SessionLocal is not None
