import app.notifications as notifications
from app.config import Settings


def test_unconfigured_send_is_noop():
    # No channels -> returns False without any network call.
    assert notifications.send("hi", settings=Settings()) is False


def test_configured_flags():
    assert Settings().notifications_configured is False
    tg = Settings(telegram_bot_token="t", telegram_chat_id="c")
    assert tg.telegram_configured is True
    assert tg.notifications_configured is True


def test_notify_if_ready_latches_once(tmp_path, monkeypatch):
    import app.readiness as readiness

    flag = tmp_path / ".ready_notified"
    monkeypatch.setattr(notifications, "READY_FLAG", flag)

    sent_messages = []
    monkeypatch.setattr(notifications, "send", lambda *a, **k: sent_messages.append(a[0]) or True)

    # Not ready -> no alert, no flag.
    monkeypatch.setattr(readiness, "evaluate", lambda settings=None: {"is_ready": False})
    assert notifications.notify_if_ready() is False
    assert not flag.exists()

    # Becomes ready -> one alert + flag set.
    ready = {"is_ready": True, "edge_confidence_pct": 96.0, "num_trades": 40, "profit_factor": 1.6}
    monkeypatch.setattr(readiness, "evaluate", lambda settings=None: ready)
    assert notifications.notify_if_ready() is True
    assert flag.exists()
    assert len(sent_messages) == 1

    # Still ready -> no duplicate alert.
    assert notifications.notify_if_ready() is False
    assert len(sent_messages) == 1

    # Regresses -> flag clears so it can re-arm later.
    monkeypatch.setattr(readiness, "evaluate", lambda settings=None: {"is_ready": False})
    notifications.notify_if_ready()
    assert not flag.exists()
