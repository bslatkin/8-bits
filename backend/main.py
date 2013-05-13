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

"""Entry point."""

import logging

from google.appengine.ext import webapp

# Local libs
from beaker import middleware
import config
import jobs
import landing
import posts
import presence
import send_email
import topics


class WarmupHandler(webapp.RequestHandler):
    """Handles warm-up requests by doing nothing."""

    def get(self):
        pass


class DebugLoggingMiddleware(object):
    """Sets the log level to debug on each request. Used in dev_appserver."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        logging.getLogger().setLevel(logging.DEBUG)
        return self.app(environ, start_response)


LOCAL_ROUTES = [
    (r'/_ah/warmup', WarmupHandler),
]

ROUTES = (
    LOCAL_ROUTES +
    jobs.ROUTES +
    landing.ROUTES +
    posts.ROUTES +
    presence.ROUTES +
    send_email.ROUTES +
    topics.ROUTES +
    []
)

APP = webapp.WSGIApplication(ROUTES, debug=config.debug)

APP = middleware.SessionMiddleware(APP, {
    'session.type': 'cookie',
    'session.key': '8bits',
    'session.httponly': True,
    'session.secure': not config.debug,
    'session.cookie_expires': False,
    'session.validate_key': config.session_validate_key,
    'session.encrypt_key': config.session_encrypt_key,
})

if config.appstats:
    APP = recording.appstats_wsgi_middleware(APP)

if config.debug:
    APP = DebugLoggingMiddleware(APP)
