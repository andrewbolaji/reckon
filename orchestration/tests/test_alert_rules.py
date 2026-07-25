"""Local and in-cluster alert rules must not drift apart.

The same two files have to agree for the demo to mean anything: a failure
reproduced locally should fire the same alert the EKS cluster would fire. They
are separate files because one is a Prometheus config and the other is Helm
values, so nothing but a test keeps them honest.
"""

import yaml

from orchestration.resources import REPO_ROOT

LOCAL_RULES = REPO_ROOT / "observability" / "prometheus" / "alerts.yml"
CLUSTER_VALUES = REPO_ROOT / "infra" / "helm" / "monitoring" / "values.yaml"

EXPECTED_ALERTS = {
    "PipelineFreshnessBreach",
    "PipelineDbtTestFailure",
    "PipelineRunFailure",
}


def _rules(groups):
    return {rule["alert"]: rule for group in groups for rule in group["rules"]}


def local_rules():
    return _rules(yaml.safe_load(LOCAL_RULES.read_text())["groups"])


def cluster_rules():
    values = yaml.safe_load(CLUSTER_VALUES.read_text())
    return _rules(values["additionalPrometheusRulesMap"]["reckon-pipeline"]["groups"])


def test_both_rule_sets_define_the_same_alerts():
    assert set(local_rules()) == EXPECTED_ALERTS
    assert set(cluster_rules()) == EXPECTED_ALERTS


def test_expressions_match_between_local_and_cluster():
    local, cluster = local_rules(), cluster_rules()
    for name in EXPECTED_ALERTS:
        assert local[name]["expr"] == cluster[name]["expr"], f"{name} expr drifted"


def test_run_failure_alert_watches_the_metric_the_sensors_push():
    """orchestration/sensors.py and report_run.py both push pipeline_run_failed."""
    assert local_rules()["PipelineRunFailure"]["expr"] == "pipeline_run_failed > 0"


def test_freshness_breach_still_matches_the_48_hour_trust_gate():
    from copilot.trust_gate import FRESHNESS_ERROR_HOURS

    expr = local_rules()["PipelineFreshnessBreach"]["expr"]
    assert str(FRESHNESS_ERROR_HOURS * 3600) in expr
