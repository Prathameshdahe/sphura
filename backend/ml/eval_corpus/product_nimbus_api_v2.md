# Nimbus Storage API v2 — Developer Reference

## Overview

The Nimbus Storage API lets applications store and retrieve files, called objects, in buckets over HTTPS. All endpoints in this reference live under the base URL https://api.nimbus.example/v2 and accept and return JSON unless stated otherwise. Version 2 was released in March 2023 and remains supported until 30 June 2026.

## Authentication

Every request must include an API key in the X-Nimbus-Key header. Keys are created in the console under Settings → Access Keys and are shown only once. Each key has a scope of read, write or admin. A read key can list buckets and download objects but cannot upload or delete. Requests without a valid key fail with error E-401-KEY, and requests that use a key outside its scope fail with E-403-SCOPE.

For server-to-server integrations, keys can be restricted to a list of IP addresses. A request from an address that is not on the list is rejected even if the key is otherwise valid.

## Buckets

Create a bucket with POST /v2/buckets and a body containing a name and a region. Bucket names must be 3 to 63 characters long, use only lowercase letters, digits and hyphens, and be unique across all Nimbus customers. The available regions are eu-west-1, us-east-2 and ap-south-1. A bucket's region cannot be changed after creation; to move data, create a new bucket and copy the objects.

## Uploading objects

Small files up to 64 MB can be uploaded in a single PUT /v2/buckets/{bucket}/objects/{key} request. Larger files must use multipart upload: start with POST /v2/buckets/{bucket}/uploads, send each part with PUT and a part number, and finish with POST /v2/buckets/{bucket}/uploads/{uploadId}/complete. Each part except the last must be at least 5 MB, and an upload can have at most 10,000 parts. Incomplete multipart uploads are deleted automatically after 7 days.

Every successful upload returns an ETag, a checksum of the stored content. Clients should compare the ETag with a locally computed MD5 hash to detect corruption in transit.

## Downloading and listing

Download an object with GET /v2/buckets/{bucket}/objects/{key}. Range requests are supported through the standard Range header, which is useful for resuming interrupted downloads or streaming video. List objects with GET /v2/buckets/{bucket}/objects; results are returned in pages of up to 1,000 keys, and the response includes a next_cursor value when more results are available.

## Rate limits

Each API key may make up to 600 requests per minute. Bursts above this limit receive HTTP 429 with error code E-429-RATE and a Retry-After header indicating how many seconds to wait. Uploads and downloads count as one request each, regardless of size. Clients should retry with exponential backoff starting at one second and should never retry more than five times.

## Error codes

Errors are returned with an appropriate HTTP status and a JSON body containing code and message fields.

| Code | Meaning |
|---|---|
| E-401-KEY | The API key is missing, malformed or revoked |
| E-403-SCOPE | The key does not have the required scope |
| E-403-IP | The request came from an IP address that is not allowed for this key |
| E-404-BUCKET | The bucket does not exist or belongs to another account |
| E-409-NAME | A bucket with this name already exists |
| E-413-SIZE | The object is too large for a single PUT; use multipart upload |
| E-429-RATE | Too many requests; retry after the time in Retry-After |
| E-503-MAINT | The region is in scheduled maintenance |

## Webhooks

Nimbus can call your server when objects are created or deleted. Register a webhook URL per bucket in the console. Each webhook request carries an X-Nimbus-Signature header containing an HMAC-SHA256 signature of the body, computed with the webhook secret; reject any request whose signature does not match. Failed deliveries are retried up to eight times over 24 hours.

## Versioning and deletion

When versioning is enabled on a bucket, overwriting or deleting an object keeps the previous version, which can be restored for up to 30 days. Deleting a bucket requires it to be empty and fails with E-409-NOTEMPTY otherwise.

## Client libraries

Official client libraries are available for Python, JavaScript, Go and Java. They handle multipart uploads, retries with backoff and webhook signature checks automatically, so most applications never need to call the HTTP endpoints directly. Community libraries exist for other languages but are not reviewed by Nimbus.
