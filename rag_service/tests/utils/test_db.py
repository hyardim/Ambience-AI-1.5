from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from src.utils.db import DatabaseManager


class TestDatabaseManager:
    def test_get_session_returns_session(self) -> None:
        manager = DatabaseManager()
        with patch.object(manager, "SessionLocal") as mock_session:
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
        with patch("src.utils.db.psycopg2.connect") as mock_connect:
            mock_connect.return_value = MagicMock()
            conn = manager.get_raw_connection()
            assert conn is not None
            mock_connect.assert_called_once()

    def test_engine_created(self) -> None:
        manager = DatabaseManager()
        assert manager.engine is not None

    def test_session_local_created(self) -> None:
        manager = DatabaseManager()
        assert manager.SessionLocal is not None
