"""Entry point for `cdk deploy`. The real description is in stack.py."""

import os

import aws_cdk as cdk

from stack import HousePartyStack

app = cdk.App()
HousePartyStack(
    app,
    "HouseParty",
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
    ),
)
app.synth()
