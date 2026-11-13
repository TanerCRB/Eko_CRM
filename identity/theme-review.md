# Login theme review record (ADR-0003-C31)

The `eko-crm` login theme (`identity/themes/eko-crm/`) overrides parts of its parent, the
`keycloak.v2` login theme shipped in the official Keycloak image. The parent changes with Keycloak
releases without notice, so every change of the base image version in `identity/Dockerfile`
(patch releases included) and every change to the theme is reviewed before deployment
(ADR-0003 addendum of 2026-11-12, *Upgrade review duty*). Each review appends one entry below;
the newest entry is the last one. The static check
`backend/tests/static/test_eko201_k07_theme.py` compares the latest entry's Keycloak version with
the base image version and its two listings with the templates and message keys present in the
theme.

Each entry names the Keycloak version it was reviewed against, lists every overridden template
and every overridden message key, and records the outcome of comparing each one with the parent's
version in that image.

## 2026-11-12 — reviewed against Keycloak 26.8.1

- Overridden templates: none.
- Overridden message keys: `loginTitleHtml`, `loginAccountTitle`, `loginTotpTitle`,
  `code-clipboard-label`, `code-copy-label`, `code-copy-success`, `code-copy-failure`.
- Parent compared: `theme/keycloak.v2/login` and `theme/base/login` in
  `lib/lib/main/org.keycloak.keycloak-themes-26.8.1.jar` of `quay.io/keycloak/keycloak:26.8.1`.
- Outcome: no template is overridden, so no parent template drift applies. The parent's
  `template.ftl` renders `loginTitleHtml` through `kcSanitize(...)` before output, so the
  overridden value stays sanitized; the other keys are plain message text. `loginTitle` keeps the
  parent's Polish text with the realm display name. `loginTotpTitle` replaces the parent's Polish
  text, which kept the English words "Mobile Authenticator". The four `code-*` keys have no Polish
  text in the parent (English fallback) and are used by the parent's `field.ftl`/`code.ftl` copy
  controls. The stylesheet `css/eko-crm.css` is added after the parent's `css/styles.css` and only
  sets colours, the page background and the header text.
