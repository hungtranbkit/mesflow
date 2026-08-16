"""Phase 3 Predictive / AI: pure unit tests (no PostgreSQL) -- statistics
helpers and AI provider validation/safety."""
import json
import os
os.environ.setdefault('MESFLOW_SECRET_KEY','test')
from mesflow.domain.predictive import Confidence,linear_regression,mad,mean,median,stdev
from mesflow.services.forecast_service import risk_for_days
from mesflow.services.ai_incident_service import (
 AIProvider,DisabledAIProvider,IncidentAIService,_validate_structured,build_context,
)


def test_linear_regression_perfect_line():
 points=[(0,10),(1,12),(2,14),(3,16)]
 slope,intercept,r2=linear_regression(points)
 assert abs(slope-2)<1e-9 and abs(intercept-10)<1e-9 and r2>0.999


def test_linear_regression_flat_line_has_zero_slope():
 points=[(0,50),(1,50),(2,50),(3,50)]
 slope,intercept,r2=linear_regression(points)
 assert slope==0


def test_linear_regression_needs_at_least_two_points():
 assert linear_regression([])==(0.0,0.0,0.0)
 assert linear_regression([(0,5)])==(0.0,0.0,0.0)


def test_mad_is_robust_to_a_single_outlier():
 values=[10,11,9,10,11,9,10,100]
 assert stdev(values)>mad(values)  # classic MAD-vs-stdev outlier resistance


def test_risk_for_days_bands():
 assert risk_for_days(None)=='INFO'
 assert risk_for_days(-1)=='INFO'
 assert risk_for_days(3)=='HIGH'
 assert risk_for_days(10)=='MEDIUM'
 assert risk_for_days(20)=='LOW'
 assert risk_for_days(40)=='INFO'


# --- AI provider / structured-output validation ---------------------------

def test_disabled_provider_is_never_available():
 p=DisabledAIProvider()
 assert p.available() is False


def test_validate_structured_accepts_well_formed_json():
 raw=json.dumps({'summary':'x','evidence':['a'],'likely_causes':['b'],'uncertainties':[],
                  'suggested_checks':[{'action':'check disk','risk':'SAFE_CHECK','reason':'r'}]})
 data,err=_validate_structured(raw)
 assert err is None and data['summary']=='x'
 assert data['suggested_checks'][0]['risk']=='SAFE_CHECK'


def test_validate_structured_rejects_missing_fields():
 data,err=_validate_structured(json.dumps({'summary':'x'}))
 assert data is None and err=='INVALID_OUTPUT'


def test_validate_structured_rejects_garbage():
 data,err=_validate_structured('not json at all {{{')
 assert data is None and err=='INVALID_OUTPUT'


def test_validate_structured_clamps_unknown_risk_label_to_safe_check():
 raw=json.dumps({'summary':'x','evidence':[],'likely_causes':[],'uncertainties':[],
                  'suggested_checks':[{'action':'restart everything','risk':'DELETE_PRODUCTION','reason':'r'}]})
 data,err=_validate_structured(raw)
 assert err is None
 assert data['suggested_checks'][0]['risk']=='SAFE_CHECK'  # never trust an invented/unsafe label


def test_validate_structured_accepts_fenced_json_block():
 raw='```json\n'+json.dumps({'summary':'x','evidence':[],'likely_causes':[],'uncertainties':[],'suggested_checks':[]})+'\n```'
 data,err=_validate_structured(raw)
 assert err is None and data['summary']=='x'


def test_build_context_is_bounded_and_sanitizes_secrets():
 alert={'title':'PostgreSQL DOWN','severity':'CRITICAL','component':'POSTGRESQL','message':'x','opened_at':'now'}
 diag={'note':'password=hunter2 token=abc123'}
 ctx=build_context(alert,diag,[],max_chars=50)
 assert len(ctx)<=50
 full_ctx=build_context(alert,diag,[])
 assert 'hunter2' not in full_ctx and 'abc123' not in full_ctx


class _FakeProvider(AIProvider):
 name='fake'
 def __init__(self,response=None,raise_exc=None):self.response=response;self.raise_exc=raise_exc
 def available(self):return True
 def analyze(self,context_text):
  if self.raise_exc:raise self.raise_exc
  return self.response


def test_ai_service_never_executes_anything_from_ai_output():
 """section 82: even if the model literally returns an instruction to
 restart something, there must be no code path from that text to any
 subprocess/infrastructure-mutation call. Asserted structurally: the
 service module never imports subprocess/os.system, and its only network
 call is the single, hardcoded, read-only-response Anthropic Messages POST
 -- there is no code that takes AI output and feeds it into another
 request or command."""
 import inspect
 import mesflow.services.ai_incident_service as mod
 src=inspect.getsource(mod)
 assert 'subprocess' not in src
 assert 'os.system' not in src
 assert 'eval(' not in src and 'exec(' not in src
