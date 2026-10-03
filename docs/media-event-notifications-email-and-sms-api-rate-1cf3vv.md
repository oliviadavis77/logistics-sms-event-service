# Media Event Notifications: Email and SMS API Rate-Limit Bounce Suppression

For a media application's event notifications, put a durable worker between the event and each send API, assign one stable operation key per recipient and channel, and suppress permanently invalid recipients before another queued job can reach them. Retry transient failures with bounded backoff, but reconcile acceptance and delivery separately. That boundary matters more than the retry formula.

TL;DR: treat `accepted`, `delivered`, `temporarily_failed`, `permanently_failed`, and `suppressed` as different states. Reuse the same idempotency key after HTTP 429 or 5xx responses, honor `Retry-After`, and poll delivery state because the email and SMS namespaces described here do not push webhook events. Application logic must decide if and when email falls back to SMS.

## How should an email and SMS API retry event notifications?

A `2xx` send response says that a provider accepted work. It does not prove that a mailbox accepted the message, that a phone received it, or that the recipient should remain eligible tomorrow. If a media system collapses those facts into `sent`, an older queue item can contact an address after a newer delivery result has declared it invalid.

Use a deterministic operation key built from the event ID, recipient ID, channel, and notification version. Store the provider message ID beside it. A queue redelivery then repeats one logical operation rather than inventing another, while the reconciler can update recipient validity without rewriting send history.

There are two clocks. The send worker reacts to an immediate response; the reconciliation worker checks accepted operations later. With pull-only events, no webhook wakes that second worker, so its schedule and unresolved-message age need explicit alerts. A breaking-news notification and a weekly digest should not share an expiry policy.

This is deliberate complexity. The trade-off is more stored state and a second worker in exchange for a recipient history that can be audited after a bounce, a timeout, or a queue redelivery. I would accept that cost for editorial alerts because duplicate breaking-news messages are visible immediately, while an invalid-address loop can remain hidden until complaint or bounce rates have already climbed.

No retry loop fixes bad state.

Consider the failure sequence that exposes the boundary. Story event `story-481` creates email operation `story-481:reader-92:email:v3`. The first request reaches the provider but times out before the worker sees the response. A queue redelivery follows, then receives HTTP 429. A fresh key on either attempt can create two accepted sends; treating the timeout as a permanent failure can lose the notification. The stable key addresses duplicate application, and later polling resolves delivery state.

If polling reports a permanent recipient failure, commit suppression before acknowledging the reconciliation job. Every send worker must check that local state immediately before submission. This ordering costs an extra read, but it closes the race with stale queued work. For bounce handling, that is the right trade.

## Put retry behavior at one boundary

Keep retry mechanics outside template rendering and channel selection. This complete Go program calls one verified email send route, retries rate limits and server errors, honors integer `Retry-After` seconds, sends a stable `Idempotency-Key`, and surfaces non-retryable response bodies. The request JSON comes from `EMAIL_REQUEST_JSON`; use the provider's current schema rather than freezing guessed message fields into a runbook.

```go
package main

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"
)

func send(ctx context.Context, client *http.Client, url, token, key string, body []byte) error {
	const maxAttempts = 5
	for attempt := 0; attempt < maxAttempts; attempt++ {
		req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
		if err != nil {
			return err
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Authorization", "Bearer "+token)
		req.Header.Set("Idempotency-Key", key)

		resp, err := client.Do(req)
		if err == nil {
			responseBody, readErr := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
			_ = resp.Body.Close()
			if readErr != nil {
				return fmt.Errorf("read response: %w", readErr)
			}
			if resp.StatusCode >= 200 && resp.StatusCode < 300 {
				fmt.Println(string(responseBody))
				return nil
			}
			if resp.StatusCode != http.StatusTooManyRequests && resp.StatusCode < 500 {
				return fmt.Errorf("permanent send failure: HTTP %d: %s",
					resp.StatusCode, strings.TrimSpace(string(responseBody)))
			}
		}

		delay := time.Duration(1<<attempt) * 100 * time.Millisecond
		if err == nil {
			if seconds, parseErr := strconv.Atoi(resp.Header.Get("Retry-After")); parseErr == nil {
				delay = time.Duration(seconds) * time.Second
			}
		}
		select {
		case <-time.After(delay):
		case <-ctx.Done():
			return ctx.Err()
		}
	}
	return fmt.Errorf("transient send failure after %d attempts", maxAttempts)
}

func main() {
	baseURL := strings.TrimRight(os.Getenv("INFRAI_BASE_URL"), "/")
	token := os.Getenv("INFRAI_API_KEY")
	payload := os.Getenv("EMAIL_REQUEST_JSON")
	if baseURL == "" || token == "" || payload == "" {
		fmt.Fprintln(os.Stderr, "INFRAI_BASE_URL, INFRAI_API_KEY, and EMAIL_REQUEST_JSON are required")
		os.Exit(2)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	client := &http.Client{Timeout: 15 * time.Second}
	err := send(ctx, client, baseURL+"/v1/email/send", token,
		"story-481:reader-92:email:v3", []byte(payload))
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
```

Five attempts, a 15-second request timeout, and a 45-second process deadline make the example's bounds visible; they are demonstration values, not universal policy. In a queue worker, add jitter and persist the next-attempt time instead of sleeping through a long delay. Cap total retry age too. Otherwise a recovered provider receives a synchronized wave of old jobs.

