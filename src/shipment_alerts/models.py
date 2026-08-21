from datetime import datetime
from enum import StrEnum

try:
    from pydantic import BaseModel, Field
except ModuleNotFoundError:  # Keep the event/dispatcher layer usable in a bare test venv.
    class _Field:
        def __init__(self, **constraints: object) -> None:
            self.constraints = constraints

    def Field(**constraints: object) -> _Field:  # type: ignore[misc]
        return _Field(**constraints)

    class BaseModel:
        def __init__(self, **values: object) -> None:
            annotations = getattr(type(self), "__annotations__", {})
            for name in annotations:
                if name in values:
                    value = values[name]
                elif hasattr(type(self), name):
                    value = getattr(type(self), name)
                else:
                    raise TypeError(f"Missing required field: {name}")
                setattr(self, name, value)


class ShipmentEventType(StrEnum):
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    EXCEPTION = "exception"


class ProofOfDelivery(BaseModel):
    object_key: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signed_at: datetime


class ShipmentEvent(BaseModel):
    event_id: str = Field(min_length=1)
    shipment_id: str = Field(min_length=1)
    recipient_phone: str = Field(pattern=r"^\+[1-9]\d{7,14}$")
    event_type: ShipmentEventType
    occurred_at: datetime
    location: str | None = None
    exception_reason: str | None = None
    proof_of_delivery: ProofOfDelivery | None = None


class AlertResult(BaseModel):
    event_id: str
    decision: str
    message_id: str | None = None
