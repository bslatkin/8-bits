#!/usr/bin/env python
#
# Copyright 2010 Brett Slatkin, Nathan Naze
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
email_digest_queue = 'email-digests'

# How long posts stay alive before being deleted. About 10 days.
ephemeral_lifetime_seconds = 60 * 60 * 256

# How long a user can be inactive (no heartbeat) before being logged out.
user_max_inactive_seconds = 90

# How frequently the shard cleanup task should run.
shard_cleanup_period_seconds = 60

# How long a token is alive before it should be replenished.
user_token_lifetime_seconds = 6 * 60 * 60    # 6 hours

# Current version of the terms of service
terms_version = 1

# Name of the site to use in alt-text and various titles
site_name = '8-bits of ephemera'

# Email address to use for sending notification emails.
notification_from_email = '8-bits of ephemera <%s.appspotmail.com>' % (
    os.environ.get('APPLICATION_ID', 'test-app'))

# Template used for shard URLs
shard_url_template = 'https://%s.appspot.com/chat/' % (
    os.environ.get('APPLICATION_ID', '')) + '%s'

# Hostname to use for resources in emails
email_resource_host_prefix = '//%s.appspot.com' % (
    os.environ.get('APPLICATION_ID', ''))

# How often to email users a digest of activity
default_notify_period_seconds = 6 * 60 * 60  # 6 hours

# Beaker keys, overridden by the 'secrets' module.
session_encrypt_key = 'for-tests'
session_validate_key = 'for-tests'

# Import all secret keys and config overrides if we're in the actual container.
if os.environ.get('SERVER_SOFTWARE'):
    from secrets import *
