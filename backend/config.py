#!/usr/bin/env python

# Configuration parameters for a particular deployment.

import os
import random


debug = True


# The timestamp of the current deployment, or a cache buster locally.
version_id = (
    (os.environ.get('VERSION_ID', '').split('.', 1) + [''])[0]
    or random.randint(0, 10**10))

# Beaker keys
session_encrypt_key = 'asdf'
session_validate_key = 'asdfasdf'

# Queues
pending_queue = 'pending-posts'
apply_queue = 'apply-posts'
notify_queue = 'notify-posts'

# How long posts stay alive before being deleted.
ephemeral_lifetime_seconds = 20 # 86400 * 255

# What URL prefix shortlinks should point to.
short_url_prefix = 'http://8-bits.us/'
