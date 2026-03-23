"""Vulture whitelist — false positives."""

# TYPE_CHECKING import used in type annotation on line 45
boto3_type  # noqa

# while True + break pattern: code after loop IS reachable via break
entry  # noqa
