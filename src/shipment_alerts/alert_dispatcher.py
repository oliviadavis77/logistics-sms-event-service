from collections.abc import Callable

from .models import AlertResult, ShipmentEvent, ShipmentEventType


SendSms = Callable[..., dict[str, object]]


def dispatch_shipment_alert(event: ShipmentEvent, send_sms: SendSms) -> AlertResult:
    message = _alert_message(event)
    if message is None:
        return AlertResult(event_id=event.event_id, decision="not_alertable")

    reply = send_sms(
        to=event.recipient_phone,
        message=message,
        idempotency_key=f"shipment-event:{event.event_id}",
    )
    return AlertResult(
        event_id=event.event_id,
        decision="sent",
        message_id=str(reply["message_id"]),
    )


def _alert_message(event: ShipmentEvent) -> str | None:
    if event.event_type is ShipmentEventType.DELIVERED:
        detail = " Proof of delivery was recorded." if event.proof_of_delivery else ""
        return f"Shipment {event.shipment_id} was delivered.{detail}"
    if event.event_type is ShipmentEventType.EXCEPTION:
        reason = event.exception_reason or "Carrier review required"
        return f"Shipment {event.shipment_id} needs attention: {reason}."
    return None

