# 0002. Channel-independent core

## Status

Accepted

## Context

The first user-facing interface for SmartCart is expected to be WhatsApp.
However, the product vision is a general grocery shopping engine (list
management, price comparison, route/detour-aware store recommendations)
that should eventually be reachable from other clients: a web app, a mobile
app, Telegram, or a plain API. WhatsApp itself carries real product risk
(see the WhatsApp Business Groups API feasibility question tracked
separately) that is independent of whether the underlying shopping logic is
sound.

If business logic (list parsing results, pricing, store comparison, basket
calculation, routing decisions) were implemented directly inside
WhatsApp-specific message handlers, then:

- Every domain rule would be entangled with WhatsApp's message format,
  webhook payloads, and delivery semantics.
- Supporting a second client would require duplicating or awkwardly
  extracting logic that was never designed to be reused.
- A WhatsApp-specific setback (API access, policy changes, rate limits)
  would put the entire product at risk, rather than just the messaging
  layer.
- Testing domain behavior would require simulating WhatsApp payloads instead
  of calling plain functions/objects.

## Decision

The shopping engine (list management, product handling, pricing, stores,
routing, preferences, and their orchestration) must be implemented as a
channel-independent core with no dependency on WhatsApp, Telegram, HTTP
request/response objects, or any other client-specific representation.

Clients (WhatsApp today, others later) are treated strictly as thin
adapters: they translate an inbound message/request into a call against the
core, and translate the core's output back into that channel's format. The
core has no knowledge of which channel invoked it.

This is a constraint on *dependency direction*, not a mandate to build
multi-channel abstractions, plugin systems, or speculative interfaces before
they are needed. Phase 0 introduces no channels and no core domain logic at
all; this ADR exists so that when domain logic is introduced (starting in
later phases), it is placed under `smartcart.core` (or sibling
domain-oriented packages) rather than inside a `whatsapp` or `channels`
package, and so that it is exercised by tests without needing a WhatsApp
integration.

## Consequences

- Domain/business logic must not import from, or depend on types defined
  by, any messaging/client integration package.
- A client integration package (e.g. a future `smartcart.channels.whatsapp`)
  may depend on the core, never the other way around.
- If WhatsApp Business Groups API turns out not to be viable, the shopping
  engine itself remains unaffected and reusable behind a different client.
- This ADR does not require building abstract client interfaces, dependency
  injection frameworks, or multi-tenant channel routing before there is a
  second real client — only that the dependency direction is respected.
