from app.services.supabase_client import SupabaseNewsRepository


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, client, name):
        self.client = client
        self.name = name
        self.filters = []
        self.operation = None
        self.payload = None

    def select(self, columns):
        self.operation = ("select", columns)
        return self

    def insert(self, payload):
        self.operation = ("insert", payload)
        return self

    def upsert(self, payload, **kwargs):
        self.operation = ("upsert", payload, kwargs)
        return self

    def update(self, payload):
        self.operation = ("update", payload)
        return self

    def delete(self):
        self.operation = ("delete", None)
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def limit(self, value):
        self.filters.append(("limit", value))
        return self

    def execute(self):
        assert self.operation is not None
        self.client.calls.append((self.name, self.operation, list(self.filters)))
        key = (self.name, self.operation[0], tuple(self.filters))
        return FakeResponse(self.client.results.get(key, []))


class FakeClient:
    def __init__(self, results=None):
        self.results = results or {}
        self.calls = []

    def table(self, name):
        return FakeTable(self, name)


def build_repository(fake_client):
    repository = SupabaseNewsRepository(url="https://db", key="key")
    repository._client = fake_client
    return repository


def test_upsert_subscriber_marks_user_active():
    fake_client = FakeClient()
    repository = build_repository(fake_client)

    repository.upsert_subscriber(chat_id="42", username="viet", first_name="Viet")

    table, operation, filters = fake_client.calls[0]
    assert table == "telegram_subscribers"
    assert operation[0] == "upsert"
    assert operation[1]["chat_id"] == "42"
    assert operation[1]["is_active"] is True
    assert operation[1]["unsubscribed_at"] is None
    assert filters == []


def test_deactivate_subscriber_marks_user_inactive():
    fake_client = FakeClient()
    repository = build_repository(fake_client)

    repository.deactivate_subscriber("42")

    table, operation, filters = fake_client.calls[0]
    assert table == "telegram_subscribers"
    assert operation[0] == "update"
    assert operation[1]["is_active"] is False
    assert filters == [("chat_id", "42")]


def test_list_active_subscribers_returns_rows():
    results = {
        (
            "telegram_subscribers",
            "select",
            (("is_active", True),),
        ): [{"chat_id": "42", "is_active": True}],
    }
    repository = build_repository(FakeClient(results=results))

    subscribers = repository.list_active_subscribers()

    assert subscribers == [{"chat_id": "42", "is_active": True}]


def test_create_delivery_attempt_returns_false_when_already_sent():
    results = {
        (
            "telegram_deliveries",
            "select",
            (("news_url", "https://example.com/post"), ("chat_id", "42"), ("limit", 1)),
        ): [{"status": "sent"}],
    }
    repository = build_repository(FakeClient(results=results))

    created = repository.create_delivery_attempt("https://example.com/post", "42")

    assert created is False


def test_create_delivery_attempt_upserts_pending_row_when_missing():
    fake_client = FakeClient()
    repository = build_repository(fake_client)

    created = repository.create_delivery_attempt("https://example.com/post", "42")

    assert created is True
    assert fake_client.calls[1][0] == "telegram_deliveries"
    assert fake_client.calls[1][1][0] == "upsert"
    assert fake_client.calls[1][1][1]["status"] == "pending"


def test_mark_delivery_sent_updates_row():
    fake_client = FakeClient()
    repository = build_repository(fake_client)

    repository.mark_delivery_sent("https://example.com/post", "42")

    table, operation, filters = fake_client.calls[0]
    assert table == "telegram_deliveries"
    assert operation[0] == "update"
    assert operation[1]["status"] == "sent"
    assert filters == [("news_url", "https://example.com/post"), ("chat_id", "42")]
    assert fake_client.calls[1][0] == "telegram_subscribers"


def test_mark_delivery_failed_updates_row():
    fake_client = FakeClient()
    repository = build_repository(fake_client)

    repository.mark_delivery_failed("https://example.com/post", "42", "timeout")

    table, operation, filters = fake_client.calls[0]
    assert table == "telegram_deliveries"
    assert operation[0] == "update"
    assert operation[1]["status"] == "failed"
    assert operation[1]["error"] == "timeout"
    assert filters == [("news_url", "https://example.com/post"), ("chat_id", "42")]


def test_deactivate_subscriber_for_delivery_error_updates_error_message():
    fake_client = FakeClient()
    repository = build_repository(fake_client)

    repository.deactivate_subscriber_for_delivery_error("42", "blocked")

    table, operation, filters = fake_client.calls[0]
    assert table == "telegram_subscribers"
    assert operation[0] == "update"
    assert operation[1]["is_active"] is False
    assert operation[1]["delivery_error"] == "blocked"
    assert filters == [("chat_id", "42")]
