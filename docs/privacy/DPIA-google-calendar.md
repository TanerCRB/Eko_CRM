# Data Protection Impact Assessment - Google Calendar integration

**Status:** Accepted for ADR-0006 addendum analysis only; not an authorisation for real customer data  
**Decision date:** 2026-10-29  
**Scope:** EKO-1-16 / issue #46

## Decision

The human accepted this assessment for the ADR-0006 addendum. Every environment remains limited to synthetic customer data. This document does not approve Google Calendar production processing, private Gmail calendars, or EKO-5 implementation with real customer data.

## Processing

Eko_CRM may mirror a sales visit to the representative's primary Google Calendar. The planned event contains the customer name, visit address, one eligible contact phone number, visit start/end time, and opaque visit/environment identifiers. It excludes customer e-mail addresses, tax identifiers, free-text notes/actions, attendees, invitations, notifications, and Google account identity data in Eko_CRM.

Data subjects are customers, sales representatives, and managers. Recipients are the linked representative's calendar account, Google Calendar API, and company IT staff administering the OAuth client.

## Risks And Controls

| Risk | Required control |
|---|---|
| Residual customer data in a former or inaccessible calendar | Synthetic data only until legal, contractual, offboarding, and recovery evidence is approved. |
| Ownership hold prevents erasure | Erasure jobs run despite ordinary Ownership suspension; unavailable removals have a no-customer-value record and same-calendar take-up. |
| Lost access blocks other work | A suspended sweep cannot hold a later job for the visit. |
| Duplicate or untracked calendar event | Pending create remains assigned to its original calendar and a new calendar uses a new identifier. |
| Unproven event provenance | A marker/prefix-only discovery is unresolved and never automatically deleted before validated provenance. |
| Failed recorded-owner read | Candidate remains unchanged; verification retries; notice contains no customer value; no link-wide Ownership hold occurs before success. |

## Conditions Before Real Data

Before real customer data may be processed, the controller must provide and approve:

1. Article 6 legal basis, transparency notice, controller and privacy/DPO contact.
2. Google contractual role, hosting location, transfer and subprocessor assessment.
3. A decision on private Gmail calendar acceptability, retention, offboarding, and an event that cannot be removed.
4. EKO-5 implementation evidence for field minimisation, logging, deletion, recovery, access loss, calendar switching, notices, and validated provenance.
5. Procedures for data-subject rights, incidents, and re-assessment after a new data category, scope, recipient, retention rule, calendar type, or purpose.

## Evidence

- ADR-0005 personal-data decision.
- ADR-0006 dated EKO-1-16 addendum merged in PR #73.
- `tests/doc-checks/EKO-1-16.sh`, 9 contrasts passing in PR #73.

## Limits

This engineering governance assessment is not legal advice and is not evidence of GDPR compliance until all conditions for real-data processing are met.
