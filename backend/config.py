#!/usr/bin/env python

# Configuration parameters for a particular deployment.

import os
import random

# Run in debug mode. Raw JS locally, pretty-print exceptions.
debug = True

# Run appstats RPC profiling for requests.
appstats = False

# The timestamp of the current deployment, or a cache buster locally.
version_id = (
    (os.environ.get('VERSION_ID', '').split('.', 1) + [''])[0]
    or random.randint(0, 10**10))

# Is this running in the dev_appserver or production?
is_dev_appserver = os.environ.get('SERVER_SOFTWARE', '').startswith('Dev')

# Queues
apply_queue = 'apply-posts'
cleanup_queue = 'cleanup-shard'
notify_queue = 'notify-posts'
pending_queue = 'pending-posts'

# How long posts stay alive before being deleted. About 10 days.
ephemeral_lifetime_seconds = 60 * 60 * 256

# How long a user can be inactive (no heartbeat) before being logged out.
user_max_inactive_seconds = 90

# How frequently the shard cleanup task should run.
shard_cleanup_period_seconds = 60

# How long a token is alive before it should be replenished.
user_token_lifetime_seconds =  6 * 60 * 60  # 6 hours

# Current version of the terms of service
terms_version = 1

# Import all secret keys
from secrets import *
