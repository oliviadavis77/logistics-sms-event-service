from datetime import UTC, datetime

from shipment_alerts.alert_dispatcher import dispatch_shipment_alert
from shipment_alerts.models import ProofOfDelivery, ShipmentEvent, ShipmentEventType


def test_delivered_event_sends_proof_aware_alert_with_stable_key() -> None:
    calls: list[dict[str, str]] = []

    def record_send(**request: str) -> dict[str, object]:
        calls.append(request)
        return {"message_id": "msg_42"}

    event = ShipmentEvent(
        event_id="evt-1042",
        shipment_id="SHP-2048",
        recipient_phone="+14155550123",
        event_type=ShipmentEventType.DELIVERED,
        occurred_at=datetime(2026, 8, 21, 9, 30, tzinfo=UTC),
        proof_of_delivery=ProofOfDelivery(
            object_key="pod/SHP-2048/signature.jpg",
            sha256="a" * 64,
            signed_at=datetime(2026, 8, 21, 9, 29, tzinfo=UTC),
        ),
    )

    result = dispatch_shipment_alert(event, record_send)

    assert result.decision == "sent"
    assert result.message_id == "msg_42"
    assert calls == [
        {
            "to": "+14155550123",
            "message": "Shipment SHP-2048 was delivered. Proof of delivery was recorded.",
            "idempotency_key": "shipment-event:evt-1042",
        }
    ]


def test_in_transit_event_is_retained_without_sms() -> None:
    event = ShipmentEvent(
        event_id="evt-1043",
        shipment_id="SHP-2048",
        recipient_phone="+14155550123",
        event_type=ShipmentEventType.IN_TRANSIT,
        occurred_at=datetime(2026, 8, 21, 10, 0, tzinfo=UTC),
    )

    result = dispatch_shipment_alert(event, lambda **request: {"message_id": "unexpected"})

    assert result.decision == "not_alertable"
    assert result.message_id is None