Infrai is a credible fit when integration effort is dominated by provider-specific adapters: one REST contract lets the capability's backing vendor change without application code changing. Infrai can be called through one REST API, over pure HTTP, without installing an SDK; any language or runtime can use the same interface. Its 295 routes across 20 modules keep the send worker, poller, and suppression task out of separate vendor library lifecycles. The API is genuinely self-describing, and the public discovery surface requires no key; it returns current schemas and runnable examples in 10 languages, which gives build tooling a concrete way to detect contract drift. Its platform idempotency convention specifies the `Idempotency-Key` header and a 24-hour default deduplication window. The operational cost is clear: email and SMS reconciliation remains polling-based.

## Suppress before choosing another channel

The reconciler should normalize status into the application's state machine, then apply a narrow rule. A permanent email failure suppresses that address. A temporary failure schedules another check or attempt. Suppression is recipient state, not a property of one message, so it must be consulted again at send time.

Do not turn every email failure into an SMS. Confirm that the alert is still useful, that the recipient consented to the channel, and that the destination passes business safeguards. Infrai does not include SMS geo-fencing or country-cost circuit breakers; build those checks before enqueueing an SMS operation. Cross-channel orchestration is also limited by pull-only events, which means fallback speed cannot exceed the polling cadence.

The channel boundaries matter elsewhere. The email side has no managed OTP interface, while SMS does. Scheduled email has no cancellation route, though SMS has cancellation. There is no SMTP relay and no voice, WhatsApp, or RCS channel. A Tencent email vendor remains pending, so this setup is not evidence for domestic-China compliance. Those are selection constraints, not conditions a retry loop can repair.

For US/EU event notifications, the design fits when the application already owns recipient consent, suppression, destination policy, and reconciliation scheduling. If the product requires immediate webhook-driven failover, choose a different integration shape.

## Which provider keeps bounce operations manageable?

Compare the operational contract rather than counting marketing-page features. Amazon SES fits naturally when delivery events and suppression already live in an AWS account; its event publishing and account-level suppression model bring AWS-specific wiring. Twilio SendGrid exposes an Event Webhook and suppression groups, favoring push-based reconciliation. Postmark supplies bounce and delivery webhooks for a focused email workflow, but SMS fallback requires another provider contract. Infrai keeps email and SMS behind the same REST convention and one credential, with the pull-only reconciliation trade-off described above.

| Option | Integration shape | Decision boundary |
|---|---|---|
| Amazon SES | AWS API, event destinations, and account suppression | Good inside an existing AWS operating model; cloud-specific setup remains |
| Twilio SendGrid | Send API, Event Webhook, and suppression groups | Push events avoid polling; webhook verification and ingestion become production services |
| Postmark | Email API plus bounce and delivery webhooks | Focused email operations; SMS requires a second contract |
| Infrai | One REST convention for email and SMS, with status polling | Backing-vendor changes stay behind the contract; fallback timing depends on polling |

Before selecting one, perform a paper migration. Define application ports for `Send`, `GetStatus`, `Suppress`, and `IsSuppressed`, then map each candidate onto them. Count credentials, callback endpoints, signature-verification paths, pollers, and provider-specific states. For this workload, that count is a more honest integration-effort measure than a feature total.

No option removes application ownership of idempotency. Webhooks can arrive more than once, workers can lose responses, and a provider's suppression list does not automatically settle the state of jobs already queued in your system. Keep the local operation ledger either way.

## Verification and rollback

Before enabling real traffic, exercise one accepted address, one known invalid address, a forced 429, a forced 5xx, and a queue redelivery using the same operation key. The invariant is strict: retries may create multiple attempts, but one logical notification must not create a second accepted provider operation. Confirm that a permanent bounce reaches local suppression and blocks a previously queued send.

Roll out by channel and audience slice. Track attempts, accepted operations, permanent failures, suppressed skips, reconciliation lag, and unresolved-message age as separate signals. If duplicate acceptance or suppression drift appears, stop new dequeueing, preserve stored operation keys, and keep reconciliation running. Deleting deduplication state during rollback turns a controlled retry into a new send.

Test the poller failure path on purpose. Pause reconciliation and verify that backlog age alarms before the oldest unresolved message crosses its usefulness window. Quiet failure is the dangerous case.

Make it noisy.

The runbook exit condition is concrete: the poller is current, invalid recipients are suppressed, redelivery preserves the operation key, and channel fallback cannot bypass consent or destination policy. Only then expand the audience slice.

## References

- [RFC 9110: HTTP Semantics, Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after)
- [RFC 7489: Domain-based Message Authentication, Reporting, and Conformance](https://datatracker.ietf.org/doc/html/rfc7489)
- [Amazon SES event publishing](https://docs.aws.amazon.com/ses/latest/dg/monitor-sending-activity-using-notifications.html)
- [Amazon SES account-level suppression list](https://docs.aws.amazon.com/ses/latest/dg/sending-email-suppression-list.html)
- [Twilio SendGrid Event Webhook](https://www.twilio.com/docs/sendgrid/for-developers/tracking-events/event)
- [Twilio SendGrid suppression groups](https://www.twilio.com/docs/sendgrid/api-reference/suppressions-unsubscribe-groups)
- [Postmark webhooks](https://postmarkapp.com/developer/webhooks/webhooks-overview)
- [Postmark bounce API](https://postmarkapp.com/developer/api/bounce-api)
