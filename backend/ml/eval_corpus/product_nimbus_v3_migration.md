# Migrating from Nimbus Storage API v2 to v3

## Why v3

Nimbus Storage API v3 became generally available in September 2025. It introduces short-lived access tokens, larger single uploads, higher rate limits and a consistent error format. Version 2 will stop accepting requests on 30 June 2026, so all integrations should migrate before that date. This guide lists every breaking change and the order in which we recommend making them.

## New base URL

All v3 endpoints live under https://api.nimbus.example/v3. Paths are otherwise unchanged for buckets and objects, so in most client libraries the migration starts by changing a single configuration value. The v2 and v3 APIs read and write the same buckets, which means you can migrate one service at a time.

## Authentication changes

The X-Nimbus-Key header is no longer accepted in v3. Instead, exchange your API key for an access token by calling POST /v3/auth/token, then send the token in the standard Authorization header as a bearer token. Tokens expire after 60 minutes; request a new one when you receive error NMB-1102. Long-lived API keys are still used, but only for the token exchange, which reduces the damage if a request log leaks.

IP allow-lists continue to work exactly as before.

## Uploads

The single-request upload limit has been raised from 64 MB to 256 MB. Multipart upload is still required above that size, and the minimum part size has increased from 5 MB to 8 MB to reduce the number of requests for very large files. Incomplete multipart uploads are now kept for 3 days instead of 7, so long-running uploads should be resumed promptly.

v3 also returns a SHA-256 checksum in the X-Nimbus-Checksum header in addition to the ETag. We recommend switching integrity checks to SHA-256, because the ETag of a multipart upload is not an MD5 hash of the whole file.

## Rate limits

The default limit is now 1,500 requests per minute per project rather than per key. Projects that need more can request an increase in the console. When the limit is exceeded, v3 returns HTTP 429 with error NMB-1429 and a Retry-After header. Because the limit is shared across all keys in a project, splitting traffic over several keys no longer increases throughput.

## New error format

Every v3 error body has the fields error.code, error.message and error.request_id. Codes now share the NMB prefix and a four-digit number. The most common mappings from v2 are:

| v2 code | v3 code | Meaning |
|---|---|---|
| E-401-KEY | NMB-1101 | Invalid or revoked credentials |
| none | NMB-1102 | Access token expired |
| E-403-SCOPE | NMB-1204 | Insufficient scope |
| E-403-IP | NMB-1205 | IP address not allowed |
| E-404-BUCKET | NMB-1404 | Bucket not found |
| E-413-SIZE | NMB-1413 | Object too large for a single upload |
| E-429-RATE | NMB-1429 | Rate limit exceeded |

Include error.request_id when you contact support; it lets the support team find the exact request in the logs.

## Webhooks

Webhook signatures now use the header X-Nimbus-Signature-256 and include a timestamp, in the format t=<unix time>,v1=<signature>. Reject requests whose timestamp is more than five minutes old to protect against replay attacks. During the migration period Nimbus sends both the old and the new signature headers.

## SDK versions

The official client libraries support v3 from the following releases: Python 4.0, JavaScript 5.2, Go 3.1 and Java 4.4. Earlier releases only speak v2. Upgrading the library handles the token exchange and refresh automatically, so applications that use an SDK rarely need code changes beyond error handling.

## Recommended migration order

First, switch the base URL and authentication in a staging environment and run your integration tests. Second, update error handling to recognise the NMB codes, since code that checks for E-429-RATE will silently stop retrying. Third, move integrity checks to SHA-256. Finally, update webhook verification and remove support for the old signature header after 30 June 2026.
