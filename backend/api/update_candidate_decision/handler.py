"""POST /jobs/{job_id}/candidates/{candidate_id}/decision — human decision + at-most-once email."""

from rs_common import decisions, validate
from rs_common.authz import Caller, load_job_for
from rs_common.http import api_handler, json_body, path_id


@api_handler
def lambda_handler(event, caller: Caller):
    job_id = path_id(event, "job_id", "job")
    candidate_id = path_id(event, "candidate_id", "cand")
    job = load_job_for(caller, job_id)
    decision = validate.decision(json_body(event))
    return 200, decisions.apply_decision(job, candidate_id, decision, caller.sub)
