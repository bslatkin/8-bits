#!/usr/bin/env python

# Configuration parameters for a particular deployment.

debug = True

# URL signing key
url_signature_key = 'foobartime'

# Beaker keys
session_encrypt_key = 'asdf'
session_validate_key = 'asdfasdf'

# Queues
pending_queue = 'pending-posts'
apply_queue = 'apply-posts'
notify_queue = 'notify-posts'
