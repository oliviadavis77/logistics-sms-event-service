from fastapi import FastAPI, HTTPException

from .alert_dispatcher import dispatch_shipment_alert
from .infrai_sms import InfraiError, InfraiSmsClient
from .models import AlertResult, ShipmentEvent

app = FastAPI(title="Logistics SMS event service")


@app.post("/shipment-events", response_model=AlertResult)
def accept_shipment_event(event: ShipmentEvent) -> AlertResult:
    client = InfraiSmsClient()
    try:
        return dispatch_shipment_alert(event, client.sms_send)
    except InfraiError as exc:
        client_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=client_status,
            detail={"code": exc.code, "error": exc.detail},
        ) from exc
    finally:
        client.close()


def main() -> None:
    import uvicorn

    uvicorn.run("shipment_alerts.service:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()

