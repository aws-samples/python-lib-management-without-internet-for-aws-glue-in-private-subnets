#!/usr/bin/env python3
import os

from aws_cdk import (
    Stack,
    App,
    Environment
)
from application.application_stack import ApplicationStack

app = App()
ApplicationStack(app, "ApplicationStack",
                 cidr_block='192.168.50.0/24')

app.synth()

