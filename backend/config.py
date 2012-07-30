#!/usr/bin/env python

# Configuration parameters for a particular deployment.

import os
import random

# Run in debug mode. Raw JS locally, pretty-print exceptions.
debug = True

# The timestamp of the current deployment, or a cache buster locally.
version_id = (
    (os.environ.get('VERSION_ID', '').split('.', 1) + [''])[0]
    or random.randint(0, 10**10))

# Beaker keys
session_encrypt_key = 'asdf'
session_validate_key = 'asdfasdf'

# Queues
apply_queue = 'apply-posts'
cleanup_queue = 'cleanup-shard'
notify_queue = 'notify-posts'
pending_queue = 'pending-posts'

# How long posts stay alive before being deleted. About 10 days.
ephemeral_lifetime_seconds = 60 * 255

# How long a user can be inactive (no heartbeat) before being logged out.
user_max_inactive_seconds = 180

# How frequently the shard cleanup task should run.
shard_cleanup_period_seconds = 60

# How long a token is alive before it should be replenished.
user_token_lifetime_seconds = 110 * 60

# Current version of the terms of service
terms_version = 1
