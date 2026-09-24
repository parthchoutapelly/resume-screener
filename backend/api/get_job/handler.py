"""GET /jobs/{job_id} — one job with its effective requirements and where each came from."""

from rs_common import views
from rs_common.authz import Caller, load_job_for
from rs_common.http import api_handler, path_id


@api_handler
def lambda_handler(event, caller: Caller):
    job = load_job_for(caller, path_id(event, "job_id", "job"))
    return 200, views.job_view(job)
