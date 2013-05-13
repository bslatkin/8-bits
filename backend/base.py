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

"""Base class and functionality for request handlers, common utilities."""

import cgi
import json
import logging
import os
import traceback

from google.appengine.ext import webapp
from google.appengine.ext.webapp import template

# Local libs
import config
import models


class Error(Exception):
    """Base class for exceptions."""

class MissingParameterError(Error):
    """A required parameter was missing."""

class BadParameterValueError(Error):
    """A parameter has a bad type."""

class NotAuthorizedError(Error):
    """The user is not authorized to do this action."""

class TopicShardError(Error):
    """Topic shards cannot be used in this way."""

class PostError(Error):
    """A posting could not be made."""


class BaseHandler(webapp.RequestHandler):
    """Base handler for handling web requests."""

    # Allow requests with the GET verb.
    get_enabled = True

    # Allow requests with the POST verb.
    post_enabled = True

    def _require_xsrf_token(self):
        # TODO(bslatkin): Rotate the token periodically.
        if 'xsrf_token' not in self.session:
            self.session['xsrf_token'] = models.human_uuid()
            self.session.save()

    def get(self, *args):
        if not self.get_enabled:
            self.response.set_status(405)
            return
        self.session = self.request.environ['beaker.session']
        self._require_xsrf_token()
        self.handle_request(*args)

    def post(self, *args):
        if not self.post_enabled:
            self.response.set_status(405)
            return

        self.session = self.request.environ['beaker.session']
        self._require_xsrf_token()

        found_token = self.request.get('xsrf_token')
        if found_token != self.session['xsrf_token']:
            logging.warning('XSRF token invalid! session=%r', self.session)
            self.response.headers['X-Why'] = 'Bad XSRF token'
            self.response.set_status(403)
            return

        self.handle_request(*args)

    def handle_request(self, *args):
        raise NotImplementedError()

    def get_required(self,
                     name,
                     type_constructor,
                     default=None,
                     repeated=False,
                     html_escape=False):
        """Retrieves a required parameter with the given name and default."""
        value_list = self.request.get_all(name)

        if default is None:
            if not value_list:
                raise MissingParameterError(
                    'Parameter "%s" is required' % name)
        else:
            value_list.append(default)

        out_list = []
        for value in value_list:
            try:
                value = type_constructor(value)
            except ValueError:
                raise BadParameterValueError(
                    'Parameter "%s" has an invalid value: %r' % (name, value))

            if html_escape:
                value = cgi.escape(value)

            out_list.append(value)

        if repeated:
            return out_list
        return out_list[0]

    def require_active_login(self):
        """Raises an error if the user does not have an active connection."""
        import presence     # Break circular import
        login_record = models.LoginRecord.get_by_id(self.user_id)
        if not presence.only_active_users(login_record):
                raise NotAuthorizedError(
                    'Connection no longer valid, must relogin')
        return login_record

    def render(self, template_name, context=None):
        """Renders the given template and context."""
        js_mode = 'compiled'
        if config.debug and config.is_dev_appserver:
            js_mode = self.request.get('js_mode', 'raw')

        my_context = {
            'cache_buster': config.version_id,
            'host_url': self.request.host_url,
            'js_mode': js_mode,
            'page_name': 'base',
            'site_name': config.site_name,
            'xsrf_token': self.session['xsrf_token'],
        }
        if context:
            my_context.update(context)

        self.response.out.write(
            template.render('templates/' + template_name, my_context))


class BaseRpcHandler(BaseHandler):
    """Base handler for turning responses into JSON.

    Sub-classes should override the handle() method and stuff their response
    parameters into self.json_response. In the event an exception is raised
    it will be returned to the caller as 'error_class' and 'error_detail'
    parameters in the JSON response with a 500 response. In the successful case
    the response will be JSON with a 200 response.

    Properties:
        all_shards: List of all shards this user is logged into.
        shard: The current logged in shard, set when 'require_shard' is True.
    """

    # By default RPCs are post only.
    get_enabled = False

    # Whether or not to require user log-in to the shard they assert.
    require_shard = False

    # Do not write the output JSON or content-type to the response.
    raw_response = False    # TODO(bslatkin): Refactor this to use BaseHandler

    def handle_request(self, *args):
        self.session = self.request.environ['beaker.session']
        if 'shards' in self.session:
            self.all_shards = self.session['shards']
        else:
            self.all_shards = []
        if self.require_shard:
            self.shard = self._verify_shard_login()
            self.user_id = self.all_shards[self.shard]
        else:
            self.shard = None
            self.user_id = None

        self.json_response = {}
        try:
            self.handle(*args)
        except Exception, e:
            logging.exception('Error encountered during RPC')
            self.json_response['errorClass'] = e.__class__.__name__
            self.json_response['errorDetail'] = str(e)
            self.json_response['errorTraceback'] = traceback.format_exc()
            self.response.set_status(500)
        finally:
            if not self.raw_response:
                self.response.headers['Content-Type'] = 'text/javascript'
                self.response.out.write(json.dumps(self.json_response))

    def handle(self):
        raise NotImplementedError('Override in sub-class')

    def _verify_shard_login(self):
        """Verifies the user is logged into the shard they assert, returns it.
        """
        shard = self.get_required('shard', str)
        if 'shards' not in self.session:
            raise NotAuthorizedError('Your cookie has no valid shards')
        if shard not in self.session['shards']:
            raise NotAuthorizedError('You may not access shard %s' % shard)
        return shard
