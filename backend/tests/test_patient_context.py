"""
Tests for patient context fields (patient_age, patient_gender, patient_notes)
on chat creation and retrieval.
"""


class TestPatientContextCreate:

    def test_create_chat_with_all_patient_fields(self, client, gp_headers):
        resp = client.post("/chats/", json={
            "title": "Neurology Case",
            "specialty": "neurology",
            "patient_age": 45,
            "patient_gender": "female",
            "patient_notes": "Type 2 diabetes, eGFR 38",
        }, headers=gp_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["patient_age"] == 45
        assert data["patient_gender"] == "female"
        assert data["patient_notes"] == "Type 2 diabetes, eGFR 38"

    def test_create_chat_without_patient_fields_defaults_to_none(self, client, gp_headers):
        resp = client.post("/chats/", json={"specialty": "neurology"}, headers=gp_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["patient_age"] is None
        assert data["patient_gender"] is None
        assert data["patient_notes"] is None

    def test_create_chat_with_age_only(self, client, gp_headers):
        resp = client.post("/chats/", json={
            "specialty": "rheumatology",
            "patient_age": 72,
        }, headers=gp_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["patient_age"] == 72
        assert data["patient_gender"] is None
        assert data["patient_notes"] is None

    def test_create_chat_with_gender_only(self, client, gp_headers):
        resp = client.post("/chats/", json={
            "specialty": "neurology",
            "patient_gender": "male",
        }, headers=gp_headers)
        assert resp.status_code == 200
        assert resp.json()["patient_gender"] == "male"

    def test_create_chat_with_notes_only(self, client, gp_headers):
        resp = client.post("/chats/", json={
            "specialty": "neurology",
            "patient_notes": "Known penicillin allergy",
        }, headers=gp_headers)
        assert resp.status_code == 200
        assert resp.json()["patient_notes"] == "Known penicillin allergy"

    def test_patient_age_zero_stored_correctly(self, client, gp_headers):
        """Age 0 (newborn) is a valid clinical value and must not be dropped."""
        resp = client.post("/chats/", json={
            "specialty": "neurology",
            "patient_age": 0,
        }, headers=gp_headers)
        assert resp.status_code == 200
        assert resp.json()["patient_age"] == 0


class TestPatientContextPersistence:

    def test_patient_context_persists_on_get(self, client, gp_headers):
        """Fields stored in JSONB are returned correctly when fetching the chat."""
        chat_id = client.post("/chats/", json={
            "specialty": "neurology",
            "patient_age": 60,
            "patient_gender": "female",
            "patient_notes": "RRMS on interferon beta-1a",
        }, headers=gp_headers).json()["id"]

        data = client.get(f"/chats/{chat_id}", headers=gp_headers).json()
        assert data["patient_age"] == 60
        assert data["patient_gender"] == "female"
        assert data["patient_notes"] == "RRMS on interferon beta-1a"

    def test_patient_context_in_list_endpoint(self, client, gp_headers):
        client.post("/chats/", json={
            "specialty": "neurology",
            "patient_age": 55,
            "patient_gender": "male",
        }, headers=gp_headers)
        chats = client.get("/chats/", headers=gp_headers).json()
        assert len(chats) == 1
        assert chats[0]["patient_age"] == 55
        assert chats[0]["patient_gender"] == "male"


class TestPatientContextRAGPayload:

    def test_patient_context_forwarded_to_rag(self, client, gp_headers):
        """All patient fields plus specialty and severity reach the RAG payload."""
        from unittest.mock import MagicMock, patch

        chat = client.post("/chats/", json={
            "specialty": "neurology",
            "severity": "high",
            "patient_age": 45,
            "patient_gender": "female",
            "patient_notes": "eGFR 38, T2DM",
        }, headers=gp_headers).json()

        captured = {}

        def fake_rag(url, json, timeout):
            captured.update(json)
            m = MagicMock()
            m.raise_for_status = MagicMock()
            m.json.return_value = {"answer": "ok", "citations": [], "citations_used": [], "citations_retrieved": []}
            return m

        with patch("src.services.chat_service.httpx.post", side_effect=fake_rag):
            client.post(
                f"/chats/{chat['id']}/message",
                json={"role": "user", "content": "What treatment?"},
                headers=gp_headers,
            )

        ctx = captured.get("patient_context", {})
        assert ctx.get("age") == 45
        assert ctx.get("gender") == "female"
        assert ctx.get("notes") == "eGFR 38, T2DM"
        assert ctx.get("specialty") == "neurology"
        assert ctx.get("severity") == "high"

    def test_no_patient_context_key_when_fields_absent(self, client, gp_headers):
        """If no patient fields are set, patient_context in RAG payload is absent or empty."""
        from unittest.mock import MagicMock, patch

        chat = client.post("/chats/", json={"specialty": "neurology"}, headers=gp_headers).json()
        captured = {}

        def fake_rag(url, json, timeout):
            captured.update(json)
            m = MagicMock()
            m.raise_for_status = MagicMock()
            m.json.return_value = {"answer": "ok", "citations": [], "citations_used": [], "citations_retrieved": []}
            return m

        with patch("src.services.chat_service.httpx.post", side_effect=fake_rag):
            client.post(
                f"/chats/{chat['id']}/message",
                json={"role": "user", "content": "What treatment?"},
                headers=gp_headers,
            )

        ctx = captured.get("patient_context")
        if ctx:
            assert ctx.get("age") is None
            assert ctx.get("gender") is None
            assert ctx.get("notes") is None

    def test_recent_conversation_history_forwarded_to_rag(self, client, gp_headers):
        from unittest.mock import MagicMock, patch

        chat = client.post("/chats/", json={"specialty": "neurology"}, headers=gp_headers).json()

        second_payload = {}
        call_count = {"value": 0}

        def fake_rag(url, json, timeout):
            del url, timeout
            call_count["value"] += 1
            if call_count["value"] == 2:
                second_payload.update(json)
            response = MagicMock()
            response.raise_for_status = MagicMock()
            response.json.return_value = {
                "answer": "First answer" if call_count["value"] == 1 else "ok",
                "citations": [],
                "citations_used": [],
                "citations_retrieved": [],
            }
            return response

        with patch("src.services.chat_service.httpx.post", side_effect=fake_rag):
            client.post(
                f"/chats/{chat['id']}/message",
                json={"role": "user", "content": "Initial question"},
                headers=gp_headers,
            )
            client.post(
                f"/chats/{chat['id']}/message",
                json={"role": "user", "content": "Follow-up question"},
                headers=gp_headers,
            )

        history = (second_payload.get("patient_context") or {}).get("conversation_history", "")
        assert "GP: Initial question" in history
        assert "AI: First answer" in history
        assert "GP: Follow-up question" in history
