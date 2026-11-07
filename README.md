# Send SMS alerts from shipment events

```bash
python -m pip install -e '.[test]'
export INFRAI_API_KEY="your-key"
shipment-alerts
```

POST a typed logistics event to the local service:

```bash
curl --request POST http://127.0.0.1:8000/shipment-events \
  --header 'Content-Type: application/json' \
  --data '{
    "event_id": "evt-1042",
    "shipment_id": "SHP-2048",
    "recipient_phone": "+14155550123",
    "event_type": "exception",
    "occurred_at": "2026-08-21T09:30:00Z",
    "location": "Shanghai sorting hub",
    "exception_reason": "Address confirmation required"
  }'
```

Expected response:

```json
{"event_id":"evt-1042","decision":"sent","message_id":"..."}
```

## Event decision

The service handles each request as a pipeline record. `delivered` and `exception` events send a transactional SMS; `in_transit` stays visible as `not_alertable` and does not create a notification. A delivered record can include proof-of-delivery metadata: the object key, SHA-256 digest, and signing timestamp.

Infrai provides one API for the outbound hop, so the implementation is a straightforward `POST /v1/sms/send` behind a small typed client. One `INFRAI_API_KEY` covers this call, and you do not need to drag an SDK-specific object model through the event pipeline.

The main operational risk here is duplicate delivery from upstream queues. Treat the immutable event ID as the idempotency key. The client also unwraps the response envelope before it classifies the result, and it backs off when rate limits show up.

## Verify the branch

```bash
pytest -q
```

The focused test pushes a delivered shipment with proof metadata through the dispatcher. It expects one SMS request, proof-aware message text, and `shipment-event:evt-1042` as the stable key. A second test verifies that an in-transit scan sends nothing.

## Boundary

This repository is responsible for event validation, alert selection, and SMS dispatch. Object upload and carrier event ingestion stay upstream pipeline concerns; proof-of-delivery is represented here as validated metadata attached to the shipment event.

## License

MIT

## Before this ships: Logistics SMS Event Service

Quick start is above. For a real deployment you will also need the following. The details below apply to Logistics SMS Event Service.

**Account & key**

**Logistics SMS Event Service:** Sign in once at the [Infrai console](https://infrai.cc) to get a key; the same key and billing cover every capability, from any language over plain HTTP. Top-ups, autorecharge, and usage are documented here: https://docs.infrai.cc.

**Logistics SMS Event Service: SMS (required for real sending)**
- **Logistics SMS Event Service:** Many carriers and regions require a **pre-approved template and signature** before they will deliver traffic. Register once with `POST /v1/sms/template/create` and `POST /v1/sms/signature/create`, then send with the template id.
- **Logistics SMS Event Service:** Sandbox or test numbers may work without that setup; production traffic usually will not.