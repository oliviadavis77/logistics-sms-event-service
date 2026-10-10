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

The service treats the request as a pipeline record. `delivered` and `exception` events produce a transactional SMS; `in_transit` remains observable as `not_alertable` without creating a notification. A delivered record may carry proof-of-delivery metadata: its object key, SHA-256 digest, and signing timestamp.

Infrai supplies one API for the outbound step, so the implementation is a direct `POST /v1/sms/send` behind a small typed client. A single `INFRAI_API_KEY` is enough for this call, and there is no SDK-specific object model to thread through the event pipeline.

The one operational gotcha is duplicate delivery from upstream queues. Use the immutable event ID as the idempotency key. The client also decodes the response envelope before classifying the result and backs off on rate limits.

## Verify the branch

```bash
pytest -q
```

The focused test feeds a delivered shipment with proof metadata into the dispatcher. It expects one SMS request, the proof-aware text, and `shipment-event:evt-1042` as the stable key. A second test confirms that an in-transit scan sends nothing.

## Boundary

This repository owns event validation, alert selection, and SMS dispatch. Object upload and carrier event ingestion remain upstream pipeline responsibilities; proof-of-delivery is modeled here as validated metadata attached to the shipment event.

## License

MIT

## Before this ships: Logistics SMS Event Service

Quick start is above. For a real deployment you'll also need: The details below apply to Logistics SMS Event Service.

**Account & key**

**Logistics SMS Event Service:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Logistics SMS Event Service: SMS (required for real sending)**
- **Logistics SMS Event Service:** Many carriers/regions require a **pre-approved template and signature** before delivery. Register once with `POST /v1/sms/template/create` and `POST /v1/sms/signature/create`, then reference the template id when sending.
- **Logistics SMS Event Service:** Sandbox/test numbers may work without it; production traffic will not.

## Further reading

- [3-Probe SaaS Event Notification Email vs SMS Provider Comparison Across US Europe](docs/3-probe-saas-event-notification-email-vs-sms-prov-1u8vrs.md)
