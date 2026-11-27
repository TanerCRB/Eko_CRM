"""EKO-3-10 carriers: EKO-3-05's (the shipped `create_app()` on real PostgreSQL 18 and the local
OIDC stub, a real session per synthetic staff member, the application's clock the test's), bound
here by name. Every value is synthetic (ADR-0005).
"""

from tests.runtime.eko305 import conftest as eko305

pg = eko305.pg
clean = eko305.clean
stub = eko305.stub
clock = eko305.clock
make_app = eko305.make_app
browser_for = eko305.browser_for
clean_customers = eko305.clean_customers
crm = eko305.crm
