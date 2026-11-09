# EKO-1-12 custom-provider build stop record

Date: 2026-11-06
Worktree HEAD at the run: 7357baf99ff901a5f42072e146ed6397e69df99a

## Result

The versioned provider compiled and packaged with Maven, but the custom image did not build because its Java behavior test could not load the official image's complete runtime class path. No custom image was produced and no runtime criterion was verified.

Exact command:

`docker build -t localhost/eko-crm/keycloak:26.8.1-eko112 identity`

The initial run reached the behavior test after `mvn -q package`. Three class-path hypotheses were disproved:

1. `/opt/keycloak/lib/*:/opt/keycloak/lib/app/*` — `EventType` was not found.
2. `/opt/keycloak/lib/lib/main/*:/opt/keycloak/lib/app/*` — provider classes loaded, but `org.jboss.logging.Logger` was not found.
3. `/opt/keycloak/lib/lib/*/*:/opt/keycloak/lib/app/*` — `EventType` was again not found.

The role's three-hypothesis rule stops further class-path guesses. The final image therefore remains unbuilt, and fresh/restart/restore, provider selection/filtering, K-02/K-03/K-04, independent D-5, K-05 and the final-image gate-3 proposal are unchecked.

No credential, marker, identifier value, raw event, raw log or personal data is included here. No provider selection fallback was accepted, and no required event type or accepted exception was changed.
